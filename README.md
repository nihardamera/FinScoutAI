# 🕵️ FinScout AI v2: Autonomous Regulatory Intelligence System

**FinScout AI is a multi-agent system that automates the entire workflow of regulatory compliance for financial technology companies.** It proactively monitors web pages and PDF documents for new regulations, interprets their meaning, analyzes their business impact using a sophisticated RAG pipeline, formulates a strategic action plan, and verifies its own work for accuracy.

This project is built to be **100% free, private, and offline-capable**, running entirely on local open-source models.

---

## ✨ Key Features & Improvements

* **Multi-Source Ingestion:** Analyzes regulations from both **live URLs** and uploaded **PDF documents**.
* **Advanced RAG Pipeline:**
    * **Semantic Chunking:** Splits documents based on meaning, not arbitrary length, for superior context.
    * **Multi-Query Retriever:** The AI automatically rewrites a single question into multiple perspectives to find more comprehensive and accurate information in the knowledge base.
* **Self-Correction & Verification:** A dedicated `Verification Agent` reviews the final output, cross-referencing it against the source material to reduce errors and hallucinations.
* **Persistent Memory:** Every analysis is saved to a local **SQLite database**, creating a searchable archive of past compliance work.
* **Human-in-the-Loop (HITL) Simulation:** The UI includes a feedback mechanism (`Approve` / `Flag for Review`) to simulate a real-world workflow where a human compliance officer oversees the AI's work.
* **Optimized for Local Performance:** Uses lightweight, high-performance local models (`llama3:8b` and `nomic-embed-text`) for fast and efficient operation on consumer hardware.

---

## 🏛️ System Architecture

The system is designed as a collaborative "Crew" of four specialized AI agents:

1.  **`Regulator-Interpreter`**: The legal expert. It uses advanced scraping and PDF reading tools to ingest and summarize the raw regulatory text.
2.  **`Impact-Analyst`**: The business detective. It uses the advanced Multi-Query RAG tool to search the company's internal knowledge base and pinpoint exactly which products and processes are affected by the new rule.
3.  **`Strategy-Advisor`**: The consultant. It synthesizes the impact analysis into a clear, prioritized, and actionable strategic plan for different departments.
4.  **`Verification-Agent`**: The fact-checker. As the final step, it reviews the entire workflow to ensure the strategic plan is logically derived from and consistent with the source regulation.



---

## 🚀 Getting Started

### **Prerequisites**
* Python 3.9+
* [Ollama](https://ollama.com) installed and running on your machine.

### **Setup Instructions**

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/finscout-ai.git](https://github.com/your-username/finscout-ai.git)
    cd finscout-ai
    ```

2.  **Pull the necessary Ollama models:**
    ```bash
    ollama pull llama3:8b
    ollama pull nomic-embed-text
    ```

3.  **Create a virtual environment and install dependencies:**
    This single command creates the environment, activates it, and installs all required packages.

    * **For macOS / Linux:**
        ```bash
        python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
        ```
    * **For Windows (Command Prompt):**
        ```powershell
        python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt
        ```

### **Running the Application**

With your virtual environment active and Ollama running, start the Streamlit app:
```bash
streamlit run app.py