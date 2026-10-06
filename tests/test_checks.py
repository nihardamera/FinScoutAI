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
    assessment_problems,
    change_blocks,
    final_verdict,
    plan_problems,
    _unfence,
    _verdict,
    contradictory_ratings,
)
from utils import (
    MAX_DOCUMENT_CHARS,
    AdvancedScrapeTool,
    DocumentUnreadable,
    PDFReadTool,
    _for_agent,
    extract_page_text,
    pdf_text,
)

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


class TestReadingBeforeTheAgentsStart:
    """A broken document fails in seconds with its real cause, not after
    the model has been retried at a tool that cannot succeed."""

    def test_a_missing_pdf_fails_up_front_with_the_reason(self, tmp_path):
        tool = PDFReadTool(file_path=str(tmp_path / "missing.pdf"))
        with pytest.raises(DocumentUnreadable, match="could not read the PDF"):
            tool.prefetch()

    def test_a_non_web_address_is_refused_before_any_fetch(self):
        with pytest.raises(DocumentUnreadable, match="not an http"):
            AdvancedScrapeTool(url="file:///etc/passwd").prefetch()

    def test_a_fetch_failure_names_the_real_cause(self, monkeypatch):
        def broken(url, selector):
            raise RuntimeError("Executable doesn't exist at /path/to/chromium\nmore detail")
        monkeypatch.setattr(AdvancedScrapeTool, "_fetch", staticmethod(broken))
        with pytest.raises(DocumentUnreadable, match="Executable doesn't exist"):
            AdvancedScrapeTool(url="https://example.org/circular").prefetch()

    def test_the_pre_flight_read_does_not_count_as_the_agent_reading_it(self, tmp_path):
        """Otherwise the guardrail that checks the agent opened the document
        would pass without the agent ever calling its tool."""
        path = tmp_path / "circular.pdf"
        document = fitz.open()
        document.new_page().insert_text((72, 72), "Directions on payment aggregators")
        document.save(path)
        tool = PDFReadTool(file_path=str(path))
        tool.prefetch()
        assert tool.reads == []
        assert "payment aggregators" in tool._run()
        assert len(tool.reads) == 1

    def test_the_page_is_fetched_once(self, monkeypatch):
        calls = []
        def fetch(url, selector):
            calls.append(url)
            return "Circular text"
        monkeypatch.setattr(AdvancedScrapeTool, "_fetch", staticmethod(fetch))
        tool = AdvancedScrapeTool(url="https://example.org/circular")
        tool.prefetch()
        tool._run()
        assert calls == ["https://example.org/circular"]


GOOD_ASSESSMENT = """Change: Two-factor authentication for digital payments
  - Applies to FlexiPay: Yes, it runs UPI payments (products.md)
  - What FlexiPay does today: UPI PIN and device binding (fraud_risk_policy.md)
  - What FlexiPay must change: Nothing
  - Impact: None
Change: Risk-based checks on high-risk transactions
  - Applies to FlexiPay: Yes (fraud_risk_policy.md)
  - What FlexiPay does today: fixed rules only
  - What FlexiPay must change: add behavioural checks
  - Impact: Medium"""


class TestCodeChecksOverrideTheModel:
    """In a real run Llama 3 8B returned an empty impact assessment and the
    verification agent still answered CONSISTENT. These checks need no model."""

    def test_an_empty_assessment_is_caught(self):
        assert assessment_problems("") == [
            "the impact assessment is empty or has no 'Change:' entries"]

    def test_a_change_without_ratings_is_caught(self):
        problems = assessment_problems("Change: Two-factor authentication\n- Notes: important")
        assert problems == ["change 1 in the assessment has no Applies to FlexiPay or Impact rating"]

    def test_a_well_formed_assessment_passes(self):
        assert assessment_problems(GOOD_ASSESSMENT) == []

    def test_a_plan_that_says_nothing_is_needed_but_lists_actions_is_caught(self):
        plan = "1. Review policies\n2. Train staff\n3. Audit\nNo changes are needed."
        assert "lists 3 actions" in plan_problems(plan, GOOD_ASSESSMENT)[0]

    def test_nothing_needed_contradicts_a_rated_change(self):
        problems = plan_problems("No changes are needed.\n1. Record this.", GOOD_ASSESSMENT)
        assert any("rates a change High, Medium or Low" in p for p in problems)

    def test_a_plan_with_actions_for_a_rated_change_passes(self):
        plan = "1. Add behavioural checks to the fraud engine. Owner: Engineering."
        assert plan_problems(plan, GOOD_ASSESSMENT) == []

    def test_the_model_cannot_pass_what_code_failed(self):
        assert final_verdict("CONSISTENT", ["the impact assessment is empty"]) == "INCONSISTENT"
        assert final_verdict("CONSISTENT", []) == "CONSISTENT"
        assert final_verdict("UNCLEAR", []) == "UNCLEAR"


class TestReadingTheAssessmentFormat:
    def test_an_explanation_line_inside_a_change_does_not_split_it(self):
        """The exact shape Llama 3 8B produced on the RBI authentication
        directions, which the first version of this check misread as ten
        changes, half of them unrated."""
        assessment = (
            "Change: Minimum two factors of authentication\n"
            "- Change: This change is already met by FlexiPay India.\n"
            "- Applies to FlexiPay: Yes\n"
            "- What FlexiPay must change: Nothing\n"
            "- Impact: None\n"
            "\n"
            "Change: Cross-border card-not-present checks\n"
            "- Change: This change does not apply to FlexiPay India.\n"
            "- Applies to FlexiPay: No\n"
            "- Impact: None\n")
        assert len(change_blocks(assessment)) == 2
        assert assessment_problems(assessment) == []

    def test_a_contradiction_is_still_found_inside_such_a_block(self):
        assessment = ("Change: A\n- Change: explanation\n- Applies to FlexiPay: No\n"
                      "- Impact: High")
        assert contradictory_ratings(assessment)
