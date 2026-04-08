#!/usr/bin/env python3
"""
Scio Township Agenda Text Extractor
Reads downloaded agenda PDFs + manifest, re-scrapes Granicus for viewer URLs,
extracts text from each PDF, outputs agenda_index.json for ScioSearch.

Usage:
    python3 scio_agenda_extract.py
    python3 scio_agenda_extract.py --pdfs ./scio_agendas --output ./agenda_index.json

Dependencies:
    pip3 install requests pypdf beautifulsoup4 --break-system-packages
"""

import argparse
import csv
import json
import os
import re

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

GRANICUS_URL = "https://sciotownship.granicus.com/ViewPublisher.php?view_id=19"
CLOUDFRONT_DOMAIN = "d3n9y02raazwpg.cloudfront.net"
GRANICUS_DOMAIN = "sciotownship.granicus.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


def scrape_viewer_urls() -> dict:
    """
    Scrape Granicus and return {cloudfront_pdf_url: granicus_viewer_url} mapping.
    Looks for AgendaViewer or MediaPlayer links in the same row as each packet PDF.
    Falls back to the main ViewPublisher page if no viewer link found.
    """
    print("Fetching Granicus to collect viewer URLs...")
    resp = requests.get(GRANICUS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    mapping = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        cf_url = None
        viewer_url = None

        for a in row.find_all("a", href=True):
            href = a["href"]
            # Make relative URLs absolute
            if href.startswith("//"):
                href = f"https:{href}"
            elif href.startswith("/"):
                href = f"https://{GRANICUS_DOMAIN}{href}"

            if CLOUDFRONT_DOMAIN in href and href.endswith(".pdf"):
                cf_url = href
            elif GRANICUS_DOMAIN in href and (
                "AgendaViewer" in href or "MediaPlayer" in href
            ):
                viewer_url = href

        if cf_url:
            mapping[cf_url] = viewer_url or GRANICUS_URL

    print(f"  Found {len(mapping)} packet URL → viewer URL mappings")
    return mapping


def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF file. Returns empty string on failure."""
    try:
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                # Collapse excessive whitespace but preserve line breaks
                text = re.sub(r" {2,}", " ", text).strip()
                parts.append(text)
        return "\n".join(parts)
    except Exception as e:
        print(f"  WARNING: text extraction failed for {os.path.basename(pdf_path)}: {e}")
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Extract text from agenda PDFs and build agenda_index.json"
    )
    parser.add_argument(
        "--pdfs",
        default="./scio_agendas",
        help="Directory containing downloaded agenda PDFs (default: ./scio_agendas)",
    )
    parser.add_argument(
        "--output",
        default="./agenda_index.json",
        help="Output JSON file path (default: ./agenda_index.json)",
    )
    args = parser.parse_args()

    manifest_path = os.path.join(args.pdfs, "agendas_manifest.csv")
    if not os.path.exists(manifest_path):
        print(f"ERROR: manifest not found at {manifest_path}")
        print(f"  Run scio_agenda_download.py first to download PDFs.")
        return

    # Read manifest
    with open(manifest_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Manifest: {len(rows)} entries")

    # Get viewer URLs from live Granicus page
    viewer_map = scrape_viewer_urls()

    # Build index
    index = []
    missing = 0

    for i, row in enumerate(rows, 1):
        fname = row.get("file", "")
        fpath = os.path.join(args.pdfs, fname)
        cf_url = row.get("url", "")

        if not os.path.exists(fpath):
            print(f"[{i:03d}/{len(rows)}] MISSING  {fname}")
            missing += 1
            continue

        viewer_url = viewer_map.get(cf_url, GRANICUS_URL)
        print(f"[{i:03d}/{len(rows)}] {fname}")

        text = extract_text(fpath)

        index.append(
            {
                "date": row.get("date", ""),
                "body": row.get("body", ""),
                "file": fname,
                "granicus_url": viewer_url,
                "text": text,
            }
        )

    # Sort by date ascending
    index.sort(key=lambda e: e["date"])

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    total_chars = sum(len(e["text"]) for e in index)
    size_mb = os.path.getsize(args.output) / 1024 / 1024
    empty = sum(1 for e in index if not e["text"])

    print(f"\n{'='*60}")
    print(f"Done.")
    print(f"  Entries written : {len(index)}")
    print(f"  Missing PDFs    : {missing}")
    print(f"  Empty text      : {empty}  (image-only PDFs, OCR not run)")
    print(f"  Total text chars: {total_chars:,}")
    print(f"  Output file     : {args.output}")
    print(f"  File size       : {size_mb:.1f} MB")
    print(f"\nNext step: upload agenda_index.json to Azure $web container")
    print(f"  portal.azure.com → sciotownshipsearch → Containers → $web → Upload")


if __name__ == "__main__":
    main()
