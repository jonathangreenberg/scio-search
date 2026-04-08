# Scio Township Meeting Search — Project Document
**Last Updated: March 12, 2026**

---

## Quick Reference

| Item | Detail |
|------|--------|
| **Project** | Scio Township Meeting Search |
| **Location** | `/Users/pooda4/Desktop/DERMLE DATA/Scio Script Extractor/` |
| **Live URL** | https://sciotownshipsearch.z20.web.core.windows.net/ |
| **Stack** | Python 3.9, Azure Static Website (Blob Storage), single-file HTML/JS app |
| **Deployment** | Claude copies files from Mac and pushes to Azure via curl + SAS token |
| **Azure Storage** | `sciotownshipsearch` storage account, `$web` container |
| **SAS Token** | Embedded in `scio_search.html` (expires Feb 2027) |

---

## Technical Notes

### Architecture
Two independent data pipelines feed two tabs in a single-file HTML/JS search app:

**Transcript tab** — YouTube auto-captions from Scio Community News channel, stored as `all_transcripts.txt` (~32MB). Loaded on page open. Search runs in-browser against parsed line/timestamp data.

**Agenda tab** — Agenda packet PDFs downloaded from Granicus CDN, text-extracted to `agenda_index.json`. Loaded lazily on first tab click. Search runs in-browser against full text. Results link to Granicus viewer page.

### Transcript Pipeline
1. `scio_transcript_extractor.py` — scrapes YouTube channel, downloads captions, rebuilds `all_transcripts.txt`
2. Must run from residential IP — YouTube blocks cloud IPs
3. Claude deploys to Azure (see Update Procedures below)

### Agenda Pipeline
1. `scio_agenda_download.py` — scrapes Granicus, downloads CloudFront PDFs, trims to first N pages, writes `agendas_manifest.csv`
2. `scio_agenda_extract.py` — re-scrapes Granicus for viewer URLs, runs pypdf text extraction on all PDFs, outputs `agenda_index.json`
3. Claude deploys to Azure (see Update Procedures below)

### Deploying HTML Changes
Tell Claude to deploy `scio_search.html` — same curl method as data files.

### Python Dependencies
```bash
pip3 install requests pypdf beautifulsoup4 --break-system-packages
```

### Key Behavioral Notes
- Agenda tab lazy-loads `agenda_index.json` on first click (avoids loading ~5MB on initial page open)
- The downloader skip logic checks filename existence only — does not verify file integrity
- CloudFront handles high concurrency well; tested to 50 parallel workers with no 403s
- Some PDFs are image-only (no extractable text) — these appear in the index with empty text and won't match searches
- Granicus viewer URLs are scraped live each time `scio_agenda_extract.py` runs; if no viewer link is found for a meeting, falls back to the main ViewPublisher page

### CORS / SAS Token
Azure CORS is configured to allow PUT from the site origin. The SAS token is stored in PROJECT.md (below) and used by Claude to deploy files via curl. If it expires (Feb 2027), generate a new one: Azure portal → sciotownshipsearch → Shared access tokens → Blob service, Object resource, Write+Create permissions → set expiry → copy full token string → update SAS Token entry below.

---

## File Map

| File | Purpose |
|------|---------|
| `scio_search.html` | Single-file search UI — both tabs, all CSS and JS |
| `scio_transcript_extractor.py` | Fetches YouTube captions, rebuilds `all_transcripts.txt` |
| `scio_agenda_download.py` | Downloads agenda PDFs from Granicus CDN |
| `scio_agenda_extract.py` | Extracts text from PDFs, outputs `agenda_index.json` |
| `all_transcripts.txt` | Combined transcript data (~32MB), uploaded to Azure |
| `transcript_index.csv` | Index of all YouTube videos processed |
| `agendas_manifest.csv` | Index of all downloaded agenda PDFs with CloudFront URLs |
| `scio_logo.png` | Township logo used in the UI header |
| `transcripts/` | Individual transcript files with timestamps |
| `scio_agendas/` | Downloaded/trimmed agenda PDFs (260 files as of Mar 2026) |

### Azure `$web` Container Files
| File | Size | Notes |
|------|------|-------|
| `scio_search.html` | ~54KB | The app |
| `all_transcripts.txt` | ~32MB | Transcript data |
| `agenda_index.json` | 1.38 MB | Agenda text index |
| `scio_logo.png` | small | Header logo |

---

## Coverage

### Transcripts
- 702 transcripts, December 2021 through March 2026
- Source: YouTube auto-captions from Scio Community News channel
- Bodies: Board of Trustees, Planning Commission, ZBA, Parks & Rec, DDA, Budget & Finance, Compensation Commission, Land Preservation, others

### Agendas
- 261 packets, January 2024 through March 9, 2026
- Source: Granicus CDN (CloudFront) packet PDFs, trimmed to first 5 pages
- Bodies: All 20+ bodies that post to Granicus with downloadable packets
- ~83 meetings in date range have no downloadable packet (video/agenda-only)

---

## Update Procedures

### How Deployment Works
Claude copies files from your Mac using the Filesystem tool, then pushes to Azure Blob Storage via `curl` with the SAS token. No az CLI, no portal, no manual steps beyond running the local Python scripts.

### Azure Blob Storage Base URL
```
https://sciotownshipsearch.blob.core.windows.net/$web/
```

### SAS Token (expires Feb 2027)
```
sv=2024-11-04&ss=b&srt=o&sp=wctfx&se=2027-02-08T09:07:46Z&st=2026-02-08T00:52:46Z&spr=https&sig=is1vbDrmjxpq2No5lS%2Fs7AFkRnnXqAfVCS3mzWRTbr0%3D
```

---

### "Update Scio Search" — Full Workflow

When you say "update Scio Search", Claude runs through this sequence in order.

**Step 1 — Claude checks current state on Azure**
Claude pulls the live counts from Azure: transcript count and last date, agenda count and last date. Reports both to you.

**Step 2 — Transcripts**
Claude gives you this command to run:
```bash
cd ~/Desktop/"DERMLE DATA"/"Scio Script Extractor"
python3 scio_transcript_extractor.py
```
You paste the output. Claude verifies new count, then copies `all_transcripts.txt` from your Mac and deploys to Azure.

**Step 3 — Agendas**
Claude gives you this command to run (substituting the last known agenda date from Step 1):
```bash
cd ~/Desktop/"DERMLE DATA"/"Scio Script Extractor"
python3 scio_agenda_download.py --since YYYY-MM-DD
```
You paste the output. Claude verifies the manifest row count matches expected (current count + new downloads). If the manifest count looks wrong, Claude pulls the index from Azure to recover before proceeding. If manifest looks good, Claude gives you:
```bash
python3 scio_agenda_extract.py
```
You paste the output. Claude verifies entry count in the generated `agenda_index.json` matches the manifest. If counts match, Claude copies `agenda_index.json` from your Mac and deploys to Azure.

**Step 4 — Claude updates PROJECT.md**
Updates transcript count, agenda count, and coverage dates to reflect the new state.

**Step 5 — Claude confirms**
Verifies both files are live on Azure with correct counts.

---

### Deploy HTML Changes Only
1. Tell Claude: "deploy the HTML to the site"
2. Claude copies `scio_search.html` from your Mac and pushes to Azure

### If agenda_index.json or agendas_manifest.csv gets corrupted
The authoritative copy of `agenda_index.json` is always on Azure. Claude pulls it down, merges any new entries, redeploys, and provides restored local copies for download.

---

## Pending Work

- **OCR pass** — ~15-20 agenda PDFs are image-only and return no text from pypdf. Could run tesseract on those specifically.
- **Incremental agenda updates** — Currently the downloader re-checks all meetings and skips existing files. Add a `--since last-run` mode that only looks for new Granicus packets posted after the last manifest date.
- **Incremental transcript updates** — Already works; just re-run `scio_transcript_extractor.py` and re-upload `all_transcripts.txt`.
- **Agenda date range hint** — Transcripts tab shows "range from X to Y." Add same to Agendas tab once data is loaded.

---

## Future Ideas

- Wire search into ScioNews.com (iframe or dedicated page)
- Unified search across both transcripts and agendas simultaneously
- Full-text OCR for image-only PDFs (tesseract)
- Expand agenda archive back to April 2020 (Granicus launch)
- Email/RSS alert when new meetings are posted

---

## Design & Style

Matches Scio Township branding:
- Deep forest green primary (`#2e8b57`, `#236b43`)
- Gold/yellow highlight (`#f4c430`)
- Sand/cream backgrounds (`#f5f1eb`, `#faf8f5`)
- Blue timestamps/links (`#3498db`)
- Libre Baskerville not used here (sans-serif UI)

---

## File Structure

```
Scio Script Extractor/
├── scio_search.html              # Search UI (deploy to Azure)
├── scio_transcript_extractor.py  # YouTube caption scraper
├── scio_agenda_download.py       # Granicus PDF downloader
├── scio_agenda_extract.py        # PDF text extractor → agenda_index.json
├── all_transcripts.txt           # Combined transcripts (~32MB)
├── transcript_index.csv          # YouTube video index
├── agendas_manifest.csv          # Agenda PDF manifest (in scio_agendas/)
├── scio_logo.png                 # UI header logo
├── transcripts/                  # Individual transcript files
└── scio_agendas/                 # Downloaded agenda PDFs (260 files)
    ├── agendas_manifest.csv
    ├── 2024-01-03_roads-advisory-committee_agenda.pdf
    └── ... (259 more)
```

---

## Notes

- SAS token expires February 2027. See CORS / SAS Token section above for renewal instructions. Update the token in the Update Procedures section of this document.
- YouTube transcript scraping must run from a residential IP. Cloud/VPN IPs get rate-limited or blocked.
- Granicus CDN (CloudFront) has no rate limiting observed at up to 50 parallel workers.
- `pypdf` extracts text well from digitally-created PDFs. Scanned/image PDFs return empty strings silently.
- agenda_index.json is estimated at ~5MB (260 packets × ~5 pages × ~400 words avg). This is fine for browser loading but consider pagination if the archive grows significantly.
