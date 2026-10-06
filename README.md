# FinScout AI

Give it a regulatory circular, as a web page or a PDF, and it writes an impact
assessment and an action plan for FlexiPay India, a fictional Indian fintech.
Four agents built with CrewAI do the work in sequence, all running on a local
Llama 3 8B model through Ollama, so the document is never sent to an outside
service. The report is a draft for a person to review; they then archive it as
approved or flag it for follow-up.

A report produced by the current code, unedited, is in
[`examples/sample_report.md`](examples/sample_report.md).

## The four agents

| Agent | Job | Tools |
| --- | --- | --- |
| Regulatory Interpreter | Reads the circular and summarises what changes, with paragraph numbers | A reader bound to the one document you chose (web page or PDF) |
| Business Impact Analyst | Decides, change by change, whether it applies to FlexiPay and what would have to change | Search over FlexiPay's internal policies in a Chroma vector database |
| Strategy and Compliance Advisor | Turns the assessment into a prioritised action plan | None |
| Verification Specialist | Checks the summary, the assessment and the plan against each other and gives a verdict | None |

Each agent has only the tool its job needs. Only the analyst can search the
policies, and only the interpreter can read the document.

## The checks around the agents

A small model left to itself will sometimes summarise a document it never
opened, or rate a change as "does not apply" and "high impact" at once. Code,
not the model, checks for these and sends the answer back with the reason:

- The summary is rejected if the reader tool was never called, if it copies the
  circular instead of summarising it, or if it lists no changes.
- The assessment is rejected if the analyst made fewer than three knowledge-base
  searches, or if a change marked as not applying still has an impact rating.
  After two retries it is accepted, and the report says what is still wrong.
- The verifier must end with `VERDICT: CONSISTENT` or `VERDICT: INCONSISTENT`.
  The verdict is read from that line by code; if it is missing the report says
  `UNCLEAR` rather than assuming a pass.
- Every knowledge-base search and what it returned is listed at the end of the
  report, so a reader can see what the assessment was based on.
- Documents longer than 12,000 characters are cut, and the report says so.

## Setup

Requires Python 3.12 and [Ollama](https://ollama.com).

```bash
git clone https://github.com/nihardamera/FinScoutAI.git
cd FinScoutAI
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

ollama pull llama3:8b
ollama pull nomic-embed-text
```

The knowledge base (`knowledge_base/*.md`) is embedded with `nomic-embed-text`
on first use and stored in `chroma_db/`. It is rebuilt automatically when the
files change. `FINSCOUT_CHAT_MODEL` and `OLLAMA_BASE_URL` override the model
and the Ollama address.

## Run

```bash
.venv/bin/streamlit run app.py                     # web UI with the archive
.venv/bin/python cli.py "<circular URL or PDF path>" --out report.md
```

Without a CSS selector the reader keeps the page's main text and drops menus
and footers. On RBI notification pages `table.tablebg` selects just the
circular. On an Apple M4 laptop a run takes two to four minutes.

```bash
.venv/bin/python -m pytest      # the reading and checking code; no model needed
```

## Limitations

- The knowledge base describes a fictional company in six short documents. It
  shows how the retrieval works; it is not a real compliance corpus.
- The verifier only compares the three outputs with each other. It does not
  see the circular or the policies, so it can catch contradictions but not a
  summary that misreads the source.
- Llama 3 8B is a small model. Its checks are shallow: in the sample report the
  plan says "No changes are needed" and then lists two filing steps, and the
  verifier does not object. Treat every report as a first draft.
- It analyses one document per run, on demand. It does not monitor regulators'
  websites.
- The archive (SQLite) is a list of past reports with their status; it is not
  searchable.
