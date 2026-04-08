# Scio Township Meeting Transcript Search

A tool to extract, search, and browse transcripts from Scio Township meeting videos on YouTube.

## Live Site

**https://sciotownshipsearch.z20.web.core.windows.net/**

No login required. Works on any device.

## Architecture

- **Hosting:** Azure Static Website (storage account: `sciotownshipsearch`, container: `$web`)
- **Files on Azure:** `scio_search.html` (search UI), `all_transcripts.txt` (combined transcripts)
- **Transcript source:** YouTube auto-captions from the Scio Community News channel
- **Upload mechanism:** The "Update Transcript File" button in the web UI uploads to both the browser session and Azure blob storage via SAS token

## Current Coverage

- 281 meetings, Dec 2021 through Feb 2026
- Board of Trustees, Planning Commission, ZBA, Parks & Rec, DDA, Budget & Finance, Compensation Commission, Land Preservation, and more

## Updating Transcripts (Adding New Meetings)

### Step 1: Fetch new transcripts

```bash
cd ~/Desktop/"DERMLE DATA"/"Scio Script Extractor"
python3 scio_transcript_extractor.py
```

This scans the YouTube channel, downloads any new transcripts, and rebuilds `all_transcripts.txt`.

Must run from your Mac (residential IP). YouTube blocks cloud IPs.

### Step 2: Upload to the live site

1. Go to https://sciotownshipsearch.z20.web.core.windows.net/
2. Click "Update Transcript File"
3. Select `all_transcripts.txt` from the Scio Script Extractor folder

The file loads in your browser AND saves to Azure. You'll see "Saved to server" confirmation. Everyone who visits the site after that gets the updated data.

## Updating the Search UI

Upload `scio_search.html` to the `$web` container via the Azure portal:
1. portal.azure.com → Storage accounts → sciotownshipsearch
2. Data storage → Containers → $web
3. Upload → select `scio_search.html` → check "Overwrite if files already exist"

## Going Further Back in Time

To fetch older transcripts, edit `scio_transcript_extractor.py` and change `START_DATE`, then rerun. Note: YouTube may rate-limit from certain IPs. Use a VPN if needed.

## Files

| File | Description |
|------|-------------|
| `scio_search.html` | Browser-based search UI (deployed to Azure) |
| `scio_transcript_extractor.py` | Python script to fetch transcripts from YouTube |
| `all_transcripts.txt` | Combined transcript file (~32MB, all meetings) |
| `transcript_index.csv` | Index of all videos processed |
| `transcripts/` | Individual transcript files with timestamps |

## Dependencies

```bash
pip install youtube-transcript-api scrapetube
```

## Azure Details

- Storage account: `sciotownshipsearch`
- Container: `$web`
- Primary endpoint: `https://sciotownshipsearch.z20.web.core.windows.net/`
- SAS token: Embedded in `scio_search.html` for write access (expires Feb 2027)
- CORS: Configured to allow PUT from the site origin

## Date Parsing

The search UI parses meeting dates from YouTube video titles. Supported formats include slash, dash, underscore, space, and dot separators, month names, European date order, and 2-digit years. Titles that can't be parsed still appear in search results but won't respond to date range filters.
