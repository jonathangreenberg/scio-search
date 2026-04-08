#!/usr/bin/env python3
"""
Scio Township Meeting Transcript Extractor
==========================================
Extracts transcripts from YouTube videos on the Scio Community News channel.

Requirements:
    pip install youtube-transcript-api scrapetube

Usage:
    python scio_transcript_extractor.py

Output:
    - Individual transcript files in ./transcripts/
    - Combined searchable file: all_transcripts.txt
    - Index file: transcript_index.csv
"""

import os
import re
import csv
import time
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# Try scrapetube first, fall back to manual approach if needed
try:
    import scrapetube
    HAS_SCRAPETUBE = True
except ImportError:
    HAS_SCRAPETUBE = False
    print("Note: scrapetube not installed. Install with: pip install scrapetube")

# =============================================================================
# CONFIGURATION - Modify these as needed
# =============================================================================

CHANNEL_URL = "https://www.youtube.com/@sciocommunitynews2701"
CHANNEL_ID = None  # Will be extracted or can be set manually

# Keywords to identify board/trustee meetings (case-insensitive)
MEETING_KEYWORDS = [
    "board",
    "trustee", 
    "meeting",
    "township",
    "regular meeting",
    "special meeting",
]

# Keywords to EXCLUDE (e.g., if there are non-meeting videos)
EXCLUDE_KEYWORDS = [
    # Add any keywords to exclude here
]

# Date filter - only include videos from this date forward
# Set to None to disable date filtering
START_DATE = "2026-01-01"  # January 1, 2026

# Output settings
OUTPUT_DIR = "transcripts"
COMBINED_FILE = "all_transcripts.txt"
INDEX_FILE = "transcript_index.csv"
FAILED_FILE = "failed_videos.txt"

# =============================================================================
# FUNCTIONS
# =============================================================================

def parse_date_from_title(title):
    """Try to extract a date from a video title."""
    
    # Common patterns in meeting titles
    patterns = [
        # "January 14, 2025" or "January 14 2025"
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
        # "Jan 14, 2025" or "Jan 14 2025"
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',
        # "1-14-2025" or "1/14/2025"
        r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',
        # "1-14-25" or "1/14/25"
        r'(\d{1,2})[-/](\d{1,2})[-/](\d{2})(?!\d)',
    ]
    
    month_map = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
        'oct': 10, 'nov': 11, 'dec': 12
    }
    
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            try:
                if i < 2:  # Month name patterns
                    month = month_map[match.group(1).lower()]
                    day = int(match.group(2))
                    year = int(match.group(3))
                elif i == 2:  # M-D-YYYY
                    month = int(match.group(1))
                    day = int(match.group(2))
                    year = int(match.group(3))
                else:  # M-D-YY
                    month = int(match.group(1))
                    day = int(match.group(2))
                    year = int(match.group(3))
                    year = 2000 + year if year < 100 else year
                
                return datetime(year, month, day)
            except (ValueError, KeyError):
                continue
    
    return None


def get_channel_videos(channel_url):
    """Get all videos from a YouTube channel."""
    
    if not HAS_SCRAPETUBE:
        print("\nERROR: scrapetube is required to scan the channel.")
        print("Install it with: pip install scrapetube")
        print("\nAlternatively, you can manually create a file 'video_ids.txt'")
        print("with one YouTube video ID per line, and the script will use that.")
        return None
    
    print(f"Scanning channel: {channel_url}")
    
    # Extract channel handle from URL
    if "/@" in channel_url:
        channel_handle = channel_url.split("/@")[1].split("/")[0]
        videos = scrapetube.get_channel(channel_url=channel_url)
    else:
        videos = scrapetube.get_channel(channel_url=channel_url)
    
    video_list = []
    for video in videos:
        title = video.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown')
        video_list.append({
            'video_id': video['videoId'],
            'title': title,
            'url': f"https://www.youtube.com/watch?v={video['videoId']}",
            'parsed_date': parse_date_from_title(title)
        })
    
    print(f"Found {len(video_list)} total videos on channel")
    return video_list


def filter_meeting_videos(videos, keywords=MEETING_KEYWORDS, exclude=EXCLUDE_KEYWORDS, start_date=START_DATE, skip_keyword_filter=False):
    """Filter videos to only include meetings based on title keywords and date."""
    
    if not videos:
        return []
    
    # Parse start_date if provided
    min_date = None
    if start_date:
        try:
            min_date = datetime.strptime(start_date, "%Y-%m-%d")
            print(f"Filtering for videos from {start_date} forward")
        except ValueError:
            print(f"Warning: Could not parse start date '{start_date}', skipping date filter")
    
    filtered = []
    skipped_date = 0
    skipped_keyword = 0
    no_date_found = 0
    
    for video in videos:
        title_lower = video['title'].lower()
        
        # Check if any keyword matches (skip if --all flag)
        if not skip_keyword_filter:
            has_keyword = any(kw.lower() in title_lower for kw in keywords)
            
            # Check if any exclude keyword matches
            has_exclude = any(ex.lower() in title_lower for ex in exclude) if exclude else False
            
            if not has_keyword or has_exclude:
                skipped_keyword += 1
                continue
        
        # Check date filter
        if min_date:
            video_date = video.get('parsed_date')
            if video_date is None:
                # Include videos where we can't parse the date (user can review)
                no_date_found += 1
                video['date_note'] = "Date could not be parsed from title"
            elif video_date < min_date:
                skipped_date += 1
                continue
        
        filtered.append(video)
    
    print(f"Filtered to {len(filtered)} videos")
    if skipped_keyword > 0:
        print(f"  - {skipped_keyword} videos skipped (no matching keywords)")
    if skipped_date > 0:
        print(f"  - {skipped_date} videos skipped (before {start_date})")
    if no_date_found > 0:
        print(f"  - {no_date_found} videos included but date couldn't be parsed")
    
    return filtered


def get_transcript(video_id):
    """Get transcript for a single video."""
    
    try:
        # New API (version 1.0+)
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.fetch(video_id)
        # Convert to list of dicts format
        return [{'start': snippet.start, 'text': snippet.text, 'duration': snippet.duration} for snippet in transcript_list]
    except TranscriptsDisabled:
        return None, "Transcripts disabled"
    except NoTranscriptFound:
        return None, "No transcript found"
    except Exception as e:
        return None, str(e)


def already_downloaded(video_id, output_dir=OUTPUT_DIR):
    """Check if transcript for this video already exists."""
    if not os.path.exists(output_dir):
        return False
    for filename in os.listdir(output_dir):
        if filename.startswith(video_id):
            return True
    return False


def load_failed_videos(failed_file=FAILED_FILE):
    """Load set of video IDs that previously failed (transcripts disabled, etc)."""
    if not os.path.exists(failed_file):
        return set()
    with open(failed_file, 'r') as f:
        return set(line.strip().split('#')[0].strip() for line in f if line.strip() and not line.startswith('#'))


def save_failed_video(video_id, reason, failed_file=FAILED_FILE):
    """Append a failed video ID to the failed list."""
    with open(failed_file, 'a') as f:
        f.write(f"{video_id} # {reason}\n")


def format_transcript(transcript_data, include_timestamps=True):
    """Format transcript data into readable text."""
    
    if not transcript_data or isinstance(transcript_data, tuple):
        return None
    
    lines = []
    for entry in transcript_data:
        if include_timestamps:
            # Convert seconds to HH:MM:SS
            seconds = int(entry['start'])
            timestamp = f"[{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}]"
            lines.append(f"{timestamp} {entry['text']}")
        else:
            lines.append(entry['text'])
    
    return "\n".join(lines)


def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS format."""
    return f"{int(seconds)//3600:02d}:{(int(seconds)%3600)//60:02d}:{int(seconds)%60:02d}"


def search_transcripts(search_term, transcripts_dir=OUTPUT_DIR):
    """Search all transcripts for a term and return matches with context."""
    
    results = []
    search_lower = search_term.lower()
    
    for filename in os.listdir(transcripts_dir):
        if not filename.endswith('.txt'):
            continue
            
        filepath = os.path.join(transcripts_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines):
            if search_lower in line.lower():
                # Get context (2 lines before and after)
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = "".join(lines[start:end])
                
                results.append({
                    'file': filename,
                    'line_number': i + 1,
                    'match_line': line.strip(),
                    'context': context.strip()
                })
    
    return results


def save_transcript(video_info, transcript_text, output_dir=OUTPUT_DIR):
    """Save a single transcript to a file."""
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Create safe filename from title
    safe_title = re.sub(r'[^\w\s-]', '', video_info['title'])
    safe_title = re.sub(r'\s+', '_', safe_title)[:80]
    filename = f"{video_info['video_id']}_{safe_title}.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Title: {video_info['title']}\n")
        f.write(f"Video ID: {video_info['video_id']}\n")
        f.write(f"URL: {video_info['url']}\n")
        f.write(f"Extracted: {datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
        f.write(transcript_text)
    
    return filepath


def create_combined_file(transcripts_dir=OUTPUT_DIR, output_file=COMBINED_FILE):
    """Combine all transcripts into a single searchable file."""
    
    if not os.path.exists(transcripts_dir):
        print(f"No transcripts directory found - skipping combined file creation")
        return
    
    combined = []
    
    for filename in sorted(os.listdir(transcripts_dir)):
        if not filename.endswith('.txt'):
            continue
            
        filepath = os.path.join(transcripts_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        combined.append("\n" + "=" * 80)
        combined.append(f"FILE: {filename}")
        combined.append("=" * 80 + "\n")
        combined.append(content)
    
    if combined:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(combined))
        print(f"Created combined file: {output_file}")
    else:
        print("No transcripts to combine")


def create_index(video_data, output_file=INDEX_FILE):
    """Create a CSV index of all processed videos."""
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Video ID', 'Title', 'URL', 'Transcript Status', 'Filename'])
        
        for video in video_data:
            writer.writerow([
                video['video_id'],
                video['title'],
                video['url'],
                video.get('status', 'Unknown'),
                video.get('filename', '')
            ])
    
    print(f"Created index file: {output_file}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main(skip_keyword_filter=False):
    """Main execution function."""
    
    print("=" * 60)
    print("SCIO TOWNSHIP MEETING TRANSCRIPT EXTRACTOR")
    print("=" * 60)
    print()
    
    if skip_keyword_filter:
        print("Mode: Downloading ALL videos (no keyword filter)")
        print()
    
    # Check for manual video ID list first
    if os.path.exists('video_ids.txt'):
        print("Found video_ids.txt - using manual video list")
        with open('video_ids.txt', 'r') as f:
            video_ids = [line.strip() for line in f if line.strip()]
        videos = [{'video_id': vid, 'title': f'Video {vid}', 'url': f'https://www.youtube.com/watch?v={vid}'} for vid in video_ids]
    else:
        # Get videos from channel
        videos = get_channel_videos(CHANNEL_URL)
        
        if not videos:
            print("\nNo videos found or scrapetube not available.")
            print("\nManual fallback option:")
            print("1. Go to the YouTube channel")
            print("2. Copy video IDs from URLs you want to process")
            print("3. Create a file 'video_ids.txt' with one ID per line")
            print("4. Run this script again")
            return
        
        # Filter to meeting videos
        videos = filter_meeting_videos(videos, skip_keyword_filter=skip_keyword_filter)
    
    if not videos:
        print("No meeting videos found to process.")
        return
    
    print(f"\nProcessing {len(videos)} videos...")
    print("-" * 60)
    
    # Load previously failed videos
    failed_ids = load_failed_videos()
    if failed_ids:
        print(f"Skipping {len(failed_ids)} previously failed videos (delete {FAILED_FILE} to retry)")
    
    # Process each video
    successful = 0
    failed = 0
    skipped = 0
    
    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] {video['title'][:50]}...")
        
        # Skip if already downloaded
        if already_downloaded(video['video_id']):
            print(f"  ⏭ Already downloaded, skipping")
            video['status'] = "Already downloaded"
            skipped += 1
            continue
        
        # Skip if previously failed
        if video['video_id'] in failed_ids:
            print(f"  ⏭ Previously failed, skipping")
            video['status'] = "Previously failed"
            skipped += 1
            continue
        
        # Add delay between requests to avoid rate limiting
        if i > 1:
            time.sleep(2)  # 2 second delay between requests
        
        result = get_transcript(video['video_id'])
        
        if result is None or isinstance(result, tuple):
            error = result[1] if isinstance(result, tuple) else "Unknown error"
            print(f"  ✗ Failed: {error}")
            video['status'] = f"Failed: {error}"
            # Only save permanent failures, not IP blocks
            if "Transcripts disabled" in error or "No transcript found" in error:
                save_failed_video(video['video_id'], error)
                failed_ids.add(video['video_id'])
            failed += 1
            continue
        
        # Format and save transcript
        transcript_text = format_transcript(result, include_timestamps=True)
        filepath = save_transcript(video, transcript_text)
        
        print(f"  ✓ Saved: {os.path.basename(filepath)}")
        video['status'] = "Success"
        video['filename'] = os.path.basename(filepath)
        successful += 1
    
    # Create combined file and index
    print("\n" + "-" * 60)
    create_combined_file()
    create_index(videos)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total videos processed: {len(videos)}")
    print(f"Successful: {successful}")
    print(f"Skipped (already downloaded): {skipped}")
    print(f"Failed: {failed}")
    print(f"\nOutput files:")
    print(f"  - Individual transcripts: ./{OUTPUT_DIR}/")
    print(f"  - Combined file: ./{COMBINED_FILE}")
    print(f"  - Index: ./{INDEX_FILE}")
    
    if successful > 0:
        print(f"\n✓ Ready for searching! Open {COMBINED_FILE} and use Ctrl+F")
        print(f"  or use the search_transcripts() function in Python.")


def interactive_search():
    """Interactive search mode for finding terms across all transcripts."""
    
    print("\n" + "=" * 60)
    print("TRANSCRIPT SEARCH MODE")
    print("=" * 60)
    print("Enter search terms to find across all transcripts.")
    print("Type 'quit' to exit.\n")
    
    while True:
        term = input("Search for: ").strip()
        
        if term.lower() == 'quit':
            break
        
        if not term:
            continue
        
        results = search_transcripts(term)
        
        if not results:
            print(f"  No matches found for '{term}'\n")
            continue
        
        print(f"\n  Found {len(results)} matches for '{term}':\n")
        
        for i, result in enumerate(results, 1):
            print(f"  --- Match {i} ---")
            print(f"  File: {result['file']}")
            print(f"  Context:")
            for line in result['context'].split('\n'):
                print(f"    {line}")
            print()


def count_videos():
    """Count all videos from START_DATE forward (no keyword filter)."""
    
    print("=" * 60)
    print("SCIO TOWNSHIP VIDEO COUNT")
    print("=" * 60)
    print()
    
    videos = get_channel_videos(CHANNEL_URL)
    
    if not videos:
        print("Could not retrieve videos from channel.")
        return
    
    total = len(videos)
    
    # Parse start_date
    min_date = None
    if START_DATE:
        try:
            min_date = datetime.strptime(START_DATE, "%Y-%m-%d")
        except ValueError:
            pass
    
    # Count by category
    from_date = 0
    before_date = 0
    no_date = 0
    by_type = {}
    
    for video in videos:
        video_date = video.get('parsed_date')
        
        if min_date:
            if video_date is None:
                no_date += 1
            elif video_date >= min_date:
                from_date += 1
                # Categorize by meeting type
                title = video['title']
                if 'Board of Trustees' in title or 'BOT' in title:
                    by_type['Board of Trustees'] = by_type.get('Board of Trustees', 0) + 1
                elif 'Zoning Board' in title:
                    by_type['Zoning Board of Appeals'] = by_type.get('Zoning Board of Appeals', 0) + 1
                elif 'Loch Alpine' in title:
                    by_type['Loch Alpine Sanitary'] = by_type.get('Loch Alpine Sanitary', 0) + 1
                elif 'Planning' in title:
                    by_type['Planning Commission'] = by_type.get('Planning Commission', 0) + 1
                elif 'Parks' in title:
                    by_type['Parks & Recreation'] = by_type.get('Parks & Recreation', 0) + 1
                elif 'DDA' in title:
                    by_type['DDA'] = by_type.get('DDA', 0) + 1
                elif 'Manager' in title:
                    by_type['Manager Meetings'] = by_type.get('Manager Meetings', 0) + 1
                else:
                    by_type['Other'] = by_type.get('Other', 0) + 1
            else:
                before_date += 1
    
    print(f"Total videos on channel: {total}")
    print(f"\nFrom {START_DATE} forward: {from_date}")
    print(f"Before {START_DATE}: {before_date}")
    print(f"Date not parseable: {no_date}")
    
    if by_type:
        print(f"\nBreakdown by meeting type (from {START_DATE}):")
        for mtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {mtype}: {count}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'search':
        interactive_search()
    elif len(sys.argv) > 1 and sys.argv[1] == '--count':
        count_videos()
    elif len(sys.argv) > 1 and sys.argv[1] == '--all':
        main(skip_keyword_filter=True)
    elif len(sys.argv) > 1 and sys.argv[1] == '--rebuild':
        print("Rebuilding combined transcript file...")
        create_combined_file()
        print("Done.")
    else:
        main()
