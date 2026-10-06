"""The FinScout crew: four agents that turn a regulatory circular into a report.

1. Regulatory Interpreter reads the circular (web page or PDF) and summarises it.
2. Business Impact Analyst searches FlexiPay India's internal documents in a
   Chroma vector database to find what the circular affects.
3. Strategy and Compliance Advisor drafts an action plan from that assessment.
4. Verification Specialist compares the three outputs with each other and
   flags anything inconsistent.

Each agent gets only the tools its job needs: the interpreter has one reader
(web page or PDF, bound to the document the user chose), the analyst has the
knowledge-base search, and the advisor and the verifier have no tools. All
model calls go to a local Ollama server.

Nothing here runs at import time. The models, the vector store and the crew
are created when ``run_crew`` is called.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

# Keep every byte on this machine: switch off CrewAI's anonymous telemetry and
# trace upload, Chroma's telemetry and LiteLLM's download of its model price list.
for _name, _value in {
    "CREWAI_DISABLE_TELEMETRY": "true",
    "CREWAI_TRACING_ENABLED": "false",
    "OTEL_SDK_DISABLED": "true",
    "ANONYMIZED_TELEMETRY": "False",
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
}.items():
    os.environ.setdefault(_name, _value)

from chromadb.config import Settings as ChromaSettings  # noqa: E402
from crewai import LLM, Agent, Crew, Process, Task  # noqa: E402
from crewai.tasks.task_output import TaskOutput  # noqa: E402
from crewai.tools import BaseTool  # noqa: E402
from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_ollama import OllamaEmbeddings  # noqa: E402
from langchain_text_splitters import MarkdownHeaderTextSplitter  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from utils import (  # noqa: E402
    MAX_DOCUMENT_CHARS,
    AdvancedScrapeTool,
    DocumentUnreadable,
    PDFReadTool,
    ToolInput,
)

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("FINSCOUT_CHAT_MODEL", "llama3:8b")
EMBEDDING_MODEL = "nomic-embed-text"
# Llama 3 8B's full context. Ollama's default is smaller and would silently
# drop the start of long prompts.
CONTEXT_TOKENS = 8192

APP_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_DIR = APP_DIR / "knowledge_base"
CHROMA_DIR = APP_DIR / "chroma_db"
SEARCH_RESULTS = 4


# --- Knowledge base -------------------------------------------------------

def _knowledge_base_fingerprint() -> str:
    digest = hashlib.sha256(EMBEDDING_MODEL.encode())
    for path in sorted(KNOWLEDGE_BASE_DIR.glob("**/*.md")):
        digest.update(path.relative_to(KNOWLEDGE_BASE_DIR).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _load_knowledge_base() -> list[Document]:
    """Load the markdown files and split them into one chunk per section."""
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("##", "document"), ("###", "section")],
        strip_headers=False,
    )
    chunks = []
    for path in sorted(KNOWLEDGE_BASE_DIR.glob("**/*.md")):
        for chunk in splitter.split_text(path.read_text(encoding="utf-8")):
            chunk.metadata["source"] = path.name
            chunks.append(chunk)
    return chunks


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    """Open the Chroma store, building it on first use.

    The collection name includes a hash of the knowledge-base files, so editing
    a file makes the next run embed the documents again.
    """
    store = Chroma(
        collection_name=f"flexipay_kb_{_knowledge_base_fingerprint()}",
        embedding_function=OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_URL),
        persist_directory=str(CHROMA_DIR),
        client_settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
    )
    if not store.get(limit=1)["ids"]:
        chunks = _load_knowledge_base()
        store.add_documents(chunks)
        print(f"Knowledge base: embedded {len(chunks)} sections from {KNOWLEDGE_BASE_DIR}")
    return store


class KnowledgeBaseQuery(ToolInput):
    query: str = Field(..., description="One specific question about FlexiPay India's products, policies or systems.")


class KnowledgeBaseSearchTool(BaseTool):
    name: str = "search_knowledge_base"
    description: str = (
        "Searches FlexiPay India's internal policy, product and infrastructure documents "
        "and returns the most relevant sections, each labelled with its source file. "
        "Ask one specific question per call, as plain text, for example: "
        '{"query": "Where is customer data stored?"}'
    )
    args_schema: type[BaseModel] = KnowledgeBaseQuery
    searches: list = Field(default_factory=list, exclude=True)

    def _run(self, query: str) -> str:
        results = get_vector_store().similarity_search(query, k=SEARCH_RESULTS)
        self.searches.append({"query": query, "sources": [_label(doc) for doc in results]})
        if not results:
            return "No matching section found in the knowledge base."
        return "\n\n".join(f"[Source: {_label(doc)}]\n{doc.page_content}" for doc in results)


def _label(doc: Document) -> str:
    section = doc.metadata.get("section")
    return f"{doc.metadata['source']} > {section}" if section else doc.metadata["source"]


# --- Crew -----------------------------------------------------------------

def get_llm() -> LLM:
    # LiteLLM's ollama_chat route lets us set num_ctx. CrewAI's native Ollama
    # route cannot, and it also sends native tool definitions, which Llama 3
    # rejects; through LiteLLM CrewAI falls back to text (ReAct) tool calls.
    return LLM(
        model=f"ollama_chat/{CHAT_MODEL}",
        base_url=OLLAMA_URL,
        is_litellm=True,
        temperature=0.2,
        num_ctx=CONTEXT_TOKENS,
    )


def _is_url(source: str) -> bool:
    return bool(re.match(r"https?://", source.strip(), re.IGNORECASE))


MIN_SEARCHES = 3
SUMMARY_MAX_CHARS = 2000  # about 300 words


@dataclass
class CrewRun:
    crew: Crew
    reader: AdvancedScrapeTool | PDFReadTool
    knowledge_base: KnowledgeBaseSearchTool


def build_crew(source: str, selector: str | None = None, verbose: bool = False) -> CrewRun:
    llm = get_llm()
    # The interpreter gets one reader, bound to the document the user chose.
    if _is_url(source):
        reader = AdvancedScrapeTool(url=source, css_selector=selector)
    else:
        reader = PDFReadTool(file_path=source)
    knowledge_base = KnowledgeBaseSearchTool()

    # Guardrails return (passed, output or feedback). No return annotation: CrewAI
    # inspects it at runtime and this module uses postponed annotations.
    def document_was_read(output: TaskOutput):
        # Without this check a small model sometimes "summarises" a circular it never read.
        if not reader.reads:
            return False, (
                f"You have not read the circular yet. Call the {reader.name} tool (it takes no "
                "arguments, so give an empty Action Input) and summarise the text it returns."
            )
        # It also sometimes returns the whole text, or only the title, instead of a summary.
        document_chars = min(reader.reads[-1]["chars"], MAX_DOCUMENT_CHARS)
        if len(output.raw) > min(SUMMARY_MAX_CHARS, max(600, 0.6 * document_chars)):
            return False, (
                "Your answer copies the circular instead of summarising it. Write a summary in "
                "your own words of at most 250 words, with the changes as short bullet points."
            )
        if not re.search(r"^\s*([-*\u2022]|\d+[.)])\s+\S", output.raw, re.MULTILINE):
            return False, (
                "Your summary lists no changes. Add each change or requirement in the circular "
                "as a short bullet point, with its paragraph number."
            )
        return True, output

    analyst_attempts = {"count": 0}

    def assessment_is_grounded(output: TaskOutput):
        analyst_attempts["count"] += 1
        problems = []
        if len(knowledge_base.searches) < MIN_SEARCHES:
            problems.append(
                f"You searched the knowledge base {len(knowledge_base.searches)} time(s). Make at "
                f"least {MIN_SEARCHES} searches with the search_knowledge_base tool, one specific "
                "question per change in the summary."
            )
        if not _CHANGE_BLOCK.search(output.raw):
            problems.append(
                "Your assessment is empty or not in the required format. Write one block per "
                "change, starting with 'Change:', each with 'Applies to FlexiPay', 'What FlexiPay "
                "does today', 'What FlexiPay must change' and 'Impact'."
            )
        if contradictory_ratings(output.raw):
            problems.append(
                "A change marked 'Applies to FlexiPay: No' must have 'What FlexiPay must change: "
                "Nothing' and 'Impact: None'."
            )
        summary = interpret_task.output.raw if interpret_task.output else ""
        for problem in coverage_problems(summary, output.raw):
            problems.append(
                f"In your assessment, {problem}. Assess exactly the changes listed in the summary, "
                "one 'Change:' block each, and search the knowledge base for each of them.")
        if any("needs no change yet is rated" in p for p in assessment_problems(output.raw)):
            problems.append("If FlexiPay must change Nothing, the Impact is None.")
        if not problems or analyst_attempts["count"] > 2:
            return True, output  # after two retries, accept; the report states what is wrong
        return False, " ".join(problems) + " Then write the assessment again."

    advisor_attempts = {"count": 0}

    def plan_is_consistent(output: TaskOutput):
        advisor_attempts["count"] += 1
        assessment = impact_task.output.raw if impact_task.output else ""
        problems = plan_problems(output.raw, assessment)
        if not problems or advisor_attempts["count"] > 2:
            return True, output  # after two retries, accept; the report states what is wrong
        return False, (
            "Your plan is inconsistent: " + "; ".join(problems) + ". Give one or more actions "
            "for each change rated High, Medium or Low, or, only if every change is rated None, "
            "write 'No changes are needed.' and at most two record-keeping steps."
        )

    interpreter = Agent(
        role="Regulatory Interpreter",
        goal="Read a regulatory circular and summarise exactly what it requires.",
        backstory=(
            "You are a legal analyst at an Indian fintech. You read circulars from the RBI and "
            "other regulators closely and report only what the text says."
        ),
        llm=llm,
        tools=[reader],
        allow_delegation=False,
        max_iter=5,
        verbose=verbose,
    )
    analyst = Agent(
        role="Business Impact Analyst",
        goal="Work out which FlexiPay India products, policies and systems a circular affects.",
        backstory=(
            "You are a business analyst at FlexiPay India, a fintech (not a bank) that runs a UPI "
            "app and a wallet. You check every claim against the company's own documents by searching "
            "the company knowledge base, and you say so when the documents are silent."
        ),
        llm=llm,
        tools=[knowledge_base],
        allow_delegation=False,
        max_iter=8,
        verbose=verbose,
    )
    advisor = Agent(
        role="Strategy and Compliance Advisor",
        goal="Turn an impact assessment into a short, prioritised action plan.",
        backstory=(
            "You are a compliance advisor who writes plans that name an owner, a priority and a "
            "deadline for every action."
        ),
        llm=llm,
        allow_delegation=False,
        max_iter=3,
        verbose=verbose,
    )
    verifier = Agent(
        role="Verification Specialist",
        goal="Check that the summary, the impact assessment and the action plan agree with each other.",
        backstory=(
            "You are a careful reviewer. You do not add new analysis; you look for statements "
            "that are unsupported by, or contradict, the earlier outputs."
        ),
        llm=llm,
        allow_delegation=False,
        max_iter=3,
        verbose=verbose,
    )

    interpret_task = Task(
        description=(
            f"Call the {reader.name} tool to get the text of the circular. It takes no arguments. "
            "Then summarise the circular in your own words, using only that text. Give: its title, "
            "issuer, reference number and date; who it applies to; each change or requirement as a "
            "short bullet point, with its paragraph number where the text has one; and the "
            "effective date or deadlines. Do not paste the text and do not use code blocks. Do not "
            "add requirements that are not in the text. If the text ends with a note that it was "
            "truncated, say that the summary covers only the part that was read. If the tool "
            "returns an error, report the error and do not invent a summary."
        ),
        expected_output=(
            "A markdown summary of at most 250 words: title, issuer, reference and date; who it "
            "applies to; key changes as bullet points with paragraph references; effective date."
        ),
        agent=interpreter,
        guardrail=document_was_read,
        guardrail_max_retries=2,
    )
    impact_task = Task(
        description=(
            "Assess the impact of the circular summarised above on FlexiPay India. Work in this "
            "order. First, list the changes in the summary. Second, for each change, call the "
            "search_knowledge_base tool with one specific question about it (for example who "
            "FlexiPay onboards, how it verifies identity, where it stores data, its limits or its "
            "complaint handling, whichever the change touches). Make at least three searches "
            "before you give your final answer. Third, write the assessment. Base every statement "
            "about FlexiPay on a section a search returned and put its source file in brackets, "
            "for example (kyc_policy.md). If no section covers a change, write 'No matching policy "
            "found' instead of guessing. Rule: if a change does not apply to FlexiPay, then What "
            "FlexiPay must change is Nothing and Impact is None."
        ),
        expected_output=(
            "For each change in the summary, this block:\n"
            "- Change: the change, as in the summary\n"
            "  - Applies to FlexiPay: Yes or No, and why, with source file\n"
            "  - What FlexiPay does today: from the knowledge base, with source file\n"
            "  - What FlexiPay must change: the work needed to comply, or Nothing\n"
            "  - Impact: High, Medium, Low or None"
        ),
        agent=analyst,
        context=[interpret_task],
        guardrail=assessment_is_grounded,
        guardrail_max_retries=2,
    )
    plan_task = Task(
        description=(
            "Draft an action plan from the impact assessment. For each change with Impact High, "
            "Medium or Low, give one or more actions that do what the assessment says FlexiPay "
            "must change, each with an owner (Compliance, Legal, Engineering, Operations or "
            "Product), a priority and a target date relative to the circular's effective date. "
            "Do not propose actions for changes with Impact None. If every change has Impact None, "
            "write only 'No changes are needed.' followed by at most two steps that record this "
            "conclusion. Never write both a list of actions and 'No changes are needed.' Do not "
            "add work that the assessment does not mention."
        ),
        expected_output=(
            "A numbered list of actions (action, owner, priority, target date, and the change it "
            "addresses), or 'No changes are needed.' followed by at most two record-keeping steps."
        ),
        agent=advisor,
        context=[impact_task],
        guardrail=plan_is_consistent,
        guardrail_max_retries=2,
    )
    verify_task = Task(
        description=(
            "Compare the summary of the circular, the impact assessment and the action plan with "
            "each other. You do not have the circular or the knowledge base, only these three "
            "outputs. Make these four checks, one at a time, quoting the text you rely on. "
            "(1) Coverage: list the changes in the summary; FAIL if any of them is missing from "
            "the impact assessment. "
            "(2) Ratings: for each change in the impact assessment, quote 'Applies to FlexiPay', "
            "'What FlexiPay must change' and 'Impact'. The correct combinations are: No, Nothing, "
            "None; or Yes, Nothing, None; or Yes, some work, High or Medium or Low. PASS if every "
            "change has a correct combination, otherwise FAIL. "
            "(3) Plan: FAIL if the plan says 'No changes are needed' and also lists actions, if a "
            "change rated High, Medium or Low has no action, or if an action asks for work the "
            "assessment does not call for. "
            "(4) Facts: FAIL if dates, amounts or who the circular applies to differ between the "
            "three outputs. "
            "For each check write its number, PASS or FAIL, and the reason. End with a final line "
            "that is exactly 'VERDICT: CONSISTENT' if all four checks pass, or 'VERDICT: "
            "INCONSISTENT' if any fails."
        ),
        expected_output="Four short paragraphs, one per check (PASS or FAIL with the quoted reason), then a last line 'VERDICT: CONSISTENT' or 'VERDICT: INCONSISTENT'.",
        agent=verifier,
        context=[interpret_task, impact_task, plan_task],
    )

    crew = Crew(
        agents=[interpreter, analyst, advisor, verifier],
        tasks=[interpret_task, impact_task, plan_task, verify_task],
        process=Process.sequential,
        memory=False,
        tracing=False,
        verbose=verbose,
    )
    return CrewRun(crew=crew, reader=reader, knowledge_base=knowledge_base)


# --- Entry point ----------------------------------------------------------

@dataclass
class Report:
    source: str
    markdown: str
    verdict: str  # "CONSISTENT", "INCONSISTENT" or "UNCLEAR"
    warnings: list[str] = field(default_factory=list)


_CHANGE_BLOCK = re.compile(r"(?im)^\W*change:")
_NO_CHANGES = re.compile(r"(?i)no changes are needed")
_NUMBERED = re.compile(r"(?m)^\s*\d+[.)]\s+\S")
_RATED = re.compile(r"(?i)impact\W*(high|medium|low)\b")


_IMPACT_LINE = re.compile(r"(?i)impact\W*(high|medium|low|none)\b")


def change_blocks(assessment: str) -> list[str]:
    """Split an assessment into one block per change.

    A `Change:` line starts a new block only once the current block has its
    Impact rating. Models sometimes add an explanatory "- Change: ..." line
    inside a block, and splitting on every such line made one change look like
    two, the first with no ratings at all.
    """
    blocks: list[str] = []
    current: list[str] | None = None
    for line in assessment.splitlines():
        starts = _CHANGE_BLOCK.match(line) is not None
        if starts and (current is None or _IMPACT_LINE.search("\n".join(current))):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


_BULLET = re.compile(r"(?m)^\s*(?:[-*\u2022]|\d+[.)])\s+(.+)$")
_STOPWORDS = frozenset(
    "the and for with that this from into their which shall must will have been "
    "such other under where when than more each also only least based".split())


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3 and w not in _STOPWORDS}


def summary_changes(summary: str) -> list[str]:
    """The bulleted changes listed in the interpreter's summary."""
    return [m.group(1).strip() for m in _BULLET.finditer(summary)]


def coverage_problems(summary: str, assessment: str) -> list[str]:
    """Changes in the summary that no change in the assessment talks about.

    A word-overlap test, deliberately loose: a change counts as covered if any
    assessed change shares at least two of its significant words. It is meant
    to catch an assessment about the wrong subject entirely, which a small
    model produced when its knowledge-base search drifted, not to grade
    wording.
    """
    titles = [_keywords(block.splitlines()[0] + " " + " ".join(block.splitlines()[1:2]))
              for block in change_blocks(assessment)]
    missing = []
    for change in summary_changes(summary):
        words = _keywords(change)
        if len(words) >= 2 and not any(len(words & title) >= 2 for title in titles):
            missing.append(change)
    if missing:
        listed = "; ".join(m if len(m) <= 80 else m[:77] + "..." for m in missing)
        return [f"the assessment does not cover {len(missing)} change(s) in the summary: {listed}"]
    return []


def assessment_problems(assessment: str) -> list[str]:
    """What is wrong with an impact assessment's shape, found by code.

    A small model can return an empty assessment, and the verification agent
    has been seen to pass one anyway. These checks do not depend on any model.
    """
    blocks = change_blocks(assessment)
    if not blocks:
        return ["the impact assessment is empty or has no 'Change:' entries"]
    problems = []
    for number, block in enumerate(blocks, 1):
        missing = [field for field, pattern in (
            ("Applies to FlexiPay", r"(?i)applies to flexipay\W*(yes|no)\b"),
            ("Impact", r"(?i)impact\W*(high|medium|low|none)\b"),
        ) if not re.search(pattern, block)]
        if missing:
            problems.append(f"change {number} in the assessment has no {' or '.join(missing)} rating")
        elif (re.search(r"(?i)must change\W*nothing\b", block)
              and re.search(r"(?i)impact\W*(high|medium|low)\b", block)):
            problems.append(f"change {number} needs no change yet is rated High, Medium or Low")
    if contradictory_ratings(assessment):
        problems.append("the assessment rates a change that does not apply to FlexiPay as "
                        "High, Medium or Low")
    return problems


def plan_problems(plan: str, assessment: str) -> list[str]:
    """Contradictions between the action plan and the assessment, found by code."""
    problems = []
    says_nothing_needed = bool(_NO_CHANGES.search(plan))
    actions = len(_NUMBERED.findall(plan))
    if says_nothing_needed and actions > 2:
        problems.append(f"the plan says 'No changes are needed' but lists {actions} actions")
    if says_nothing_needed and _RATED.search(assessment):
        problems.append("the plan says 'No changes are needed' but the assessment rates a "
                        "change High, Medium or Low")
    if not says_nothing_needed and actions == 0:
        problems.append("the plan has no actions and does not say that no changes are needed")
    return problems


def final_verdict(model_verdict: str, code_problems: list[str]) -> str:
    """The verifier's verdict, unless code found a problem it missed.

    A model saying CONSISTENT is never allowed to outrank a check that is
    certain: if code found a problem, the report is INCONSISTENT.
    """
    return "INCONSISTENT" if code_problems else model_verdict


def contradictory_ratings(assessment: str) -> bool:
    """True if a change marked as not applying to FlexiPay is still rated High, Medium or Low."""
    for block in change_blocks(assessment):
        applies = re.search(r"(?i)applies to flexipay\W*(yes|no)\b", block)
        impact = re.search(r"(?i)impact\W*(high|medium|low|none)\b", block)
        if applies and impact and applies.group(1).lower() == "no" and impact.group(1).lower() != "none":
            return True
    return False


def _verdict(text: str) -> str:
    """The verifier's last 'VERDICT: ...' line, or UNCLEAR if it did not write one."""
    matches = re.findall(r"VERDICT:\W*(INCONSISTENT|CONSISTENT)", text, re.IGNORECASE)
    return matches[-1].upper() if matches else "UNCLEAR"


def _unfence(text: str) -> str:
    """Remove a code fence wrapped around a whole answer so it renders as markdown."""
    match = re.fullmatch(r"```[a-z]*\n(.*)\n```", text.strip(), re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def run_crew(source: str, selector: str | None = None, verbose: bool = False) -> Report:
    """Analyse one circular (a URL or a local PDF path) and return the report.

    This is the entry point used by both the Streamlit app and cli.py.
    """
    source = source.strip()
    selector = (selector or "").strip() or None
    run = build_crew(source, selector, verbose=verbose)
    try:
        run.reader.prefetch()  # fail now, with the real reason, if the document can't be read
    except DocumentUnreadable as error:
        raise RuntimeError(f"No report was produced: {error}") from error
    get_vector_store()  # build the knowledge base before the agents need it
    unread = (
        "The Regulatory Interpreter did not manage to read the document, so no report was produced."
    )
    try:
        result = run.crew.kickoff()
    except Exception as error:
        if not run.reader.reads:
            raise RuntimeError(f"{unread} Last error: {error}") from error
        raise RuntimeError(f"The crew stopped before finishing the report: {error}") from error
    if not run.reader.reads:
        raise RuntimeError(unread)

    warnings = []
    chars = max(read["chars"] for read in run.reader.reads)
    if chars > MAX_DOCUMENT_CHARS:
        warnings.append(
            f"The document has {chars:,} characters; only the first {MAX_DOCUMENT_CHARS:,} were analysed."
        )
    searches = len(run.knowledge_base.searches)
    if searches < MIN_SEARCHES:
        warnings.append(
            f"The Business Impact Analyst searched the knowledge base {searches} time(s), fewer than "
            f"the {MIN_SEARCHES} it was asked for; parts of its assessment may not be grounded."
        )

    summary, impact, plan, verification = (_unfence(output.raw) for output in result.tasks_output)
    code_problems = (assessment_problems(impact) + coverage_problems(summary, impact)
                     + plan_problems(plan, impact))
    model_verdict = _verdict(verification)
    verdict = final_verdict(model_verdict, code_problems)
    if code_problems and model_verdict == "CONSISTENT":
        warnings.append("The verification agent said CONSISTENT, but the code checks found "
                        "problems it missed.")

    lines = [
        f"# FinScout report: {source}",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} with {CHAT_MODEL} on Ollama",
        f"- Verdict: {verdict}",
        f"- Code checks: {'passed' if not code_problems else '; '.join(code_problems)}",
        f"- Verification agent said: {model_verdict}",
        "- Status: draft for human review",
    ]
    lines += [f"- Warning: {warning}" for warning in warnings]
    lines += [
        "",
        "## 1. Summary of the circular",
        "",
        summary,
        "",
        "## 2. Impact on FlexiPay India",
        "",
        impact,
        "",
        "## 3. Action plan",
        "",
        plan,
        "",
        "## 4. Verification",
        "",
        verification,
        "",
        "## Appendix: knowledge-base searches",
        "",
    ]
    if run.knowledge_base.searches:
        for search in run.knowledge_base.searches:
            lines.append(f"- \"{search['query']}\" returned: {'; '.join(search['sources']) or 'nothing'}")
    else:
        lines.append("- None")
    return Report(source=source, markdown="\n".join(lines) + "\n", verdict=verdict, warnings=warnings)
