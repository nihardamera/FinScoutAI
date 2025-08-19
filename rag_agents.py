from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool
from langchain.tools import Tool
from langchain_community.chat_models import ChatOllama
from langchain.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceInstructEmbeddings
from langchain_experimental.text_splitter import SemanticChunker
from langchain.document_loaders import DirectoryLoader
from langchain.retrievers.multi_query import MultiQueryRetriever
from utils import PDFReadTool, AdvancedScrapeTool


llm = ChatOllama(model="llama3:8b", base_url="http://localhost:11434")
embedding_function = HuggingFaceInstructEmbeddings(
    model_name="nomic-embed-text",
    model_kwargs={"device": "cpu"}
)


vectordb = Chroma(
    persist_directory="./chroma_db", 
    embedding_function=embedding_function
)


def initialize_vector_store():
    if vectordb._collection.count() == 0:
        print("Knowledge base is empty. Initializing with Semantic Chunking...")
        loader = DirectoryLoader('./knowledge_base', glob="**/*.md")
        docs = loader.load()
        semantic_chunker = SemanticChunker(embedding_function)
        splits = semantic_chunker.create_documents([doc.page_content for doc in docs])
        
        vectordb.add_documents(documents=splits, embedding=embedding_function)
        print("Knowledge base initialized.")

initialize_vector_store()

retriever = MultiQueryRetriever.from_llm(
    retriever=vectordb.as_retriever(), 
    llm=llm
)

retriever_tool = Tool(
    name="Company Knowledge Base Search",
    description="Searches the company's knowledge base for relevant information about its products, infrastructure, and processes. Use this to answer questions about how regulations might impact the company.",
    func=retriever.invoke
)

# --- AGENTS ---

regulator_interpreter = Agent(
    role="Regulatory Interpreter",
    goal="Scan regulatory documents from URLs or PDFs and interpret their core meaning.",
    backstory="You are an expert legal analyst. Your strength is reading dense legal documents and extracting key points.",
    llm=llm,
    tools=[AdvancedScrapeTool(), PDFReadTool()],
    allow_delegation=False,
    verbose=True
)

impact_analyst = Agent(
    role="Business Impact Analyst",
    goal="Analyze how regulatory changes affect the company's products, operations, and technical infrastructure.",
    backstory=(
        "You are a seasoned business analyst at FlexiPay India. You have deep knowledge of all products and systems. "
        "Your primary skill is using the 'Company Knowledge Base Search' tool to ask detailed questions and find precise information "
        "to connect regulatory changes to specific business operations."
    ),
    llm=llm,
    tools=[retriever_tool], # Assign the new tool
    allow_delegation=False,
    verbose=True
)

strategy_advisor = Agent(
    role="Strategy and Compliance Advisor for Indian Fintech",
    goal="Create a prioritized, actionable plan with clear departmental owners.",
    backstory=(
        "You are a seasoned compliance strategist who previously worked at a major Indian digital payments company. "
        "You are an expert at translating dense regulatory language into concrete operational and engineering tasks. "
        "Your plans are always practical, clear, and include estimated timelines. "
        "**Always structure your final output using Markdown with these sections: 1. Executive Summary, 2. Key Risks, 3. Action Plan by Department.**"
    ),
    llm=llm,
    allow_delegation=False,
    verbose=True
) 


verification_agent = Agent(
    role="Verification Specialist",
    goal="Verify the final strategic plan against the initial regulatory summary for consistency and accuracy.",
    backstory=(
        "You are a meticulous fact-checker. Your job is to ensure that every recommendation in the final report "
        "is directly supported by the initial interpretation of the regulation. You flag any inconsistencies or unsupported claims."
    ),
    llm=llm,
    allow_delegation=False,
    verbose=True
)

# --- TASKS ---

interpret_task = Task(
    description=(
        "Read the content of the provided source: '{source}'. "
        "If it's a URL, first inspect the page to find the main content's CSS selector (e.g., 'div#content', 'article.main'). "
        "Then, use the advanced scraper with the URL and the selector to get clean text. "
        "If it's a local file path, use the PDF reader. "
        "Finally, provide a concise summary of the key regulatory changes."
    ),
    expected_output="A bullet-point summary of core changes from the clean, extracted text.",
    agent=regulator_interpreter
)

impact_task = Task(
    description=(
        "Using the summary of regulatory changes, analyze the specific impact on FlexiPay India. "
        "You MUST use the 'Company Knowledge Base Search' tool to ask multiple, specific questions about the company's products and processes. "
        "For example, ask 'What is our current KYC process for the FlexiUPI app?' or 'What is our data storage policy?'. "
        "Synthesize the answers you find to create a detailed analysis of the impact."
    ),
    expected_output="A detailed analysis of how each change affects specific parts of the company, citing the information retrieved from the knowledge base.",
    agent=impact_analyst,
    context=[interpret_task]
)

strategy_task = Task(
    description=(
        "Based on the impact analysis, create a high-level, actionable strategic plan. "
        "Outline the recommended next steps for key departments (e.g., Engineering, Operations, Legal). "
        "The plan should be clear, concise, and prioritized."
    ),
    expected_output="A final report containing a prioritized list of actions for different departments to ensure compliance.",
    agent=strategy_advisor,
    context=[impact_task]
)

verification_task = Task(
    description=(
        "Review the entire analysis. Compare the initial regulatory summary from the first step with the final strategic plan. "
        "Ensure the strategic advice is logically derived from the regulatory changes. "
        "If everything is consistent, approve the report. If there are inconsistencies, point them out and provide a final corrected version."
    ),
    expected_output="A final, verified report. If inconsistencies were found, the report must include a section detailing the corrections made.",
    agent=verification_agent,
    context=[interpret_task, impact_task, strategy_task]
)


# --- CREW ---

finscout_crew = Crew(
    agents=[regulator_interpreter, impact_analyst, strategy_advisor, verification_agent],
    tasks=[interpret_task, impact_task, strategy_task, verification_task],
    process=Process.sequential,
    verbose=2
)

def run_crew(source: str):
    result = finscout_crew.kickoff(inputs={'source': source})
    return result