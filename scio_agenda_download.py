#!/usr/bin/env python3
"""
Scio Township Agenda Downloader
Scrapes Granicus, finds all CloudFront packet PDFs, downloads & trims to first N pages.

Usage:
    python scio_agenda_download.py
    python scio_agenda_download.py --pages 5 --output ./scio_agendas --since 2024-01-01

Dependencies:
    pip install requests pypdf beautifulsoup4
"""

import argparse
import csv
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader, PdfWriter

GRANICUS_URL = "https://sciotownship.granicus.com/ViewPublisher.php?view_id=19"
CLOUDFRONT_DOMAIN = "d3n9y02raazwpg.cloudfront.net"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

MONTH_MAP = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}


def scrape_meetings(since: datetime) -> list[dict]:
    """Fetch the Granicus listing and return meetings with CloudFront packet URLs."""
    print(f"Fetching meeting list from Granicus...")
    resp = requests.get(GRANICUS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.find_all("tr")

    meetings = []
    seen_urls = set()

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        body = cells[0].get_text(strip=True)
        if not body:
            continue

        # Find date in row text
        date_match = re.search(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(\d{4})',
            row.get_text()
        )
        if not date_match:
            continue

        mon, day, year = date_match.group(1), int(date_match.group(2)), int(date_match.group(3))
        try:
            dt = datetime(year, MONTH_MAP[mon], day)
        except ValueError:
            continue

        if dt < since:
            continue

        # Find CloudFront PDF link
        packet_link = None
        for a in row.find_all("a", href=True):
            if CLOUDFRONT_DOMAIN in a["href"] and a["href"].endswith(".pdf"):
                packet_link = a["href"]
                break

        if not packet_link or packet_link in seen_urls:
            continue

        seen_urls.add(packet_link)
        meetings.append({"body": body, "date": dt, "url": packet_link})

    meetings.sort(key=lambda m: m["date"])
    print(f"Found {len(meetings)} meetings with downloadable packets since {since.date()}")
    return meetings


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def download_and_trim(url: str, pages: int, retries: int = 3):
    """Download PDF and return trimmed bytes + total page count."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            data = r.content
            break
        except requests.RequestException as e:
            print(f"    attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2)
    else:
        return None, 0

    reader = PdfReader(BytesIO(data))
    total = len(reader.pages)
    writer = PdfWriter()
    for i in range(min(pages, total)):
        writer.add_page(reader.pages[i])
    out = BytesIO()
    writer.write(out)
    return out.getvalue(), total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages",  type=int, default=5,
                        help="Pages to extract from each packet (default: 5)")
    parser.add_argument("--output", default="./scio_agendas",
                        help="Output directory (default: ./scio_agendas)")
    parser.add_argument("--since",  default="2024-01-01",
                        help="Only include meetings on/after this date (default: 2024-01-01)")
    parser.add_argument("--workers", type=int, default=5,
                        help="Parallel download threads (default: 5)")
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d")
    os.makedirs(args.output, exist_ok=True)
    manifest_path = os.path.join(args.output, "agendas_manifest.csv")

    meetings = scrape_meetings(since)
    if not meetings:
        print("No meetings found.")
        return

    print(f"\nDownloading to: {args.output}")
    print(f"Extracting first {args.pages} pages per packet")
    print("-" * 65)

    results = []
    used_names = set()
    print_lock = threading.Lock()

    # Pre-assign filenames (must be done serially to avoid duplicates)
    jobs = []
    for i, m in enumerate(meetings, 1):
        body = m["body"]
        dt   = m["date"]
        url  = m["url"]
        base  = f"{dt.strftime('%Y-%m-%d')}_{slugify(body)}_agenda"
        fname = f"{base}.pdf"
        n = 2
        while fname in used_names:
            fname = f"{base}_{n}.pdf"
            n += 1
        used_names.add(fname)
        jobs.append((i, body, dt, url, fname))

    def process(job):
        i, body, dt, url, fname = job
        fpath = os.path.join(args.output, fname)
        label = f"[{i:03d}/{len(meetings)}] {dt.strftime('%Y-%m-%d')} {body[:38]:<38}"

        if os.path.exists(fpath):
            with print_lock:
                print(f"{label} SKIP")
            return dict(date=dt.date(), body=body, file=fname,
                        status="skipped", extracted="", total="", url=url)

        pdf_bytes, total = download_and_trim(url, args.pages)

        if pdf_bytes is None:
            with print_lock:
                print(f"{label} FAILED")
            return dict(date=dt.date(), body=body, file=fname,
                        status="failed", extracted="", total="", url=url)
        else:
            with open(fpath, "wb") as f:
                f.write(pdf_bytes)
            saved = min(args.pages, total)
            with print_lock:
                print(f"{label} OK  ({total}pp → {saved} saved, {len(pdf_bytes)//1024}KB)")
            return dict(date=dt.date(), body=body, file=fname,
                        status="ok", extracted=saved, total=total, url=url)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process, job): job for job in jobs}
        for future in as_completed(futures):
            results.append(future.result())

    # Sort results back into date order for the manifest
    results.sort(key=lambda r: str(r["date"]))

    # Merge with existing manifest entries (never truncate prior records)
    existing = []
    if os.path.exists(manifest_path):
        with open(manifest_path, newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    existing_files = {r["file"] for r in existing}
    new_rows = [r for r in results if r["file"] not in existing_files]
    merged = existing + [{k: str(v) for k, v in r.items()} for r in new_rows]
    merged.sort(key=lambda r: str(r["date"]))

    # Write manifest
    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date","body","file","status","extracted","total","url"])
        w.writeheader()
        w.writerows(merged)

    ok      = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed  = sum(1 for r in results if r["status"] == "failed")

    print("-" * 65)
    print(f"Done.  {ok} downloaded  |  {skipped} skipped  |  {failed} failed")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
