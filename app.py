import streamlit as st
import pandas as pd
import os
from rag_agents import run_crew
from database import init_db, save_analysis, get_all_analyses

# Initialize the database
init_db()

st.set_page_config(layout="wide")

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Live Analysis", "Past Analyses"])

if page == "Live Analysis":
    st.title("🕵️ FinScout AI v2")
    st.markdown("### Persistent Regulatory Intelligence")
    
    source_type = st.radio("Select source type", ["URL", "PDF File"])
    
    source = None
    if source_type == "URL":
        source = st.text_input("Enter URL of the regulatory circular:")
    else:
        uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
        if uploaded_file is not None:
            # Save the PDF temporarily to be read by the agent
            if not os.path.exists("temp"):
                os.makedirs("temp")
            file_path = os.path.join("temp", uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            source = file_path

    if st.button("Analyze"):
        if source:
            with st.spinner("The local AI agents are at work... This may take a moment."):
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
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve Analysis"):
                save_analysis(st.session_state['last_source'], st.session_state['last_analysis'], "approved")
                st.success("Analysis approved and saved!")
                del st.session_state['last_analysis'] # Clear after action
        with col2:
            if st.button("🚩 Flag for Review"):
                save_analysis(st.session_state['last_source'], st.session_state['last_analysis'], "flagged")
                st.warning("Analysis flagged and saved for review.")
                del st.session_state['last_analysis']

elif page == "Past Analyses":
    st.title("📖 Past Analyses Archive")
    
    analyses = get_all_analyses()
    if analyses:
        df = pd.DataFrame(analyses, columns=['ID', 'Source', 'Analysis', 'Status', 'Timestamp'])
        
        # Displaying with better formatting
        for index, row in df.iterrows():
            with st.expander(f"{row['Timestamp']} - {row['Source']} ({row['Status'].upper()})"):
                st.markdown(row['Analysis'])
    else:
        st.info("No past analyses found.")