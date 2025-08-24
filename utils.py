import fitz  # PyMuPDF
from crewai_tools import BaseTool
from playwright.sync_api import sync_playwright

class PDFReadTool(BaseTool):
    name: str = "PDF Reader Tool"
    description: str = "Reads the text content of a local PDF file. Use this when you are given a path to a PDF document."

    def _run(self, file_path: str) -> str:
        try:
            document = fitz.open(file_path)
            text = ""
            for page_num in range(len(document)):
                page = document.load_page(page_num)
                text += page.get_text()
            return text
        except Exception as e:
            return f"Error reading PDF file: {e}"

class AdvancedScrapeTool(BaseTool):
    name: str = "Advanced Website Scraper"
    description: str = (
        "A powerful tool to scrape specific content from a website using a CSS selector. "
        "Use this when you need to extract a precise section of a webpage, avoiding irrelevant noise."
    )

    def _run(self, url: str, selector: str) -> str:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector(selector, timeout=10000)
                content = page.locator(selector).inner_text()
                browser.close()
                return content
        except Exception as e:
            return f"Error during scraping: {e}"