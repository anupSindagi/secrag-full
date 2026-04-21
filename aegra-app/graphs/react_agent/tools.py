"""This module provides SEC filing retrieval tools.

It includes two retrieval tools for searching SEC filings:
- sec_text_retrieval: For narrative content, management discussions, risk factors
- sec_fact_retrieval: For factual data, tables, financial metrics, structured information
"""

import os
from collections.abc import Callable
from typing import Any

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.tools import tool

# Get the ChromaDB path
# Priority: 1. Environment variable, 2. /secrag/chroma_db (Docker default), 3. Calculate relative path (local)
_chroma_db_path = os.getenv("CHROMA_DB_PATH")
if not _chroma_db_path:
    # Check if we're in Docker (app runs from /app)
    if os.path.exists("/app"):
        # In Docker, default to /secrag/chroma_db (mounted from host)
        _chroma_db_path = "/secrag/chroma_db"
    else:
        # Local development: go up 3 levels from react_agent -> graphs -> aegra-app -> secrag
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
        _chroma_db_path = os.path.join(project_root, 'chroma_db')

# Create directory if it doesn't exist (with proper error handling)
try:
    os.makedirs(_chroma_db_path, exist_ok=True)
except (PermissionError, OSError) as e:
    # Log the error but continue - ChromaDB will handle the path
    import sys
    print(f"Warning: Could not create ChromaDB directory at {_chroma_db_path}: {e}", file=sys.stderr)

# Lazy initialization of ChromaDB client (using PersistentClient)
_chroma_client = None

def _get_chroma_client():
    """Get or create ChromaDB PersistentClient (lazy initialization)."""
    global _chroma_client
    if _chroma_client is None:
        try:
            _chroma_client = chromadb.PersistentClient(
                path=_chroma_db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        except ValueError as e:
            if "tenant" in str(e).lower():
                # Tenant validation failed - try with explicit tenant/database
                import sys
                print(f"WARNING: Tenant validation failed, trying alternative initialization: {e}", file=sys.stderr)
                # Try creating client with explicit tenant/database
                _chroma_client = chromadb.PersistentClient(
                    path=_chroma_db_path,
                    tenant="default_tenant",
                    database="default_database",
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
            else:
                raise

            # Test connection by trying to list collections
            collections = _chroma_client.list_collections()
            import sys
            print(f"INFO: Connected to ChromaDB at {_chroma_db_path}", file=sys.stderr)
            print(f"INFO: Found {len(collections)} collections: {[c.name for c in collections]}", file=sys.stderr)
            # Check collection counts
            for coll in collections:
                try:
                    count = coll.count()
                    print(f"INFO: Collection '{coll.name}' has {count} documents", file=sys.stderr)
                except Exception as e:
                    print(f"WARNING: Could not get count for collection '{coll.name}': {e}", file=sys.stderr)
        except Exception as e:
            import sys
            print(f"ERROR: Failed to initialize ChromaDB at {_chroma_db_path}", file=sys.stderr)
            print(f"  Error: {e}", file=sys.stderr)
            print(f"  Resolved path: {_chroma_db_path}", file=sys.stderr)
            print(f"  Path exists: {os.path.exists(_chroma_db_path)}", file=sys.stderr)
            if _chroma_db_path:
                parent_dir = os.path.dirname(_chroma_db_path)
                print(f"  Parent directory: {parent_dir}", file=sys.stderr)
                print(f"  Parent exists: {os.path.exists(parent_dir)}", file=sys.stderr)
            print(f"  CHROMA_DB_PATH env var: {os.getenv('CHROMA_DB_PATH')}", file=sys.stderr)
            raise
    return _chroma_client

# Lazy initialization of vector stores
_sec_text_vectorstore = None
_sec_facts_vectorstore = None

def _get_vectorstores():
    """Get or create vector stores (lazy initialization)."""
    global _sec_text_vectorstore, _sec_facts_vectorstore
    if _sec_text_vectorstore is None:
        client = _get_chroma_client()
        _sec_text_vectorstore = Chroma(
            client=client,
            collection_name="sec_text"
        )
        _sec_facts_vectorstore = Chroma(
            client=client,
            collection_name="sec_facts"
        )
    return _sec_text_vectorstore, _sec_facts_vectorstore

# Lazy initialization of retrievers
_sec_text_retriever = None
_sec_facts_retriever = None

def _get_retrievers():
    """Get or create retrievers (lazy initialization)."""
    global _sec_text_retriever, _sec_facts_retriever
    if _sec_text_retriever is None:
        sec_text_vs, sec_facts_vs = _get_vectorstores()
        _sec_text_retriever = sec_text_vs.as_retriever(search_kwargs={"k": 10})
        _sec_facts_retriever = sec_facts_vs.as_retriever(search_kwargs={"k": 20})
    return _sec_text_retriever, _sec_facts_retriever


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
    try:
        sec_text_ret, _ = _get_retrievers()
        docs = sec_text_ret.invoke(query)
        # Debug: log results
        import sys
        print(f"DEBUG: sec_text_retrieval query '{query}' returned {len(docs)} documents", file=sys.stderr)
        if docs:
            print(f"DEBUG: First doc preview: {docs[0].page_content[:200]}...", file=sys.stderr)
        return "\n\n".join([doc.page_content for doc in docs]) if docs else "No relevant text found."
    except Exception as e:
        import sys
        print(f"ERROR: sec_text_retrieval failed: {e}", file=sys.stderr)
        return f"Error retrieving text: {e}"


@tool
def sec_fact_retrieval(query: str) -> str:
    """Retrieve relevant SEC facts and tables from the sec_facts collection.

    Use this tool to search for factual data, tables, and structured
    information from SEC filings, such as financial metrics, balance sheets,
    or income statements.

    This tool returns raw financial data and tables from SEC filings.
    Always examine the returned data carefully for specific financial metrics.

    Args:
        query: The search query to find relevant SEC facts and tables

    Returns:
        A string containing the retrieved fact chunks with financial data
    """
    try:
        _, sec_facts_ret = _get_retrievers()
        docs = sec_facts_ret.invoke(query)
        # Debug: log results
        import sys
        print(f"DEBUG: sec_fact_retrieval query '{query}' returned {len(docs)} documents", file=sys.stderr)
        if docs:
            print(f"DEBUG: First doc preview: {docs[0].page_content[:200]}...", file=sys.stderr)

        if not docs:
            return "No relevant facts found."

        # Format the results with clear headers
        result_parts = []
        result_parts.append(f"SEARCH RESULTS FOR: '{query}'")
        result_parts.append(f"Found {len(docs)} relevant document chunks:")
        result_parts.append("=" * 50)

        for i, doc in enumerate(docs, 1):
            result_parts.append(f"\n--- Document {i} ---")
            result_parts.append(doc.page_content)

        return "\n".join(result_parts)

    except Exception as e:
        import sys
        print(f"ERROR: sec_fact_retrieval failed: {e}", file=sys.stderr)
        return f"Error retrieving facts: {e}"


TOOLS: list[Callable[..., Any]] = [sec_text_retrieval, sec_fact_retrieval]
