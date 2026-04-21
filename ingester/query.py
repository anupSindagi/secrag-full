# log how many rows are there in files collection in appwrite

import os
from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

load_dotenv()

client = Client()
client.set_endpoint(os.getenv('APPWRITE_API_ENDPOINT'))
client.set_project(os.getenv('APPWRITE_PROJECT_ID'))
client.set_key(os.getenv('APPWRITE_KEY'))

databases = Databases(client)

db_id = os.getenv('APPWRITE_DB_ID_DOCS')
collection_id = os.getenv('APPWRITE_DOCS_DB_COLLECTIONS_FILES')

# Count all documents by paginating through them
# Appwrite caps the 'total' field at 5000, so we need to count manually
total_count = 0
cursor = None
limit = 100  # Maximum limit per request

print("Counting all documents...")

while True:
    query_list = [Query.limit(limit)]
    if cursor:
        query_list.append(Query.cursor_after(cursor))
    
    response = databases.list_documents(
        database_id=db_id,
        collection_id=collection_id,
        queries=query_list
    )
    
    documents = response.get('documents', [])
    if not documents:
        break
    
    total_count += len(documents)
    
    # Show progress every 1000 documents
    if total_count % 1000 == 0:
        print(f"  Counted so far: {total_count}")
    
    # Check if we've reached the end
    if len(documents) < limit:
        break
    
    # Get cursor for next page
    cursor = documents[-1].get('$id')
    if not cursor:
        break

print(f"\n✅ Total rows in collection: {total_count}")