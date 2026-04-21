import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def delete_all_files():
    """Delete all documents from the files collection using REST API bulk delete while preserving the collection structure."""
    db_id = os.getenv('APPWRITE_DB_ID_DOCS')
    collection_id = os.getenv('APPWRITE_DOCS_DB_COLLECTIONS_FILES')
    endpoint = os.getenv('APPWRITE_API_ENDPOINT', 'https://cloud.appwrite.io/v1')
    project_id = os.getenv('APPWRITE_PROJECT_ID', '')
    api_key = os.getenv('APPWRITE_KEY', '')

    if not db_id:
        print("❌ APPWRITE_DB_ID_DOCS environment variable not set")
        return

    if not collection_id:
        print("❌ APPWRITE_DOCS_DB_COLLECTIONS_FILES environment variable not set")
        return

    if not project_id:
        print("❌ APPWRITE_PROJECT_ID environment variable not set")
        return

    if not api_key:
        print("❌ APPWRITE_KEY environment variable not set")
        return

    print(f"🗑️  Deleting all documents from files collection using bulk delete API...")
    
    try:
        # Use REST API directly to delete all documents
        # DELETE /v1/databases/{databaseId}/collections/{collectionId}/documents
        url = f"{endpoint}/databases/{db_id}/collections/{collection_id}/documents"
        
        headers = {
            'X-Appwrite-Project': project_id,
            'X-Appwrite-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        # Make the DELETE request - if no queries specified, should delete all
        response = requests.delete(url, headers=headers, json={})
        
        if response.status_code == 200 or response.status_code == 204:
            print(f"✅ Successfully deleted all documents from files collection")
            print(f"✅ Collection structure is intact (only documents were deleted)")
        else:
            print(f"❌ API Error: Status code {response.status_code}")
            print(f"❌ Response: {response.text}")
            
            # If the above doesn't work, try with an empty queries array
            print(f"\n🔄 Trying alternative approach with empty queries...")
            response = requests.delete(url, headers=headers, json={"queries": []})
            
            if response.status_code == 200 or response.status_code == 204:
                print(f"✅ Successfully deleted all documents from files collection")
                print(f"✅ Collection structure is intact (only documents were deleted)")
            else:
                print(f"❌ Alternative approach failed: Status code {response.status_code}")
                print(f"❌ Response: {response.text}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    delete_all_files()

