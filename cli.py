"""Run FinScout on one circular from the command line, without the web UI.

Calls the same entry point as the Streamlit app (rag_agents.run_crew).

    python cli.py "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13699&Mode=0" --out report.md
    python cli.py path/to/circular.pdf
"""

import argparse
import sys
import time

from rag_agents import run_crew


def main() -> int:
    parser = argparse.ArgumentParser(description="Write an impact assessment for one regulatory circular.")
    parser.add_argument("source", help="URL of the circular (HTML page or PDF), or the path to a local PDF")
    parser.add_argument("--selector", help="optional CSS selector for the circular's text on a web page")
    parser.add_argument("--out", help="write the report to this file instead of printing it")
    parser.add_argument("--verbose", action="store_true", help="print the agents' steps and tool calls")
    args = parser.parse_args()

    started = time.monotonic()
    try:
        report = run_crew(args.source, args.selector, verbose=args.verbose)
    except RuntimeError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - started

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(report.markdown)
    else:
        print(report.markdown)
    for warning in report.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    print(f"Finished in {elapsed:.0f} s. Verdict: {report.verdict}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
