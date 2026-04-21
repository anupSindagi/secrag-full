# secrag-dockploy

Isolated Dockploy deployment stack for:
- one-time (or restart-safe) SEC ingestion
- Chroma persistence
- gated Aegra startup after ingestion completion

## Flow

1. `ingestion-worker` fetches SEC submissions for top 100 companies.
2. Worker filters to `10-K` filings from the last 365 days.
3. Worker ingests filings into Chroma and persists progress to a state volume.
4. Worker writes `ingestion_complete.flag` only when the run finishes cleanly.
5. `aegra` waits for that flag, then starts migrations and serves the API.

No webapp is included in this stack.

## Start

```bash
cd secrag-dockploy
docker compose up --build
```

## Services

- `postgres`: Aegra metadata/checkpoint database
- `ingestion-worker`: scanner + ingestion pipeline (no Appwrite)
- `aegra`: API service, starts only after ingestion completion flag exists

## Important Paths

- Chroma volume path in worker: `/data/chroma_db`
- Chroma path in Aegra: `/secrag/chroma_db`
- Shared state path: `/data/state`
- Completion flag: `/data/state/ingestion_complete.flag`

## Worker Defaults

- `MAX_COMPANIES=100`
- `TARGET_FORM=10-K`
- `LOOKBACK_DAYS=365`
- `FORCE_REINGEST=false`

