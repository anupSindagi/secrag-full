import os
import chromadb
from chromadb.config import Settings

# Get the project root directory (parent of current directory)
project_root = os.path.dirname(os.path.abspath(__file__))

# Create persistent ChromaDB database path (same as ingester)
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

# Get collections
sec_text_collection = chroma_client.get_or_create_collection(name="sec_text")
sec_facts_collection = chroma_client.get_or_create_collection(name="sec_facts")


def run_query(collection, query_text: str, label: str):
    """Run a query against a collection and print top result (200 chars)."""
    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=1
        )
        print(f"\n{label}")
        if results['documents'] and results['documents'][0]:
            doc = results['documents'][0][0]
            metadata = results['metadatas'][0][0]
            snippet = doc

            print(f"  Symbol: {metadata.get('symbol', 'N/A')}")
            print(f"  Company: {metadata.get('company_name', 'N/A')}")
            print(f"  Form: {metadata.get('form', 'N/A')}")
            print(f"  Report Date: {metadata.get('report_date', 'N/A')}")
            if metadata.get('item'):
                print(f"  Item: {metadata.get('item', 'N/A')}")
            if metadata.get('category'):
                print(f"  Category: {metadata.get('category', 'N/A')}")
            if metadata.get('period'):
                print(f"  Period: {metadata.get('period', 'N/A')}")
            print("  Text (200 chars):")
            print(f"    {snippet}")
        else:
            print("  No results found")
        print("✅ Query successful!\n")
    except Exception as e:
        print(f"❌ Error querying {label}: {e}")
        import traceback
        traceback.print_exc()


def test_chromadb_queries():
    """
    Test function to check if ChromaDB queries are working for both collections.
    Using vague queries to test embedding robustness.
    """
    print("=" * 70)
    print("🧪 Testing ChromaDB Queries - Embedding Robustness Test")
    print("=" * 70)
    
    # Check collection counts
    text_count = sec_text_collection.count()
    facts_count = sec_facts_collection.count()
    
    print(f"\n📊 Collection Statistics:")
    print(f"   sec_text collection: {text_count} documents")
    print(f"   sec_facts collection: {facts_count} documents")
    print()
    
    if text_count == 0 and facts_count == 0:
        print("⚠️  No documents found in collections.")
        print("   Run the ingester first to populate the collections.")
        return
    
    queries = [
        ("what was the revenue of microsoft in 2024?", "Test 1: Revenue 2024"),
        ("what is the performance of microsoft sales in q2 2022", "Test 2: Sales performance Q2 2022"),
        ("how much total assets are managed by microsoft in 2021", "Test 3: Total assets 2021"),
        ("what was the revenue of microsoft in 2020 q4", "Test 4: Revenue Q4 2020"),
        ("how microsoft did in 2023 in business?", "Test 5: Business performance 2023"),
    ]

    for query_text, label in queries:
        print("\n" + "-" * 70)
        print(f"🔎 {label}")
        print("-" * 70)
        run_query(sec_text_collection, query_text, f"Text Search - {label}")
        run_query(sec_facts_collection, query_text, f"Facts Search - {label}")

    # Samples
    print("\n" + "-" * 70)
    print("📋 Samples from both collections")
    print("-" * 70)
    try:
        if text_count > 0:
            text_samples = sec_text_collection.get(limit=1)
            print(f"\n📝 sec_text sample (showing {len(text_samples['ids'])}):")
            for i, (doc_id, metadata) in enumerate(zip(text_samples['ids'], text_samples['metadatas']), 1):
                print(f"\n  Sample {i}:")
                print(f"    Symbol: {metadata.get('symbol', 'N/A')}")
                print(f"    Company: {metadata.get('company_name', 'N/A')}")
                print(f"    Form: {metadata.get('form', 'N/A')}")
                print(f"    Item: {metadata.get('item', 'N/A')}")
        
        if facts_count > 0:
            facts_samples = sec_facts_collection.get(limit=1)
            print(f"\n📊 sec_facts sample (showing {len(facts_samples['ids'])}):")
            for i, (doc_id, metadata) in enumerate(zip(facts_samples['ids'], facts_samples['metadatas']), 1):
                print(f"\n  Sample {i}:")
                print(f"    Symbol: {metadata.get('symbol', 'N/A')}")
                print(f"    Company: {metadata.get('company_name', 'N/A')}")
                print(f"    Category: {metadata.get('category', 'N/A')}")
                print(f"    Data Type: {metadata.get('data_type', 'N/A')}")
        
        print("\n✅ Get operation successful!")
    except Exception as e:
        print(f"❌ Error getting samples: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("✅ All tests completed!")
    print("=" * 70)


if __name__ == "__main__":
    test_chromadb_queries()

