import streamlit as st
import pandas as pd
import os
from rag_agents import run_crew
from database import init_db, save_analysis, get_all_analyses

init_db()

st.set_page_config(page_title="FinScout AI v2", layout="wide")

st.sidebar.title("FinScout AI Navigation")
page = st.sidebar.radio("Go to", ["Live Analysis", "Past Analyses Archive"])

if page == "Live Analysis":
    st.title("🕵️ FinScout AI v2")
    st.markdown("### Autonomous Regulatory Intelligence System")
    
    source_type = st.radio("Select source type", ["URL", "PDF File"], horizontal=True)
    
    source = None
    if source_type == "URL":
        source = st.text_input("Enter URL of the regulatory circular:")
        st.info("Hint: For RBI, a good CSS selector is often `#tdcontent`")
    else:
        uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
        if uploaded_file is not None:
            if not os.path.exists("temp"):
                os.makedirs("temp")
            file_path = os.path.join("temp", uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            source = file_path

    if st.button("Analyze Regulation"):
        if source:
            with st.spinner("The AI agents are at work... This may take a few minutes."):
                try:
                    result = run_crew(source)
                    st.session_state['last_analysis'] = result
                    st.session_state['last_source'] = source
                except Exception as e:
                    st.error(f"An error occurred: {e}")
        else:
            st.warning("Please provide a source (URL or PDF).")

    if 'last_analysis' in st.session_state:
        st.subheader("Analysis Complete!")
        st.markdown(st.session_state['last_analysis'])
        
        st.subheader("Human-in-the-Loop Feedback")
        st.write("Save this analysis to the archive for future reference.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve & Save Analysis"):
                save_analysis(st.session_state['last_source'], st.session_state['last_analysis'], "approved")
                st.success("Analysis approved and saved to the archive!")
                del st.session_state['last_analysis']
        with col2:
            if st.button("🚩 Flag & Save for Review"):
                save_analysis(st.session_state['last_source'], st.session_state['last_analysis'], "flagged")
                st.warning("Analysis flagged and saved to the archive.")
                del st.session_state['last_analysis']

elif page == "Past Analyses Archive":
    st.title("📖 Past Analyses Archive")
    st.markdown("Review all previously saved analyses.")
    
    analyses = get_all_analyses()
    if analyses:
        df = pd.DataFrame(analyses, columns=['ID', 'Source', 'Analysis', 'Status', 'Timestamp'])
        
        for index, row in df.iterrows():
            status_color = "green" if row['Status'] == 'approved' else "orange"
            with st.expander(f"**{row['Timestamp']}** | **Source:** `{row['Source']}` | **Status:** :{status_color}[{row['Status'].upper()}]"):
                st.markdown(row['Analysis'])
    else:
        st.info("No past analyses found in the database.")