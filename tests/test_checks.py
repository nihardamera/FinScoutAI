"""The code around the agents: what they read, and how their answers are judged.

These parts decide what reaches the model and what counts as a pass, so they
are tested without the model. None of them need Ollama.
"""
from __future__ import annotations

import fitz  # PyMuPDF
import pytest

from rag_agents import (
    KnowledgeBaseQuery,
    _load_knowledge_base,
    _unfence,
    _verdict,
    contradictory_ratings,
)
from utils import MAX_DOCUMENT_CHARS, _for_agent, extract_page_text, pdf_text

CIRCULAR_PAGE = """
<html><head><title>RBI</title><script>var tracking = 1;</script></head>
<body>
  <nav><a href="/">Home</a> <a href="/notifications">Notifications</a> <a href="/press">Press</a></nav>
  <div id="sidebar"><ul><li><a href="/a">Archive 2025</a></li><li><a href="/b">Archive 2024</a></li></ul></div>
  <div id="tdcontent">
    <p>RBI/2026-27/99 Reserve Bank of India (Payment Aggregators) Amendment Directions, 2026.</p>
    <p>1. All payment aggregators shall complete merchant due diligence before onboarding.</p>
    <p>2. These directions shall come into force with immediate effect for all authorised entities.</p>
  </div>
  <footer>Copyright Reserve Bank of India. All rights reserved. Terms of use.</footer>
</body></html>
"""


class TestReadingAPage:
    def test_the_main_text_is_kept_and_the_navigation_dropped(self):
        text = extract_page_text(CIRCULAR_PAGE)
        assert "merchant due diligence" in text
        assert "Archive 2025" not in text
        assert "tracking" not in text  # scripts are removed before anything else

    def test_a_selector_picks_exactly_that_element(self):
        text = extract_page_text(CIRCULAR_PAGE, selector="#tdcontent")
        assert text.startswith("RBI/2026-27/99")
        assert "Copyright" not in text

    def test_a_selector_that_matches_nothing_says_so(self):
        with pytest.raises(ValueError, match="matched nothing"):
            extract_page_text(CIRCULAR_PAGE, selector="#does-not-exist")


class TestReadingAPdf:
    def test_text_is_extracted_from_a_real_pdf(self, tmp_path):
        path = tmp_path / "circular.pdf"
        document = fitz.open()
        document.new_page().insert_text((72, 72), "Directions on digital payment authentication")
        document.save(path)
        assert "digital payment authentication" in pdf_text(path=str(path))

    def test_long_documents_are_cut_and_the_cut_is_stated(self):
        text = _for_agent("x" * (MAX_DOCUMENT_CHARS + 500))
        assert "[Truncated" in text
        assert f"{MAX_DOCUMENT_CHARS:,}" in text


class TestJudgingTheAnswers:
    def test_a_change_that_does_not_apply_cannot_carry_an_impact(self):
        bad = ("Change: KYC for NRIs\n- Applies to FlexiPay: No\n"
               "- What FlexiPay must change: Nothing\n- Impact: High")
        good = bad.replace("Impact: High", "Impact: None")
        assert contradictory_ratings(bad)
        assert not contradictory_ratings(good)

    def test_each_change_is_judged_on_its_own(self):
        two = ("Change: A\n- Applies to FlexiPay: Yes\n- Impact: High\n"
               "Change: B\n- Applies to FlexiPay: No\n- Impact: None")
        assert not contradictory_ratings(two)

    def test_the_verdict_is_read_from_the_last_verdict_line(self):
        assert _verdict("Check 1 PASS\nVERDICT: INCONSISTENT") == "INCONSISTENT"
        assert _verdict("draft said VERDICT: CONSISTENT\nfinal: VERDICT: INCONSISTENT") == "INCONSISTENT"

    def test_a_missing_verdict_is_unclear_not_a_pass(self):
        assert _verdict("All four checks look fine to me.") == "UNCLEAR"

    def test_a_fenced_answer_is_unwrapped(self):
        assert _unfence("```markdown\n## Plan\n1. Do it\n```") == "## Plan\n1. Do it"


class TestRepairingToolArguments:
    def test_a_copied_schema_layout_is_turned_into_plain_arguments(self):
        """Llama 3 8B sometimes echoes the JSON schema it was shown."""
        repaired = KnowledgeBaseQuery.model_validate(
            {"properties": {"query": {"description": "KYC limits for wallets"}}})
        assert repaired.query == "KYC limits for wallets"

    def test_plain_arguments_pass_through(self):
        assert KnowledgeBaseQuery.model_validate({"query": "refund timelines"}).query == "refund timelines"


class TestTheKnowledgeBase:
    def test_policies_are_split_into_sections_that_name_their_file(self):
        """Each search result can then be cited as 'kyc_policy.md > section'."""
        chunks = _load_knowledge_base()
        sources = {c.metadata["source"] for c in chunks}
        assert {"kyc_policy.md", "products.md"} <= sources
        assert all(c.page_content.strip() for c in chunks)
        assert len(chunks) > len(sources)  # sections, not whole files
