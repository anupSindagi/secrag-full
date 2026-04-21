import os
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_chroma import Chroma

# Load environment variables
load_dotenv()

# Get the project root directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Create persistent ChromaDB database path
chroma_db_path = os.path.join(project_root, 'chroma_db')
os.makedirs(chroma_db_path, exist_ok=True)

# Initialize ChromaDB client with persistent storage
chroma_client = chromadb.PersistentClient(
    path=chroma_db_path,
    settings=Settings(
        anonymized_telemetry=False,
        allow_reset=True
    )
)

# Create vector stores for both collections (using ChromaDB's default embedding)
sec_text_vectorstore = Chroma(
    client=chroma_client,
    collection_name="sec_text"
)

sec_facts_vectorstore = Chroma(
    client=chroma_client,
    collection_name="sec_facts"
)

# Create retrieval tools
sec_text_retriever = sec_text_vectorstore.as_retriever(search_kwargs={"k": 10})
sec_facts_retriever = sec_facts_vectorstore.as_retriever(search_kwargs={"k": 10})

@tool
def sec_text_retrieval(query: str) -> str:
    """Retrieve relevant SEC text documents from the sec_text collection.
    
    Use this tool to search for textual information from SEC filings,
    such as management discussions, risk factors, or narrative sections.
    
    Args:
        query: The search query to find relevant SEC text documents
        
    Returns:
        A string containing the retrieved document chunks
    """
    docs = sec_text_retriever.invoke(query)
    print("sec_text_retrieval")
    print(query)
    # print("-" * 100)
    # for id, doc in enumerate(docs):
    #     print(f"Document {id}:")
    #     print(doc.page_content)
    #     print("-" * 100)
    return "\n\n".join([doc.page_content for doc in docs])

@tool
def sec_fact_retrieval(query: str) -> str:
    """Retrieve relevant SEC facts and tables from the sec_facts collection.
    
    Use this tool to search for factual data, tables, and structured
    information from SEC filings, such as financial metrics, balance sheets,
    or income statements.
    
    Args:
        query: The search query to find relevant SEC facts and tables
        
    Returns:
        A string containing the retrieved fact chunks
    """
    docs = sec_facts_retriever.invoke(query)
    print("sec_fact_retrieval")
    print(query)
    # print("-" * 100)
    # for id, doc in enumerate(docs):
    #     print(f"Document {id}:")
    #     print(doc.page_content)
    #     print("-" * 100)
    return "\n\n".join([doc.page_content for doc in docs])

# Define system prompt
SYSTEM_PROMPT = """You are a helpful assistant that can answer questions about SEC filings.

You have access to two retrieval tools:
1. sec_text_retrieval - Use this for narrative content, management discussions, risk factors, and textual information from SEC filings.
2. sec_fact_retrieval - Use this for factual data, tables, structured information, financial metrics, balance sheets, income statements, and numerical data.

Think step-by-step:
- Analyze the user's question to determine which tool(s) would be most appropriate
- Use sec_text_retrieval for questions about company strategy, risks, management discussion, or narrative content
- Use sec_fact_retrieval for questions about financial numbers, metrics, tables, or structured data
- You can use both tools if needed to provide a comprehensive answer
- Provide clear, accurate answers based on the retrieved information
- If you can't find the information, say "I'm sorry, I can't find the information you're looking for."
- In the final response, add source URL of the SEC filing if you can find it. You will find the URL in the metadata of the retrieved documents.
"""

# Create tools list
tools = [sec_text_retrieval, sec_fact_retrieval]

# Create agent using LangChain V1 API
agent = create_agent(
    model="openai:gpt-5-mini",
    tools=tools,
    system_prompt=SYSTEM_PROMPT
)

def run_agent(query: str):
    """Run the agent with a query."""
    # Invoke agent with messages format
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    
    # Extract the final response from messages
    if "messages" in result and result["messages"]:
        # Get the last message which should be the AI's final response
        last_message = result["messages"][-1]
        if hasattr(last_message, "content"):
            return last_message.content
        elif isinstance(last_message, dict) and "content" in last_message:
            return last_message["content"]
    
    return str(result)

if __name__ == "__main__":
    # Example usage
    query = "what something interesting that was filed in last SEC filing 10-K by Apple?"
    print(f"Query: {query}\n")
    response = run_agent(query)
    print(f"\nResponse: {response}")

