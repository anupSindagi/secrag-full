import csv
import requests
import time
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.exception import AppwriteException
import schedule

# Load environment variables
load_dotenv()

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_file = os.getenv('CSV_FILE', 'sp500.csv')
csv_path = os.path.join(script_dir, csv_file)

# Get recent SEC submissions for each company
def format_cik(cik):
    """Format CIK as 10-digit string with leading zeros"""
    return str(cik).zfill(10)


def load_sp500_data(csv_path):
    """Load S&P 500 data from CSV file"""
    sp500_data = {}
    with open(csv_path, 'r') as file:
        csv_reader = csv.DictReader(file)
        column_names = csv_reader.fieldnames
        for col in column_names:
            sp500_data[col] = []
        
        for row in csv_reader:
            for col in column_names:
                sp500_data[col].append(row[col])
    return sp500_data


def get_sec_submissions(cik):
    """Fetch recent submissions from SEC EDGAR API"""
    cik_formatted = format_cik(cik)
    url = f"https://data.sec.gov/submissions/CIK{cik_formatted}.json"
    
    headers = {
        'User-Agent': 'Company Name contact@example.com',  # SEC requires User-Agent
        'Accept-Encoding': 'gzip, deflate',
        'Host': 'data.sec.gov'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching submissions for CIK {cik}: {e}")
        return None


def fetch_sec_submissions(sp500_data):
    """Fetch SEC submissions for all companies"""
    sec_submissions = {}
    print(f"Fetching SEC submissions for {len(sp500_data['CIK'])} companies...")
    for i, cik in enumerate(sp500_data['CIK']):
        symbol = sp500_data['Symbol'][i] if i < len(sp500_data['Symbol']) else None
        print(f"Processing {symbol} (CIK: {cik})...")
        
        submissions_data = get_sec_submissions(cik)
        if submissions_data:
            sec_submissions[cik] = submissions_data
        
        # Rate limiting: SEC requires no more than 10 requests per second
        time.sleep(0.1)
    
    print(f"Successfully fetched submissions for {len(sec_submissions)} companies")
    return sec_submissions

def check_and_insert_document(databases, database_id, collection_id, accession_no_clean, cik, cik_index, form, file_name, is_xbrl_val, is_inline_xbrl_val, file_url, report_date, sp500_data):
    """Check if document exists, if not insert it"""
    try:
        # Try to get the document to check if it exists
        databases.get_document(
            database_id=database_id,
            collection_id=collection_id,
            document_id=accession_no_clean
        )
        print(f"  Document {accession_no_clean} already exists, skipping...")
        return False
    except AppwriteException as e:
        if e.code == 404:
            # Document doesn't exist, create it
            try:
                # Get company data from sp500_data
                cik_value = int(sp500_data['CIK'][cik_index]) if cik_index is not None else None
                symbol = sp500_data['Symbol'][cik_index] if cik_index is not None and cik_index < len(sp500_data['Symbol']) else None
                sector = sp500_data['GICS Sector'][cik_index] if cik_index is not None and cik_index < len(sp500_data.get('GICS Sector', [])) else None
                sub_sector = sp500_data['GICS Sub-Industry'][cik_index] if cik_index is not None and cik_index < len(sp500_data.get('GICS Sub-Industry', [])) else None
                company_name = sp500_data['Security'][cik_index] if cik_index is not None and cik_index < len(sp500_data['Security']) else None
                
                document_data = {
                    'cik': cik_value,
                    'symbol': symbol,
                    'sector': sector,
                    'sub_sector': sub_sector,
                    'company_name': company_name,
                    'form': form,
                    'file_name': file_name,
                    'report_date': report_date,
                    'is_xbrl': is_xbrl_val,
                    'ix_inline_xbrl': is_inline_xbrl_val,
                    'file_url': file_url
                }
                
                databases.create_document(
                    database_id=database_id,
                    collection_id=collection_id,
                    document_id=accession_no_clean,
                    data=document_data
                )
                print(f"  ✓ Inserted document {accession_no_clean} for {symbol}")
                return True
            except Exception as create_error:
                print(f"  ✗ Error creating document {accession_no_clean}: {create_error}")
                return False
        else:
            print(f"  ✗ Error checking document {accession_no_clean}: {e}")
            return False

def process_filings(sec_submissions, sp500_data, databases, database_id, collection_id):
    """Process and insert filings into Appwrite"""
    target_forms = ['10-K', '10-Q']
    
    print("\nProcessing SEC filings (10-K, 10-Q, 8-K only) and inserting into Appwrite...")
    print("=" * 80)
    
    total_inserted = 0
    for cik, data in sec_submissions.items():
        if 'filings' not in data or 'recent' not in data['filings']:
            continue
        
        filings = data['filings']['recent']
        forms = filings.get('form', [])
        accession_numbers = filings.get('accessionNumber', [])
        primary_documents = filings.get('primaryDocument', [])
        report_dates = filings.get('reportDate', [])
        is_xbrl = filings.get('isXBRL', [])
        is_inline_xbrl = filings.get('isInlineXBRL', [])
        
        # Find symbol for this CIK
        cik_index = None
        for i, cik_val in enumerate(sp500_data['CIK']):
            if str(cik_val) == str(cik):
                cik_index = i
                break
        
        symbol = sp500_data['Symbol'][cik_index] if cik_index is not None else "Unknown"
        
        filtered_count = 0
        inserted_count = 0
        for i, form in enumerate(forms):
            if form in target_forms:
                filtered_count += 1
                accession_no_clean = accession_numbers[i].replace('-', '') if i < len(accession_numbers) else ''
                
                if not accession_no_clean:
                    continue
                
                file_name = primary_documents[i] if i < len(primary_documents) else ''
                report_date = report_dates[i] if i < len(report_dates) else ''
                is_xbrl_value = bool(is_xbrl[i]) if i < len(is_xbrl) else False
                is_inline_xbrl_value = bool(is_inline_xbrl[i]) if i < len(is_inline_xbrl) else False
                
                # Get CIK for URL - use the numeric CIK value (remove leading zeros)
                cik_for_url = str(cik).lstrip('0') or '0'
                file_url = f"https://www.sec.gov/Archives/edgar/data/{cik_for_url}/{accession_no_clean}/{file_name}"
                
                print(f"\nProcessing: {symbol} - {form} - {accession_no_clean}")
                if check_and_insert_document(databases, database_id, collection_id, accession_no_clean, cik, cik_index, form, file_name, is_xbrl_value, is_inline_xbrl_value, file_url, report_date, sp500_data):
                    inserted_count += 1
                    total_inserted += 1
        
        if filtered_count == 0:
            print(f"\n{symbol} (CIK: {cik}): No matching filings found")
    
    print("\n" + "=" * 80)
    print(f"Processing complete! Total documents inserted: {total_inserted}")
    return total_inserted


def run_scanner():
    """Main function to run the SEC scanner"""
    try:
        print(f"\n{'='*80}")
        print(f"SEC Scanner started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
        
        # Load S&P 500 data
        if not os.path.exists(csv_path):
            print(f"Error: CSV file not found at {csv_path}")
            return
        
        sp500_data = load_sp500_data(csv_path)
        print(f"Loaded {len(sp500_data['CIK'])} companies from {csv_file}")
        
        # Initialize Appwrite client
        client = Client()
        client.set_endpoint(os.getenv('APPWRITE_API_ENDPOINT', 'https://cloud.appwrite.io/v1'))
        client.set_project(os.getenv('APPWRITE_PROJECT_ID', ''))
        client.set_key(os.getenv('APPWRITE_KEY', ''))
        
        database_id = os.getenv('APPWRITE_DB_ID_DOCS', '')
        collection_id = os.getenv('APPWRITE_DOCS_DB_COLLECTIONS_FILES', '')
        
        databases = Databases(client)
        
        # Fetch SEC submissions
        sec_submissions = fetch_sec_submissions(sp500_data)
        
        # Process and insert filings
        process_filings(sec_submissions, sp500_data, databases, database_id, collection_id)
        
        print(f"\n{'='*80}")
        print(f"SEC Scanner completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\nError in scanner execution: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Check if we should run once or schedule daily
    run_mode = os.getenv('RUN_MODE', 'scheduled').lower()
    
    if run_mode == 'once':
        # Run once and exit
        run_scanner()
    else:
        # Schedule to run daily at a specific time (default: 2 AM)
        run_time = os.getenv('RUN_TIME', '02:00')
        print(f"Scheduling scanner to run daily at {run_time}")
        schedule.every().day.at(run_time).do(run_scanner)
        
        # Also run immediately on startup
        print("Running initial scan...")
        run_scanner()
        
        # Keep the script running and check for scheduled tasks
        print(f"\nScanner running in scheduled mode. Next run: {schedule.next_run()}")
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute




