# SEC Scanner

A Python application that scans SEC EDGAR filings for S&P 500 companies and stores them in Appwrite.

## Features

- Fetches recent SEC filings (10-K, 10-Q, 8-K) for all S&P 500 companies
- Filters and stores filings in Appwrite database
- Runs daily on a schedule
- Dockerized for easy deployment

## Environment Variables

Create a `.env` file with the following variables:

```
APPWRITE_API_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_KEY=your_api_key
APPWRITE_DB_ID_DOCS=your_database_id
APPWRITE_DOCS_DB_COLLECTIONS_FILES=your_collection_id
CSV_FILE=sp500.csv
RUN_MODE=scheduled
RUN_TIME=02:00
```

### Environment Variable Descriptions

- `APPWRITE_API_ENDPOINT`: Your Appwrite API endpoint
- `APPWRITE_PROJECT_ID`: Your Appwrite project ID
- `APPWRITE_KEY`: Your Appwrite API key
- `APPWRITE_DB_ID_DOCS`: Your Appwrite database ID
- `APPWRITE_DOCS_DB_COLLECTIONS_FILES`: Your Appwrite collection ID
- `CSV_FILE`: Name of the CSV file to use (default: `sp500.csv`)
- `RUN_MODE`: Either `scheduled` (runs daily) or `once` (runs once and exits) - default: `scheduled`
- `RUN_TIME`: Time to run the scanner daily (HH:MM format) - default: `02:00`

## Running Locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file with your configuration

3. Run the scanner:
```bash
python scanner.py
```

## Running with Docker

### Build the image:
```bash
docker build -t sec-scanner .
```

### Run the container:
```bash
docker run -d \
  --name sec-scanner \
  --env-file .env \
  --restart unless-stopped \
  sec-scanner
```

### View logs:
```bash
docker logs -f sec-scanner
```

## Schedule

When `RUN_MODE=scheduled` (default), the scanner will:
- Run immediately on startup
- Then run daily at the time specified in `RUN_TIME` (default: 2:00 AM)

To run once and exit, set `RUN_MODE=once`

