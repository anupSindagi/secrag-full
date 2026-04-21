import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import chromadb
import requests
from chromadb.config import Settings
from dotenv import load_dotenv

from sec_filing_parser import parse_sec_filing

load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Company Name contact@example.com")
REQUEST_INTERVAL_SECONDS = float(os.getenv("REQUEST_INTERVAL_SECONDS", "0.1"))
MAX_COMPANIES = int(os.getenv("MAX_COMPANIES", "100"))
TARGET_FORM = os.getenv("TARGET_FORM", "10-K")
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "365"))
SP500_CSV_PATH = Path(os.getenv("SP500_CSV_PATH", "/app/data/sp500.csv"))
CHROMA_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", "/data/chroma_db"))
STATE_DIR = Path(os.getenv("STATE_DIR", "/data/state"))
FORCE_REINGEST = env_bool("FORCE_REINGEST", False)
INGESTION_COMPLETE_FLAG = Path(
    os.getenv("INGESTION_COMPLETE_FLAG", str(STATE_DIR / "ingestion_complete.flag"))
)

PROCESSED_ACCESSIONS_FILE = STATE_DIR / "processed_accessions.json"
CHECKPOINT_FILE = STATE_DIR / "checkpoint.json"
LOCK_FILE = STATE_DIR / ".ingestion.lock"

SEC_SUBMISSION_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

SEC_FILING_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}


def ensure_directories() -> None:
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, data: Dict | List) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp_path.replace(path)


def load_processed_accessions() -> Set[str]:
    if not PROCESSED_ACCESSIONS_FILE.exists():
        return set()
    with PROCESSED_ACCESSIONS_FILE.open("r", encoding="utf-8") as f:
        values = json.load(f)
    return set(values)


def save_processed_accessions(processed: Set[str]) -> None:
    atomic_write_json(PROCESSED_ACCESSIONS_FILE, sorted(processed))


def write_checkpoint(data: Dict) -> None:
    atomic_write_json(CHECKPOINT_FILE, data)


def parse_report_date(report_date: str) -> Optional[datetime]:
    if not report_date:
        return None
    try:
        return datetime.strptime(report_date.split("T")[0], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def within_lookback(report_date: str) -> bool:
    dt = parse_report_date(report_date)
    if not dt:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    return dt >= cutoff


def load_companies(csv_path: Path, max_companies: int) -> List[Dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    return rows[:max_companies]


def format_cik(cik: str) -> str:
    return str(cik).zfill(10)


def get_sec_submissions(cik: str) -> Optional[Dict]:
    cik_formatted = format_cik(cik)
    url = f"https://data.sec.gov/submissions/CIK{cik_formatted}.json"
    try:
        response = requests.get(url, headers=SEC_SUBMISSION_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"[scanner] failed submissions CIK={cik}: {exc}")
        return None


def build_candidate_filings(companies: List[Dict[str, str]]) -> List[Dict]:
    candidates: Dict[str, Dict] = {}
    print(
        f"[scanner] scanning {len(companies)} companies for form={TARGET_FORM}, lookback_days={LOOKBACK_DAYS}"
    )

    for index, company in enumerate(companies, start=1):
        cik = str(company.get("CIK", "")).strip()
        symbol = company.get("Symbol", "NA")
        if not cik:
            continue

        print(f"[scanner] ({index}/{len(companies)}) {symbol} CIK={cik}")
        data = get_sec_submissions(cik)
        if not data:
            time.sleep(REQUEST_INTERVAL_SECONDS)
            continue

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_documents = filings.get("primaryDocument", [])
        report_dates = filings.get("reportDate", [])
        is_xbrl = filings.get("isXBRL", [])
        is_inline_xbrl = filings.get("isInlineXBRL", [])

        for i, form in enumerate(forms):
            if form != TARGET_FORM:
                continue

            report_date = report_dates[i] if i < len(report_dates) else ""
            if not within_lookback(report_date):
                continue

            accession_no = accession_numbers[i] if i < len(accession_numbers) else ""
            accession_clean = accession_no.replace("-", "")
            if not accession_clean:
                continue

            file_name = primary_documents[i] if i < len(primary_documents) else ""
            if not file_name:
                continue

            cik_for_url = str(cik).lstrip("0") or "0"
            file_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_for_url}/{accession_clean}/{file_name}"
            )

            record = {
                "accession_id": accession_clean,
                "cik": int(cik) if str(cik).isdigit() else cik,
                "symbol": symbol,
                "company_name": company.get("Security", ""),
                "sector": company.get("GICS Sector", ""),
                "sub_sector": company.get("GICS Sub-Industry", ""),
                "form": form,
                "file_name": file_name,
                "report_date": report_date,
                "file_url": file_url,
                "is_xbrl": bool(is_xbrl[i]) if i < len(is_xbrl) else False,
                "ix_inline_xbrl": bool(is_inline_xbrl[i]) if i < len(is_inline_xbrl) else False,
            }
            candidates[accession_clean] = record

        time.sleep(REQUEST_INTERVAL_SECONDS)

    output = list(candidates.values())
    output.sort(key=lambda row: row.get("report_date", ""))
    print(f"[scanner] candidate filings after filters: {len(output)}")
    return output


def create_temporal_context_from_metadata(metadata: Dict) -> str:
    context_parts: List[str] = []

    if metadata.get("company_name"):
        context_parts.append(f"Company: {metadata['company_name']}")
    if metadata.get("symbol"):
        context_parts.append(f"Symbol: {metadata['symbol']}")
    if metadata.get("sector"):
        context_parts.append(f"Sector: {metadata['sector']}")
    if metadata.get("sub_sector"):
        context_parts.append(f"Sub Sector: {metadata['sub_sector']}")

    report_date = metadata.get("report_date", "")
    parsed = parse_report_date(report_date)
    if parsed:
        year = parsed.year
        month = parsed.month
        quarter = (month - 1) // 3 + 1
        context_parts.extend(
            [
                f"Report Date: {report_date.split('T')[0]}",
                f"Quarter: Q{quarter} {year}",
                f"Period: {year} Q{quarter}",
                f"Year: {year}",
                parsed.strftime("%B %Y"),
            ]
        )
    elif report_date:
        context_parts.append(f"Report Date: {report_date}")

    if metadata.get("form"):
        context_parts.append(f"Form: {metadata['form']}")

    return (" | ".join(context_parts) + "\n\n") if context_parts else ""


def ingest_filing(
    filing: Dict,
    sec_text_collection,
    sec_facts_collection,
) -> bool:
    accession_id = filing["accession_id"]
    file_url = filing["file_url"]

    try:
        response = requests.get(file_url, headers=SEC_FILING_HEADERS, timeout=60)
        response.raise_for_status()
        html_content = response.text
    except requests.RequestException as exc:
        print(f"[ingest] failed download {accession_id}: {exc}")
        return False

    try:
        chunks = parse_sec_filing(
            html_content, form_type=filing.get("form", "10-K"), url=file_url
        )
    except Exception as exc:
        print(f"[ingest] parser failure {accession_id}: {exc}")
        return False

    if not chunks:
        print(f"[ingest] no chunks for {accession_id}")
        return False

    temporal_context = create_temporal_context_from_metadata(filing)
    text_chunks = [c for c in chunks if c.get("type") == "text"]
    table_chunks = [c for c in chunks if c.get("type") == "table"]

    if text_chunks:
        text_docs = [temporal_context + chunk["content"] for chunk in text_chunks]
        text_metas = []
        for chunk in text_chunks:
            meta = chunk.get("metadata", {}).copy()
            meta.update(filing)
            meta["chunk_type"] = "text"
            meta["chunk_context"] = chunk.get("context", "")
            meta["chunk_tokens"] = chunk.get("tokens", 0)
            text_metas.append(meta)
        text_ids = [f"{accession_id}_text_{i}" for i in range(len(text_chunks))]
        sec_text_collection.upsert(documents=text_docs, metadatas=text_metas, ids=text_ids)

    if table_chunks:
        table_docs = [temporal_context + chunk["content"] for chunk in table_chunks]
        table_metas = []
        for chunk in table_chunks:
            meta = chunk.get("metadata", {}).copy()
            meta.update(filing)
            meta["chunk_type"] = "table"
            meta["chunk_context"] = chunk.get("context", "")
            meta["chunk_tokens"] = chunk.get("tokens", 0)
            meta["content_type"] = chunk.get("content_type", "html")
            table_metas.append(meta)
        table_ids = [f"{accession_id}_table_{i}" for i in range(len(table_chunks))]
        sec_facts_collection.upsert(
            documents=table_docs, metadatas=table_metas, ids=table_ids
        )

    print(
        f"[ingest] accession={accession_id} text_chunks={len(text_chunks)} table_chunks={len(table_chunks)}"
    )
    return bool(text_chunks or table_chunks)


def acquire_lock() -> bool:
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        print(f"[worker] lock exists: {LOCK_FILE}")
        return False


def release_lock() -> None:
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def run_once() -> int:
    ensure_directories()

    if INGESTION_COMPLETE_FLAG.exists() and not FORCE_REINGEST:
        print(
            f"[worker] complete flag exists ({INGESTION_COMPLETE_FLAG}), skipping due to FORCE_REINGEST=false"
        )
        return 0

    if FORCE_REINGEST and INGESTION_COMPLETE_FLAG.exists():
        INGESTION_COMPLETE_FLAG.unlink()

    if not acquire_lock():
        return 1

    try:
        chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DB_PATH),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
        sec_text_collection = chroma_client.get_or_create_collection(name="sec_text")
        sec_facts_collection = chroma_client.get_or_create_collection(name="sec_facts")

        processed = load_processed_accessions()
        companies = load_companies(SP500_CSV_PATH, MAX_COMPANIES)
        candidates = build_candidate_filings(companies)
        pending = [f for f in candidates if f["accession_id"] not in processed]

        write_checkpoint(
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "total_candidates": len(candidates),
                "already_processed": len(processed),
                "pending": len(pending),
                "current_accession": None,
            }
        )

        print(f"[worker] pending filings to ingest: {len(pending)}")
        failures = 0
        for index, filing in enumerate(pending, start=1):
            accession_id = filing["accession_id"]
            write_checkpoint(
                {
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "total_candidates": len(candidates),
                    "already_processed": len(processed),
                    "pending": len(pending),
                    "current_index": index,
                    "current_accession": accession_id,
                }
            )

            success = ingest_filing(filing, sec_text_collection, sec_facts_collection)
            if success:
                processed.add(accession_id)
                save_processed_accessions(processed)
            else:
                failures += 1

        if failures == 0:
            INGESTION_COMPLETE_FLAG.write_text(
                datetime.now(timezone.utc).isoformat(), encoding="utf-8"
            )
            write_checkpoint(
                {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "total_candidates": len(candidates),
                    "processed_total": len(processed),
                    "failures": failures,
                }
            )
            print("[worker] ingestion finished cleanly; completion flag created")
            return 0

        write_checkpoint(
            {
                "status": "partial",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_candidates": len(candidates),
                "processed_total": len(processed),
                "failures": failures,
            }
        )
        print(
            "[worker] ingestion ended with failures; completion flag not created (restart will resume)"
        )
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(run_once())
