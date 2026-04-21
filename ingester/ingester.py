import os
import time
import requests
from typing import Dict
from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.exception import AppwriteException
from appwrite.query import Query
import chromadb
from chromadb.config import Settings
from sec_filing_parser import parse_sec_filing

# Load environment variables
load_dotenv()

# Get the project root directory (parent of ingester folder)
# In Docker: file is at /app/ingester.py, so we use /app/chroma_db
# Locally: file is at /path/to/secrag/ingester/ingester.py, so we use /path/to/secrag/chroma_db
ingester_dir = os.path.dirname(os.path.abspath(__file__))
# Check if we're in Docker (file is directly in /app/) or locally (file is in ingester/ subfolder)
if os.path.basename(ingester_dir) == 'ingester':
    # Local development: go up one level from ingester/
    project_root = os.path.dirname(ingester_dir)
else:
    # Docker: file is already in /app/, so use /app directly
    project_root = ingester_dir

# Create persistent ChromaDB database in project root (outside ingester folder)
chroma_db_path = os.path.join(project_root, 'chroma_db')
os.makedirs(chroma_db_path, exist_ok=True)
print(f"📁 ChromaDB path: {chroma_db_path}")

# Initialize ChromaDB client with persistent storage
chroma_client = chromadb.PersistentClient(
    path=chroma_db_path,
    settings=Settings(
        anonymized_telemetry=False,
        allow_reset=True
    )
)

# Create ChromaDB collections
sec_text_collection = chroma_client.get_or_create_collection(name="sec_text")
sec_facts_collection = chroma_client.get_or_create_collection(name="sec_facts")

# SEC request headers reused across runs
SEC_REQUEST_HEADERS = {
    'User-Agent': 'Company Name contact@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

# Initialize Appwrite client
appwrite_client = Client()
appwrite_client.set_endpoint(os.getenv('APPWRITE_API_ENDPOINT', 'https://cloud.appwrite.io/v1'))
appwrite_client.set_project(os.getenv('APPWRITE_PROJECT_ID', ''))
appwrite_client.set_key(os.getenv('APPWRITE_KEY', ''))

databases = Databases(appwrite_client)


def create_temporal_context_from_metadata(metadata: Dict) -> str:
    """
    Create a temporal context string from metadata to prepend to chunks.
    This helps embeddings capture temporal information like dates and quarters,
    as well as company information.
    
    Args:
        metadata: Metadata dictionary containing report_date, form, company info, etc.
    
    Returns:
        Temporal context string to prepend to chunks
    """
    context_parts = []
    
    # Company information first (for better semantic matching)
    company_name = metadata.get('company_name', '')
    if company_name:
        context_parts.append(f"Company: {company_name}")
    
    symbol = metadata.get('symbol', '')
    if symbol:
        context_parts.append(f"Symbol: {symbol}")
    
    sector = metadata.get('sector', '')
    if sector:
        context_parts.append(f"Sector: {sector}")
    
    sub_sector = metadata.get('sub_sector', '')
    if sub_sector:
        context_parts.append(f"Sub Sector: {sub_sector}")
    
    # Temporal information
    report_date = metadata.get('report_date', '')
    if report_date:
        try:
            from datetime import datetime
            # Parse the date
            date_obj = datetime.strptime(str(report_date).split('T')[0], '%Y-%m-%d')
            year = date_obj.year
            month = date_obj.month
            quarter = (month - 1) // 3 + 1
            
            # Add multiple date formats for better matching
            context_parts.append(f"Report Date: {str(report_date).split('T')[0]}")
            context_parts.append(f"Quarter: Q{quarter} {year}")
            context_parts.append(f"Period: {year} Q{quarter}")
            context_parts.append(f"Year: {year}")
            
            # Add month name for additional context
            month_name = date_obj.strftime('%B')
            context_parts.append(f"{month_name} {year}")
        except Exception:
            # If parsing fails, just add the raw date
            context_parts.append(f"Report Date: {report_date}")
    
    form = metadata.get('form', '')
    if form:
        context_parts.append(f"Form: {form}")
    
    if context_parts:
        return " | ".join(context_parts) + "\n\n"
    return ""


def ingest_document(doc: Dict, headers: Dict, log_temporal_context: bool = False,
                    doc_idx: int | None = None, total_docs: int | None = None) -> tuple[int, int, bool]:
    """
    Ingest a single Appwrite document into ChromaDB.
    Uses sec_parser to extract text and table chunks from SEC filings.

    Returns:
        text_chunk_count, table_chunk_count, success_flag
    """
    metadata = {
        'cik': doc.get('cik', ''),
        'symbol': doc.get('symbol', ''),
        'sector': doc.get('sector', ''),
        'sub_sector': doc.get('sub_sector', ''),
        'company_name': doc.get('company_name', ''),
        'form': doc.get('form', ''),
        'file_name': doc.get('file_name', ''),
        'is_xbrl': doc.get('is_xbrl', False),
        'ix_inline_xbrl': doc.get('ix_inline_xbrl', False),
        'file_url': doc.get('file_url', ''),
        'report_date': doc.get('report_date', ''),
        'vector_ingested': doc.get('vector_ingested', False),
        'appwrite_id': doc.get('$id', '')
    }

    file_url = metadata.get('file_url')
    label_prefix = f"document #{doc_idx}/{total_docs}" if doc_idx and total_docs else "document"
    print(f"\n  📄 Processing {label_prefix}: {metadata.get('file_name', 'N/A')}")

    if not file_url:
        print("    ⚠️  Missing file_url, skipping")
        return 0, 0, False

    # Fetch HTML content
    try:
        response = requests.get(file_url, headers=headers, timeout=60)
        response.raise_for_status()
        html_content = response.text
    except Exception as e:
        print(f"    ❌ Error fetching HTML: {e}")
        return 0, 0, False

    temporal_context = create_temporal_context_from_metadata(metadata)
    if log_temporal_context:
        print(f"    📄 Temporal context: {temporal_context}")

    total_text_chunks = 0
    total_facts_chunks = 0
    text_success = False
    facts_success = False

    # Process chunks using new sec_parser
    try:
        # Get form type from Appwrite document (defaults to 10-Q if not specified)
        form_type = metadata.get('form', '10-Q')
        if not form_type:
            form_type = '10-Q'  # Default fallback
        print(f"    📋 Parsing as form type: {form_type}")
        chunks = parse_sec_filing(html_content, form_type=form_type, url=file_url)
        
        if chunks:
            # Separate text and table chunks
            text_chunks = [c for c in chunks if c['type'] == 'text']
            table_chunks = [c for c in chunks if c['type'] == 'table']
            
            # Process text chunks
            if text_chunks:
                texts = [temporal_context + chunk['content'] for chunk in text_chunks]
                # Merge chunk metadata with document metadata
                metadatas = []
                for chunk in text_chunks:
                    chunk_meta = chunk.get('metadata', {}).copy()
                    chunk_meta.update(metadata)
                    chunk_meta['chunk_type'] = 'text'
                    chunk_meta['chunk_context'] = chunk.get('context', '')
                    chunk_meta['chunk_tokens'] = chunk.get('tokens', 0)
                    metadatas.append(chunk_meta)
                
                ids = [f"{metadata['appwrite_id']}_text_{i}" for i in range(len(text_chunks))]

                sec_text_collection.add(
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                total_text_chunks = len(text_chunks)
                text_success = True
                print(f"    ✅ Added {len(text_chunks)} text chunks to sec_text collection")
            
            # Process table chunks (store in sec_facts collection for now)
            if table_chunks:
                texts = [temporal_context + chunk['content'] for chunk in table_chunks]
                # Merge chunk metadata with document metadata
                metadatas = []
                for chunk in table_chunks:
                    chunk_meta = chunk.get('metadata', {}).copy()
                    chunk_meta.update(metadata)
                    chunk_meta['chunk_type'] = 'table'
                    chunk_meta['chunk_context'] = chunk.get('context', '')
                    chunk_meta['chunk_tokens'] = chunk.get('tokens', 0)
                    chunk_meta['content_type'] = chunk.get('content_type', 'html')
                    metadatas.append(chunk_meta)
                
                ids = [f"{metadata['appwrite_id']}_table_{i}" for i in range(len(table_chunks))]

                sec_facts_collection.add(
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                total_facts_chunks = len(table_chunks)
                facts_success = True
                print(f"    ✅ Added {len(table_chunks)} table chunks to sec_facts collection")
            
            if not text_chunks and not table_chunks:
                print("    ⚠️  No chunks generated")
        else:
            print("    ⚠️  No chunks generated")
    except Exception as e:
        print(f"    ❌ Error processing chunks: {e}")
        import traceback
        traceback.print_exc()

    # Success if either text or table chunks were ingested
    return total_text_chunks, total_facts_chunks, (text_success or facts_success)


def ingest_pending_documents(batch_size: int = 100) -> None:
    """
    Fetch batches of documents where vector_ingested is false and ingest them.
    Continues until no pending documents are left.
    """
    db_id = os.getenv('APPWRITE_DB_ID_DOCS')
    collection_id = os.getenv('APPWRITE_DOCS_DB_COLLECTIONS_FILES')

    if not db_id:
        print("❌ APPWRITE_DB_ID_DOCS environment variable not set")
        return

    if not collection_id:
        print("❌ APPWRITE_DOCS_DB_COLLECTIONS_FILES environment variable not set")
        return

    print(f"\n🚀 Starting ingestion for pending documents (batch size={batch_size})")
    total_text_chunks = 0
    total_facts_chunks = 0
    total_documents_ingested = 0
    batches_processed = 0

    while True:
        try:
            response = databases.list_documents(
                database_id=db_id,
                collection_id=collection_id,
                queries=[
                    Query.equal('vector_ingested', False),
                    Query.limit(batch_size)
                ]
            )
        except AppwriteException as e:
            print(f"❌ Appwrite error while listing documents: {e.message}")
            break
        except Exception as e:
            print(f"❌ Error listing documents: {e}")
            import traceback
            traceback.print_exc()
            break

        documents = response.get('documents', [])
        if not documents:
            print("✅ No pending documents left to ingest.")
            break

        batches_processed += 1
        print(f"\n📦 Processing batch #{batches_processed} ({len(documents)} documents)")

        progress_made = False
        for idx, doc in enumerate(documents, 1):
            try:
                text_chunks, facts_chunks, success = ingest_document(
                    doc,
                    headers=SEC_REQUEST_HEADERS,
                    log_temporal_context=False,
                    doc_idx=idx,
                    total_docs=len(documents)
                )

                total_text_chunks += text_chunks
                total_facts_chunks += facts_chunks

                if success:
                    try:
                        databases.update_document(
                            database_id=db_id,
                            collection_id=collection_id,
                            document_id=doc.get('$id'),
                            data={'vector_ingested': True}
                        )
                        progress_made = True
                        total_documents_ingested += 1
                        print(f"    ✅ Marked document {doc.get('$id')} as ingested")
                    except Exception as e:
                        print(f"    ❌ Failed to update vector_ingested flag: {e}")
                else:
                    print("    ⚠️  Skipping flag update because ingestion was incomplete")
            except Exception as e:
                print(f"  ❌ Error processing document {doc.get('$id')}: {e}")
                import traceback
                traceback.print_exc()
                continue

        if not progress_made:
            print("⚠️  No documents were successfully ingested in this batch; stopping to avoid retry loop.")
            break

    print("\n" + "=" * 50)
    print(f"✅ Pending ingestion run complete!")
    print(f"   Total text chunks ingested: {total_text_chunks}")
    print(f"   Total table chunks ingested: {total_facts_chunks}")
    print(f"   Total documents marked ingested: {total_documents_ingested}")
    print(f"   Batches processed: {batches_processed}")
    print("=" * 50)


def test_ingest_documents():
    """
    Test function that fetches all rows from the Appwrite database collection
    and ingests them into the ChromaDB database.
    """
    try:
        # Get database and collection IDs from environment variables
        db_id = os.getenv('APPWRITE_DB_ID_DOCS')
        collection_id = os.getenv('APPWRITE_DOCS_DB_COLLECTIONS_FILES')

        if not db_id:
            print("❌ APPWRITE_DB_ID_DOCS environment variable not set")
            return None

        if not collection_id:
            print("❌ APPWRITE_DOCS_DB_COLLECTIONS_FILES environment variable not set")
            return None

        print(f"🔍 Fetching documents with symbol='AAPL' from database: {db_id}")
        print(f"📁 Collection: {collection_id}")
        print("-" * 50)

        # Fetch all documents with symbol = 'AAPL' (with pagination)
        all_documents = []
        cursor = None
        limit = 100  # Maximum limit per request
        
        try:
            while True:
                # Build query list
                query_list = [Query.equal('symbol', 'AAPL'), Query.limit(limit)]
                
                # Add cursor for pagination if we have one
                if cursor:
                    query_list.append(Query.cursor_after(cursor))
                
                # Fetch documents
                response = databases.list_documents(
                    database_id=db_id,
                    collection_id=collection_id,
                    queries=query_list
                )

                # Response is a dictionary with 'documents' and 'total' keys
                documents = response.get('documents', [])
                total = response.get('total', 0)
                
                if not documents:
                    break
                
                all_documents.extend(documents)
                
                # Show progress
                if total > 0:
                    print(f"  Fetched {len(documents)} documents (total so far: {len(all_documents)}/{total})")
                else:
                    print(f"  Fetched {len(documents)} documents (total so far: {len(all_documents)})")
                
                # Check if we've fetched all documents
                if total > 0 and len(all_documents) >= total:
                    break
                
                # If we got fewer documents than the limit, we're done
                if len(documents) < limit:
                    break
                
                # Use the last document ID as cursor for next page
                cursor = documents[-1].get('$id')
                if not cursor:
                    break

        except AppwriteException as e:
            print(f"❌ Appwrite error: {e.message}")
            return None
        except Exception as e:
            print(f"❌ Error fetching documents: {e}")
            import traceback
            traceback.print_exc()
            return None

        print(f"\n✅ Total documents fetched: {len(all_documents)}")
        print("=" * 50)

        # Log only one sample document to show column structure
        sample_logged = False
        if all_documents:
            print("\n📄 Sample Document (showing column structure):")
            print("-" * 50)
            for key, value in all_documents[0].items():
                if key.startswith('$'):
                    print(f"  {key}: {value}")
                else:
                    if isinstance(value, str) and len(value) > 200:
                        value_preview = value[:200] + "... (truncated)"
                        print(f"  {key}: {value_preview}")
                    else:
                        print(f"  {key}: {value}")
            print("-" * 50)

        # Process all documents and ingest chunks
        print(f"\n🔄 Processing and ingesting chunks for {len(all_documents)} documents...")
        print("=" * 50)

        total_text_chunks = 0
        total_facts_chunks = 0

        for idx, doc in enumerate(all_documents, 1):
            text_chunks, facts_chunks, _ = ingest_document(
                doc,
                headers=SEC_REQUEST_HEADERS,
                log_temporal_context=True,
                doc_idx=idx,
                total_docs=len(all_documents)
            )
            total_text_chunks += text_chunks
            total_facts_chunks += facts_chunks

        print("\n" + "=" * 50)
        print(f"✅ Ingestion complete!")
        print(f"   Total text chunks ingested: {total_text_chunks}")
        print(f"   Total table chunks ingested: {total_facts_chunks}")
        print(f"   Total documents processed: {len(all_documents)}")
        return all_documents

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Run pending ingestion once, then repeat daily
    # test_ingest_documents()
    while True:
        ingest_pending_documents(batch_size=100)
        print("⏲️  Sleeping for 24 hours before next ingestion run...")
        try:
            time.sleep(24 * 60 * 60)
        except KeyboardInterrupt:
            print("🛑 Ingestion loop interrupted by user, exiting.")
            break

