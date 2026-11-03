#!/usr/bin/env python3
"""
Tool 1: Archive.org PDF Downloader

Downloads PDFs and metadata from archive.org links into organized subfolders.
No OCR, no tokens, no workers — just downloading.

Usage:
    python download_pdfs.py -i links.txt -o ./output

Features:
    - Atomic downloads (.part -> rename) to prevent corrupted files
    - Auto-resume: skips already-downloaded PDFs
    - Internet disconnect detection + auto-retry
    - Metadata saved (Source URL + Tags) per book
    - Multi-PDF items get sub-subfolders
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import socket

# Force IPv4 to avoid slow IPv6 timeouts on cloud instances (like Oracle Cloud)
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4


def ensure_long_path(path: str) -> str:
    """Convert path to absolute and add \\\\?\\ prefix on Windows for long paths."""
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return str(path)


# =============================================================================
# NETWORK HELPERS
# =============================================================================

def _is_network_error(error_str):
    """Check if error is a network issue."""
    e = str(error_str).lower()
    keywords = ['timeout', 'timed out', 'reset', 'refused', 'unreachable',
                'eof occurred', '10060', '10061']
    return any(kw in e for kw in keywords)


def wait_for_internet(check_url='https://www.google.com', interval=5, label=''):
    """Pause execution until internet is available."""
    prefix = f"  [{label}] " if label else "  "
    try:
        urllib.request.urlopen(check_url, timeout=5)
        return
    except Exception:
        pass

    print(f"\n{prefix}⚠ Internet disconnected. Waiting...")
    while True:
        try:
            urllib.request.urlopen(check_url, timeout=5)
            print(f"{prefix}✓ Internet restored!\n")
            return
        except Exception:
            time.sleep(interval)


# =============================================================================
# ARCHIVE.ORG HELPERS
# =============================================================================

def extract_identifier(url):
    """Extract item identifier and optional subpath (specific book) from URL.
    Returns (identifier, subpath)."""
    if not url:
        return None, None
    
    # Strip common surrounding junk like quotes or brackets
    url = url.strip(' "\'[]()<>')
    
    # Search for archive.org/details/IDENTIFIER[/SUBPATH...]
    # Identifiers usually don't contain slashes or question marks
    match = re.search(r'archive\.org/details/([^/\\?]+)(?:/(.*))?', url)
    if match:
        identifier = match.group(1).strip()
        subpath = match.group(2)
        if subpath:
            # Strip query params or fragments if any
            subpath = subpath.split('?')[0].split('#')[0].strip('/')
        return identifier, (subpath if subpath else None)
    return None, None


def get_metadata(identifier):
    """Fetch metadata from Archive.org with retries and User-Agent."""
    url = f"https://archive.org/metadata/{identifier}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if _is_network_error(e):
                wait_for_internet(label='Metadata')
            elif attempt < 2:
                time.sleep(2)
            else:
                # Show the REAL error message here
                raise Exception(f"Metadata fetch for '{identifier}' failed: {e}")
    return None # Should not reach here


def get_book_title(data):
    """Get book title from metadata."""
    t = data.get('metadata', {}).get('title')
    return t[0] if isinstance(t, list) else t


def get_tags(data):
    """Extract tags/topics from metadata."""
    tags = []
    if 'metadata' in data:
        metadata = data['metadata']
        if 'subject' in metadata:
            subject = metadata['subject']
            if isinstance(subject, list):
                tags.extend(subject)
            else:
                tags.append(subject)
    return [t.strip() for t in tags if t and isinstance(t, str)]


def sanitize_filename(name):
    """Make filename safe for Windows and other file systems."""
    # Remove control characters (0x00-0x1F)
    name = re.sub(r'[\x00-\x1f]', '', name)
    # Replace characters illegal on Windows
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Replace any remaining problematic whitespace (tabs, newlines)
    name = re.sub(r'[\t\n\r]', ' ', name)
    # Collapse multiple spaces/underscores
    name = re.sub(r'_{2,}', '_', name)
    name = re.sub(r' {2,}', ' ', name)
    # Strip trailing dots and spaces (Windows doesn't allow them)
    name = name.strip('. ')
    # Truncate
    name = name[:200]  # type: ignore
    # Handle Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    if re.match(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)(\.|$)', name, re.IGNORECASE):
        name = '_' + name
    # Fallback if empty
    return name if name else 'untitled'


def get_pdf_files(data):
    """Get list of PDF files. Returns all available PDFs (both regular and 'Additional Text PDF').
    Prioritizes regular PDFs in ordering so they're tried first if both types exist.
    Returns list of (name, size_bytes)."""
    regular_pdfs = []
    text_pdfs = []
    for f in data.get('files', []):
        if not f.get('name', '').lower().endswith('.pdf'):
            continue
        try:
            size = int(f.get('size', 0))
        except (ValueError, TypeError):
            size = 0
        entry = (f.get('name'), size)
        if f.get('format') == 'Additional Text PDF':
            text_pdfs.append(entry)
        else:
            regular_pdfs.append(entry)
    # Deduplicate: if an item has both regular and text PDFs, prevent double-downloading.
    # If they have the exact same count (e.g., 1 regular and 1 text), we assume they
    # are duplicates of the same book and only keep the regular PDF.
    if regular_pdfs and text_pdfs and len(regular_pdfs) == len(text_pdfs):
        return regular_pdfs

    # Return both regular and text PDFs, with regular PDFs first
    # This allows users to request specific text PDFs via subpath even if regular PDFs exist
    return regular_pdfs + text_pdfs


def filter_pdfs_by_subpath(pdfs, subpath):
    """Filter a list of (name, size) PDFs by a subpath string."""
    if not subpath:
        return pdfs
    
    decoded = urllib.parse.unquote(subpath).strip('/')
    if not decoded:
        return pdfs

    # Normalize: subpath might be "filename" or "filename.pdf"
    target_clean = decoded.lower()
    if target_clean.endswith('.pdf'):
        target_clean = target_clean[:-4]

    def matches(pdf_name):
        name = pdf_name.lower()
        # 1. Exact match (with .pdf)
        if name == decoded.lower():
            return True
        # 2. Match without .pdf extension
        name_no_ext = name[:-4] if name.endswith('.pdf') else name
        if name_no_ext == target_clean:
            return True
        # 3. Inside a directory with that name
        if name.startswith(target_clean + '/'):
            return True
        return False

    filtered = [p for p in pdfs if matches(p[0])]
    
    # IMPORTANT: If a subpath was provided but nothing matched, 
    # we should return an empty list (or log a warning) rather than 
    # downloading EVERYTHING, which is usually NOT what the user wanted.
    if not filtered:
        print(f"  ⚠ Warning: Subpath '{decoded}' did not match any PDF files.")
    
    return filtered


def format_size(size_bytes):
    """Format bytes into human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# =============================================================================
# DOWNLOAD
# =============================================================================

def download_pdf(identifier, pdf_filename, save_path, expected_size=0):
    """Download a PDF with progress bar. Uses .part file for atomicity."""
    # Skip if already downloaded
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        print(f"    ✓ Already exists: {os.path.basename(save_path)}")
        return True

    part_path = save_path + ".part"
    encoded_name = urllib.parse.quote(pdf_filename)
    url = f"https://archive.org/download/{identifier}/{encoded_name}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    size_label = f" [{format_size(expected_size)}]" if expected_size > 0 else ""
    print(f"    Downloading: {os.path.basename(pdf_filename)}{size_label}")

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                total_size = int(response.info().get('Content-Length', expected_size))
                
                with open(part_path, 'wb') as f:
                    downloaded = 0
                    block_size = 1024 * 64  # 64KB blocks for cloud-friendly buffering
                    
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        
                        downloaded += len(buffer)
                        f.write(buffer)
                        
                        # Progress reporting
                        if total_size > 0:
                            pct = min(100, downloaded * 100 / total_size)
                            bar = '█' * int(20 * pct / 100) + '░' * (20 - int(20 * pct / 100))
                            mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            print(f"\r    Download: {bar} {pct:5.1f}% ({mb:.1f}/{total_mb:.1f} MB)",
                                  end='', flush=True)

            if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
                raise Exception("Downloaded file is empty")
            
            os.replace(part_path, save_path)
            print()  # newline after progress bar
            return True
            
        except Exception as e:
            print()  # newline after progress bar
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
            
            if _is_network_error(e):
                wait_for_internet(label='Download')
            elif attempt == 2:
                raise
            else:
                print(f"    ⚠ Attempt {attempt+1} failed, retrying...")
                time.sleep(2)
    return False


# =============================================================================
# METADATA HELPERS
# =============================================================================

def write_metadata(meta_path, source_url, tags):
    """Write metadata.txt with Source and Tags."""
    with open(meta_path, 'w', encoding='utf-8') as f:
        f.write(f"Source: {source_url}\n")
        if tags:
            f.write(f"Tags: {', '.join(tags)}\n")


def verify_and_fix_metadata(meta_path, expected_source, tags):
    """Read back metadata.txt and ensure Source URL is correct.
    Fixes it in place if wrong. Returns True if it was already correct."""
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        # Can't read — rewrite from scratch
        write_metadata(meta_path, expected_source, tags)
        return False

    fixed = False
    new_lines = []
    has_source = False
    for line in lines:
        if line.startswith('Source:'):
            has_source = True
            current = line.replace('Source:', '').strip().rstrip('/')
            expected = expected_source.rstrip('/')
            if current != expected:
                new_lines.append(f"Source: {expected_source}\n")
                fixed = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not has_source:
        # Source line missing entirely — prepend it
        new_lines.insert(0, f"Source: {expected_source}\n")
        fixed = True

    if fixed:
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return not fixed


def verify_pdf_size(pdf_path, expected_size):
    """Verify downloaded PDF matches expected size. Returns (ok, actual_size)."""
    if expected_size <= 0:
        # No expected size from metadata — just check it's not empty
        actual = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
        return actual > 0, actual
    actual = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
    return actual == expected_size, actual


def normalize_url(url):
    """Normalize URL by decoding percent encoding, converting to lowercase, and stripping slashes/spaces."""
    if not url:
        return ""
    import urllib.parse
    decoded = urllib.parse.unquote(url).strip().lower()
    return decoded.rstrip('/')


def get_existing_library_urls(library_dir):
    """Scan library uploads folder for existing source URLs."""
    existing_urls = set()
    if not library_dir or not os.path.exists(library_dir):
        return existing_urls
        
    for folder_name in os.listdir(library_dir):
        folder_path = os.path.join(library_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
            
        metadata_path = os.path.join(folder_path, 'metadata.txt')
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Source:'):
                            source_url = line.replace('Source:', '').strip()
                            if source_url:
                                existing_urls.add(normalize_url(source_url))
                            break
            except:
                pass
    return existing_urls


# =============================================================================
# PROCESS ONE LINK
# =============================================================================

def process_link(url, output_dir, pre_meta=None, existing_urls=None):
    """Download all PDFs + metadata for a single archive.org link.
    
    Args:
        pre_meta: Pre-fetched metadata dict (from estimation phase). If None, fetches fresh.
    """
    identifier, subpath = extract_identifier(url)
    if not identifier:
        print(f"  ✗ Invalid URL: {url}")
        return False

    # Use pre-fetched metadata or fetch fresh
    if pre_meta:
        meta = pre_meta
    else:
        try:
            meta = get_metadata(identifier)
        except Exception as e:
            print(f"  ✗ Metadata fetch failed: {e}")
            return False

    title = get_book_title(meta)
    tags = get_tags(meta)
    folder_name = sanitize_filename(title) if title else identifier
    folder_path = os.path.join(output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    # Get PDF list with sizes
    pdfs = get_pdf_files(meta)
    if not pdfs:
        print(f"  ✗ No PDFs found for: {identifier}")
        return False

    # Filter PDFs by sub-path if present (subset support)
    original_count = len(pdfs)
    pdfs = filter_pdfs_by_subpath(pdfs, subpath)
    is_subset = len(pdfs) < original_count
    if is_subset:
        print(f"  (Subset filtering applied: {urllib.parse.unquote(subpath or '')})")
    elif subpath and len(pdfs) == original_count:
        print(f"  ⚠ Subset '{subpath}' not found among PDFs. Downloading all.")

    total_size = sum(size for _, size in pdfs)
    print(f"  Title: {title or identifier}")
    print(f"  PDFs:  {len(pdfs)}  |  Size: {format_size(total_size)}")
    if tags:
        print(f"  Tags:  {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")  # type: ignore

    success = True

    for pdf_name, pdf_size in pdfs:
        # Use sub-subfolders when: multiple PDFs, OR subset-filtered from a larger set
        if original_count > 1:
            base = os.path.splitext(pdf_name)[0]
            work_dir = os.path.join(folder_path, sanitize_filename(base))
            pdf_save_path = os.path.join(work_dir, sanitize_filename(base) + '.pdf')
            
            # Deep details URL uses ORIGINAL (un-sanitized) name for correct archive.org link
            encoded_basename = urllib.parse.quote(base)
            source_url = f"https://archive.org/details/{identifier}/{encoded_basename}/"
        else:
            # Truly single-PDF items use flat folders and generic details links
            work_dir = folder_path
            pdf_save_path = os.path.join(folder_path, str(folder_name) + '.pdf')
            source_url = f"https://archive.org/details/{identifier}/"

        # Skip if already in the library
        if existing_urls:
            normalized_src = normalize_url(source_url)
            if normalized_src in existing_urls:
                print(f"    ✓ Already in library (existing folder found): {pdf_name}")
                continue

        os.makedirs(work_dir, exist_ok=True)

        # Skip if already processed into images
        pages_marker = os.path.join(work_dir, '_pages.txt')
        if os.path.exists(pages_marker):
            print(f"    ✓ Already processed: {os.path.basename(work_dir)} (_pages.txt found)")
            continue

        # Write metadata.txt (or fix if it already exists with a wrong URL)
        meta_path = os.path.join(work_dir, 'metadata.txt')
        if os.path.exists(meta_path):
            was_ok = verify_and_fix_metadata(meta_path, source_url, tags)
            if not was_ok:
                print(f"    ⚡ Fixed metadata: {os.path.basename(work_dir)}")
        else:
            write_metadata(meta_path, source_url, tags)

        # Download PDF
        try:
            download_pdf(identifier, pdf_name, pdf_save_path, expected_size=pdf_size)
            print(f"    ✓ {os.path.basename(pdf_save_path)}")
        except Exception as e:
            print(f"    ✗ Failed: {os.path.basename(pdf_name)} — {e}")
            success = False

    return success


# =============================================================================
# MAIN
# =============================================================================

def parse_links(filepath):
    """Parse input file: extract all archive.org links (ignore #sections, blanks)."""
    links = []
    if not os.path.exists(filepath):
        print(f"ERROR: Input file not found: {filepath}")
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Extract URL (ignore any | metadata after it)
            url = line.split('|')[0].strip().strip(' "')
            if 'archive.org/details/' in url:
                links.append(url)
    return links


def estimate_downloads(links):
    """Fetch metadata for all links and display size estimation table.
    
    Returns list of (url, metadata_dict) for successful fetches, or None if user declines.
    """
    print(f"\n{'=' * 60}")
    print(f"  Fetching metadata for {len(links)} link(s)...")
    print(f"{'=' * 60}")

    items = []  # (url, title, num_pdfs, total_size_bytes, metadata)
    errors = []  # (url, error_msg)

    for idx, url in enumerate(links):
        identifier, subpath = extract_identifier(url)
        if not identifier:
            errors.append((url, "Invalid URL"))
            print(f"  [{idx + 1}/{len(links)}] ✗ Invalid URL: {url}")
            continue

        print(f"  [{idx + 1}/{len(links)}] Fetching: {identifier}...", end='', flush=True)
        try:
            meta = get_metadata(identifier)
            title = get_book_title(meta) or identifier
            pdfs = get_pdf_files(meta)
            
            # Apply subset filtering to estimation
            pdfs = filter_pdfs_by_subpath(pdfs, subpath)
            
            num_pdfs = len(pdfs)
            total_size = sum(size for _, size in pdfs)
            items.append((url, title, num_pdfs, total_size, meta))
            print(f" ✓ {num_pdfs} PDF(s), {format_size(total_size)}")
        except Exception as e:
            errors.append((url, str(e)))
            print(f" ✗ {e}")

    # Display summary table
    grand_total = sum(size for _, _, _, size, _ in items)
    
    print(f"\n{'=' * 60}")
    print(f"  Download Estimation")
    print(f"{'=' * 60}")
    print(f"  {'#':<4} {'Title':<35} {'PDFs':>5}  {'Size':>10}")
    print(f"  {'─' * 4} {'─' * 35} {'─' * 5}  {'─' * 10}")

    for i, (url, title, num_pdfs, total_size, _) in enumerate(items):
        title_str = str(title)
        short_title = title_str[:33] + '..' if len(title_str) > 35 else title_str  # type: ignore
        print(f"  {i + 1:<4} {short_title:<35} {num_pdfs:>5}  {format_size(total_size):>10}")

    if errors:
        print(f"\n  ⚠ {len(errors)} link(s) failed metadata fetch:")
        for url, err in errors:
            print(f"    ✗ {url} — {err}")

    print(f"  {'─' * 56}")
    print(f"  {'Total':<40} {sum(n for _, _, n, _, _ in items):>5}  {format_size(grand_total):>10}")
    print(f"{'=' * 60}")

    # Ask for confirmation
    try:
        answer = input(f"\n  Start downloading? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return None

    if answer != 'y':
        print("  Download cancelled.")
        return None

    return items


def main():
    class Args(argparse.Namespace):
        i: str
        link: str
        output: str
        fast: bool

    parser = argparse.ArgumentParser(
        description='Download PDFs and metadata from archive.org links')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('-i', help='Input file with archive.org links')
    source.add_argument('-l', '--link', help='Single archive.org link to download')
    parser.add_argument('-o', '--output', default='output',
                        help='Output directory (default: output)')
    parser.add_argument('--library-dir', help='Library uploads directory to scan for existing items to prevent duplicates')
    parser.add_argument('--fast', action='store_true',
                        help='Skip size estimation and start downloading immediately')
    args = parser.parse_args(namespace=Args())

    # Use absolute paths with Windows long path prefix
    args.output = ensure_long_path(args.output)
    os.makedirs(args.output, exist_ok=True)

    if args.link:
        links = [args.link.strip()]
        args.fast = True  # single link, no need to estimate
    else:
        links = parse_links(args.i)
    if not links:
        print("No links found.")
        sys.exit(0)

    print(f"{'=' * 60}")
    print(f"  Archive.org PDF Downloader")
    print(f"  Links: {len(links)}  |  Output: {os.path.abspath(args.output)}")
    print(f"{'=' * 60}")

    success_count: int = 0
    fail_count: int = 0
    failed_links: list[str] = []

    # Load existing library URLs if library-dir is provided
    existing_urls = set()
    if args.library_dir:
        existing_urls = get_existing_library_urls(args.library_dir)

    if args.fast:
        # Fast mode: skip estimation, download directly
        print(f"\n  ⚡ Fast mode — skipping estimation\n")

        for idx, url in enumerate(links):
            print(f"\n[{idx + 1}/{len(links)}] {url}")
            try:
                ok = process_link(url, args.output, existing_urls=existing_urls)
                if ok:
                    success_count = success_count + 1  # type: ignore
                else:
                    failed_links.append(url)
                    fail_count = fail_count + 1  # type: ignore
            except KeyboardInterrupt:
                print("\n\nDownload interrupted by user.")
                break
            except Exception as e:
                print(f"  ✗ Unexpected error: {e}")
                failed_links.append(url)
                fail_count = fail_count + 1  # type: ignore
    else:
        # Normal mode: estimate first, then download
        items = estimate_downloads(links)
        if items is None:
            sys.exit(0)
            
        assert items is not None

        print(f"\n{'=' * 60}")
        print(f"  Starting Downloads...")
        print(f"{'=' * 60}")

        for idx, (url, title, num_pdfs, total_size, meta) in enumerate(items):
            print(f"\n[{idx + 1}/{len(items)}] {url}")
            try:
                ok = process_link(url, args.output, pre_meta=meta, existing_urls=existing_urls)
                if ok:
                    success_count = success_count + 1  # type: ignore
                else:
                    failed_links.append(url)
                    fail_count = fail_count + 1  # type: ignore
            except KeyboardInterrupt:
                print("\n\nDownload interrupted by user.")
                break
            except Exception as e:
                print(f"  ✗ Unexpected error: {e}")
                failed_links.append(url)
                fail_count = fail_count + 1  # type: ignore

    print(f"\n{'=' * 60}")
    print(f"  Done!  Success: {success_count}  |  Failed: {fail_count}")
    if failed_links:
        print(f"\n  ✗ Failed links:")
        for url in failed_links:
            print(f"    {url}")
    if fail_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
