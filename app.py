import os

import streamlit as st

from database import get_all_analyses, init_db, save_analysis
from rag_agents import CHAT_MODEL, run_crew

init_db()

st.set_page_config(page_title="FinScout AI", layout="wide")

st.sidebar.title("FinScout AI")
page = st.sidebar.radio("Go to", ["New analysis", "Archive"])

if page == "New analysis":
    st.title("FinScout AI")
    st.markdown(
        "Impact assessment and action plan for a regulatory circular, written for "
        f"FlexiPay India (a fictional fintech) by four agents running on a local `{CHAT_MODEL}` model."
    )

    source_type = st.radio("Source", ["URL", "PDF file"], horizontal=True)

    source = None
    selector = None
    if source_type == "URL":
        source = st.text_input("URL of the circular (web page or PDF)")
        selector = st.text_input(
            "CSS selector (optional)",
            help=(
                "Leave empty to let the reader find the main content. To limit it to one element, "
                "give a selector, for example table.tablebg on RBI notification pages."
            ),
        )
    else:
        uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
        if uploaded_file is not None:
            os.makedirs("temp", exist_ok=True)
            file_path = os.path.join("temp", os.path.basename(uploaded_file.name))
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            source = file_path

    if st.button("Analyse"):
        if source:
            with st.spinner("The agents are working. On a laptop this takes several minutes."):
                try:
                    st.session_state["last_report"] = run_crew(source, selector)
                except Exception as e:
                    st.error(f"The analysis failed: {e}")
        else:
            st.warning("Give a URL or upload a PDF first.")

    if "last_report" in st.session_state:
        report = st.session_state["last_report"]
        st.subheader("Report")
        if report.verdict == "CONSISTENT":
            st.info("The verification agent found the summary, impact assessment and plan consistent.")
        else:
            st.warning(f"The verification agent's verdict is {report.verdict}. See section 4 of the report.")
        st.markdown(report.markdown)

        st.subheader("Review")
        st.write("The report is a draft. Archive it as approved or flag it for follow-up.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Approve and archive"):
                save_analysis(report.source, report.markdown, "approved")
                st.success("Saved to the archive as approved.")
                del st.session_state["last_report"]
        with col2:
            if st.button("Flag and archive"):
                save_analysis(report.source, report.markdown, "flagged")
                st.warning("Saved to the archive as flagged.")
                del st.session_state["last_report"]

elif page == "Archive":
    st.title("Archive")
    st.markdown("Saved reports, newest first.")

    analyses = get_all_analyses()
    if analyses:
        for _id, source, analysis, status, timestamp in analyses:
            status_color = "green" if status == "approved" else "orange"
            with st.expander(f"**{timestamp}** | `{source}` | :{status_color}[{status.upper()}]"):
                st.markdown(analysis)
    else:
        st.info("No saved reports yet.")
