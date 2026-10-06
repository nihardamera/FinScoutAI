"""Tools used by the Regulatory Interpreter agent to read a circular.

Both tools return plain text. Long documents are cut to MAX_DOCUMENT_CHARS so
that the text, the agent's instructions and its answer fit in Llama 3 8B's
8,192-token context window; the cut is stated at the end of the returned text.
Every successful read is recorded in ``reads`` so the caller can confirm that
the agent actually read the document instead of answering from memory.
"""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlparse

import pymupdf
from bs4 import BeautifulSoup, Comment, NavigableString
from crewai.tools import BaseTool
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field, model_validator

# About 3,000 Llama 3 tokens of English text.
MAX_DOCUMENT_CHARS = 12_000

# Some regulator sites (rbidocs.rbi.org.in among them) reject the default
# "HeadlessChrome" user agent, so present an ordinary desktop Chrome one.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Elements that never hold the body of a circular.
_BOILERPLATE_TAGS = [
    "script", "style", "noscript", "template", "svg", "nav", "header",
    "footer", "aside", "iframe", "button", "select", "input", "textarea",
]
_LINE_BREAK_TAGS = [
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "section", "article", "main", "blockquote", "pre", "dd", "dt",
]
_CONTAINER_TAGS = {"main", "article", "section", "div", "td", "table", "body"}
# A text run this long, outside a link, is treated as prose rather than a menu item.
_PROSE_MIN_CHARS = 40


# Llama 3 8B tends to answer with the tool output copied verbatim. A reminder
# placed after the text, where the model reads last, prevents most of that.
_SUMMARY_REMINDER = (
    "\n\n[End of the circular. Now write the summary the task asks for, in your own words, "
    "with the changes as short bullet points. Do not copy this text.]"
)


def _for_agent(text: str) -> str:
    """Cut the text to fit the context window and add the summary reminder."""
    if len(text) > MAX_DOCUMENT_CHARS:
        text = (
            text[:MAX_DOCUMENT_CHARS]
            + f"\n\n[Truncated: the document has {len(text):,} characters; "
            f"only the first {MAX_DOCUMENT_CHARS:,} were read.]"
        )
    return text + _SUMMARY_REMINDER


def _element_text(element) -> str:
    """Text of an element with one line per block and runs of whitespace collapsed."""
    for tag in element.find_all(_LINE_BREAK_TAGS):
        tag.insert_after(NavigableString("\n"))
    for cell in element.find_all(["td", "th"]):
        cell.insert_after(NavigableString(" "))
    lines = [re.sub(r"\s+", " ", line).strip() for line in element.get_text().splitlines()]
    kept: list[str] = []
    for line in lines:
        if line or (kept and kept[-1]):
            kept.append(line)
    return "\n".join(kept).strip()


def _main_content(soup: BeautifulSoup):
    """Pick the element that holds the page's main prose.

    Start from <main>, <article> or [role=main] when the page has one, else
    <body>. Inside it, score each container by the prose it holds (text runs of
    40+ characters that are not links) minus half of everything else (menu
    items, link lists, labels), and return the best one. This keeps the body of
    a circular and drops navigation, archive lists and footers.
    """
    root = soup.body or soup
    for selector in ("main", "article", "[role=main]"):
        candidate = soup.select_one(selector)
        if candidate is not None and len(candidate.get_text(" ", strip=True)) > 500:
            root = candidate
            break

    prose: dict[int, int] = defaultdict(int)
    other: dict[int, int] = defaultdict(int)
    for string in root.find_all(string=True):
        length = len(string.strip())
        if not length:
            continue
        is_prose = length >= _PROSE_MIN_CHARS and string.find_parent("a") is None
        tally = prose if is_prose else other
        for parent in string.parents:
            if parent.name in _CONTAINER_TAGS or parent is root:
                tally[id(parent)] += length
            if parent is root:
                break

    def score(element) -> float:
        return prose[id(element)] - 0.5 * other[id(element)]

    best = root
    for element in root.find_all(list(_CONTAINER_TAGS)):
        if score(element) > score(best):
            best = element
    return best


def extract_page_text(html: str, selector: str | None = None) -> str:
    """Return the readable text of an HTML page.

    With a CSS selector, return the text of the first matching element.
    Without one, return the text of the main content (see ``_main_content``).
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_BOILERPLATE_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    if selector:
        element = soup.select_one(selector)
        if element is None:
            raise ValueError(f"the CSS selector {selector!r} matched nothing on the page")
    else:
        element = _main_content(soup)
    return _element_text(element)


def pdf_text(data: bytes | None = None, path: str | None = None) -> str:
    """Text of a PDF given either its bytes or its path."""
    document = pymupdf.open(stream=data, filetype="pdf") if data is not None else pymupdf.open(path)
    with document:
        return "\n".join(page.get_text() for page in document).strip()


class ToolInput(BaseModel):
    """Base for tool arguments that repairs two common small-model mistakes.

    Llama 3 8B sometimes copies the layout of the JSON schema it is shown, and
    sends {"properties": {"query": ...}} or {"query": {"description": "..."}}
    instead of {"query": "..."}. Both are turned into the plain form. A value
    that is just the schema's own description is left alone, so it still fails.
    """

    @model_validator(mode="before")
    @classmethod
    def _repair_schema_echo(cls, data):
        if isinstance(data, dict) and isinstance(data.get("properties"), dict):
            data = data["properties"]
        if not isinstance(data, dict):
            return data
        repaired = dict(data)
        for name, field_info in cls.model_fields.items():
            value = data.get(name)
            if not isinstance(value, dict):
                continue
            for key in ("value", "description", "example"):
                text = value.get(key)
                if isinstance(text, str) and text.strip() and text != field_info.description:
                    repaired[name] = text
                    break
        return repaired


class NoArguments(BaseModel):
    """The reader tools take no arguments; anything the model sends is ignored."""


class AdvancedScrapeTool(BaseTool):
    """Reads the circular at a URL chosen by the user.

    The URL and the optional CSS selector come from the person running the
    analysis (the app's form or cli.py), not from the model, so the model
    cannot be steered into fetching some other address.
    """

    name: str = "read_web_page"
    description: str = (
        "Returns the text of the circular being analysed, read from its web page (or from the "
        "PDF at that address). Takes no arguments."
    )
    args_schema: type[BaseModel] = NoArguments
    url: str
    css_selector: str | None = None
    reads: list = Field(default_factory=list, exclude=True)

    def _run(self, **_ignored) -> str:
        url = self.url.strip()
        if urlparse(url).scheme not in ("http", "https"):
            return f"Error: {url!r} is not an http(s) address."
        selector = (self.css_selector or "").strip() or None
        try:
            text = self._fetch(url, selector)
        except Exception as error:  # reported back to the agent as text
            message = str(error).strip()
            return f"Error reading {url}: {message.splitlines()[0] if message else type(error).__name__}"
        if not text:
            return f"Error reading {url}: the page has no readable text."
        self.reads.append({"source": url, "selector": selector, "chars": len(text)})
        return _for_agent(text)

    @staticmethod
    def _fetch(url: str, selector: str | None) -> str:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=BROWSER_USER_AGENT)
                if urlparse(url).path.lower().endswith(".pdf"):
                    return _download_pdf_text(context, url)
                page = context.new_page()
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except PlaywrightError as error:
                    # Chromium turns a PDF response into a download and aborts the navigation.
                    if "Download is starting" in str(error):
                        return _download_pdf_text(context, url)
                    raise
                if response is not None and "pdf" in response.headers.get("content-type", ""):
                    return pdf_text(data=response.body())
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightError:
                    pass  # some pages never go idle; use what has rendered
                if selector:
                    page.wait_for_selector(selector, timeout=10_000)
                return extract_page_text(page.content(), selector)
            finally:
                browser.close()


def _download_pdf_text(context, url: str) -> str:
    response = context.request.get(url, timeout=60_000)
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status}")
    body = response.body()
    if not body.startswith(b"%PDF"):
        raise RuntimeError(
            f"expected a PDF but got {response.headers.get('content-type', 'unknown content')}"
        )
    return pdf_text(data=body)


class PDFReadTool(BaseTool):
    """Reads the PDF file chosen by the user (an upload in the app, or a path given to cli.py)."""

    name: str = "read_pdf_file"
    description: str = "Returns the text of the circular being analysed, read from its PDF file. Takes no arguments."
    args_schema: type[BaseModel] = NoArguments
    file_path: str
    reads: list = Field(default_factory=list, exclude=True)

    def _run(self, **_ignored) -> str:
        try:
            text = pdf_text(path=self.file_path)
        except Exception as error:
            return f"Error reading PDF file {self.file_path}: {error}"
        if not text:
            return f"Error reading PDF file {self.file_path}: no text layer (a scanned PDF needs OCR first)."
        self.reads.append({"source": self.file_path, "selector": None, "chars": len(text)})
        return _for_agent(text)
