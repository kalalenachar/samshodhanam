#!/usr/bin/env python3
"""
Tool 2.5: Image OCR Processor

Scans a folder for _pages.txt marker files (from pdf_to_images.py),
OCRs all page images via Central Samshodhanam Cloud OCR API, writes combined text output,
and cleans up images after successful OCR.

Usage:
    python ocr_images.py -f ./output
    python ocr_images.py -f ./output/BookTitle

Pipeline:
    download_pdfs.py → pdf_to_images.py → ocr_images.py

Features:
    - Parallel OCR processing via thread pool
    - Resume: skips already-OCR'd pages in existing .txt files
    - Auto-retry: failed pages get retried once before being skipped
    - Skip tracking: writes _skipped.txt with failed page details
    - Deletes page images after successful OCR
    - Deletes _pages.txt marker after all pages are processed
    - Rate limit handling (60s cooldown on 429 errors)
    - Internet disconnect detection + auto-retry
    - Continuous mode: re-scans for new _pages.txt markers
"""

import argparse
import datetime
import concurrent.futures
import io
import os
import queue
import re
import shutil
import sys
import time
import urllib.request

import requests

# Add project root to sys.path so we can import time_utils
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)
from time_utils import get_ist_now


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
# LONG PATH SUPPORT
# =============================================================================

def ensure_long_path(path: str) -> str:
    """Convert path to absolute and add \\\\?\\ prefix on Windows for long paths."""
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return path


def _move_to_backup(folder_path: str, img_path: str):
    """Move the given image to a 'backup' subdirectory."""
    if not os.path.exists(img_path):
        return
    backup_dir = os.path.join(folder_path, 'backup')
    os.makedirs(backup_dir, exist_ok=True)
    dst_path = os.path.join(backup_dir, os.path.basename(img_path))
    try:
        if os.path.exists(dst_path):
            os.remove(dst_path)
        shutil.move(img_path, dst_path)
    except OSError:
        pass


# =============================================================================
# SAMSHODHANAM CLOUD OCR CLIENT
# =============================================================================

class RemoteOcrClient:
    """Client for Samshodhanam Cloud OCR API."""

    def __init__(self, api_url=None, api_key=None):
        self.api_url = api_url or os.environ.get('SAMSHO_OCR_API_URL', 'http://localhost:5001/api/v1/ocr')
        self.api_key = api_key or os.environ.get('SAMSHO_OCR_API_KEY', '')

    def ocr_image(self, img_path, lang='sa'):
        """Upload image to Samshodhanam Cloud OCR API and retrieve text."""
        headers = {}
        if self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"
            headers['X-API-Key'] = self.api_key

        with open(img_path, 'rb') as f:
            files = {'file': (os.path.basename(img_path), f)}
            data = {'lang': lang}
            resp = requests.post(self.api_url, headers=headers, data=data, files=files, timeout=60)

        if resp.status_code == 200:
            return resp.json().get('text', '').lstrip('\ufeff').strip()
        else:
            raise Exception(f"OCR API returned HTTP {resp.status_code}: {resp.text[:120]}")


# =============================================================================
# OCR WORKER
# =============================================================================

def process_page_ocr(task, ocr_client, results, failures, lang, print_queue=None):
    """Worker function: OCR a single page image."""
    page_num, img_path = task
    try:
        txt = ocr_client.ocr_image(img_path, lang=lang)
        if txt:
            results[page_num] = txt
            _move_to_backup(os.path.dirname(img_path), img_path)
        else:
            failures[page_num] = "Empty OCR result"
            if print_queue:
                print_queue.put(f"\n    ⚠ Page {page_num:03d} skipped: Empty OCR result")
    except Exception as e:
        failures[page_num] = str(e)
        if print_queue:
            err_msg = str(e).replace('\n', ' ')[:100]
            print_queue.put(f"\n    ⚠ Page {page_num:03d} skipped: {err_msg}")


# =============================================================================
# FIND READY FOLDERS
# =============================================================================

def find_ready_folders(folder_path):
    """Recursively find all _pages.txt marker files (signals extraction complete).
    Returns list of (folder_path, total_pages)."""
    ready = []
    for root, dirs, files in os.walk(folder_path):
        if '_pages.txt' in files:
            marker_path = os.path.join(root, '_pages.txt')
            try:
                with open(marker_path, 'r', encoding='utf-8') as f:
                    total_pages = int(f.read().strip())
                ready.append((root, total_pages))
            except (ValueError, OSError) as e:
                print(f"  ⚠ Bad _pages.txt in {root}: {e}")
    return sorted(ready)


# =============================================================================
# PROCESS ONE FOLDER
# =============================================================================

def _run_ocr_pass(tasks, ocr_client, max_workers, lang, pass_label="OCR"):
    """Run OCR on a list of (page_num, img_path) tasks. Returns (results, failures)."""
    results: dict[int, str] = {}
    failures: dict[int, str] = {}
    print_queue = queue.Queue()

    ocr_start = time.time()
    print(f"    {pass_label}: 0/{len(tasks)} (0%)", end='', flush=True)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(process_page_ocr, t, ocr_client, results, failures, lang, print_queue)  # type: ignore
                for t in tasks
            ]
            done_count = 0
            for _ in concurrent.futures.as_completed(futures):  # type: ignore
                # Drain and print any error messages before redrawing the progress bar
                while not print_queue.empty():
                    msg = print_queue.get()
                    # Print message and clear the line so it doesn't overwrite
                    print(msg + " " * 40)
                                
                done_count = done_count + 1
                pct = done_count * 100 // len(tasks)
                elapsed = time.time() - ocr_start
                eta = (elapsed / done_count) * (len(tasks) - done_count) if done_count > 0 else 0
                print(f"\r    {pass_label}: {done_count}/{len(tasks)} ({pct}%) [{int(elapsed)}s elapsed, ETA {int(eta)}s]   ", end='', flush=True)

        # Final drain just in case
        while not print_queue.empty():
            msg = print_queue.get()
            print(msg + " " * 40)

        elapsed = time.time() - ocr_start
        print(f"\n    ⏱ {pass_label} completed in {int(elapsed)}s")
        return results, failures, False
    except KeyboardInterrupt:
        print(f"\n\n  [!] OCR interrupted by user. Stopping current pass and saving progress...")
        # Cancel all pending futures that haven't started yet
        for f in futures:
            f.cancel()
        return results, failures, True


def _write_skip_file(folder_path, total_pages, skipped_failures):
    """Write a _skipped.txt file listing permanently failed pages."""
    skip_path = os.path.join(folder_path, '_skipped.txt')
    folder_name = os.path.basename(folder_path)
    now = get_ist_now().strftime('%Y-%m-%d %H:%M:%S')
    sorted_pages = sorted(skipped_failures.keys())

    with open(skip_path, 'w', encoding='utf-8') as f:
        f.write(f"# Skipped Pages - {folder_name}\n")
        f.write(f"# Generated: {now}\n")
        f.write(f"# Total pages: {total_pages}, Skipped: {len(sorted_pages)}\n")
        f.write(f"FOLDER: {folder_name}\n")
        f.write(f"PAGES: {', '.join(map(str, sorted_pages))}\n")
        for pg in sorted_pages:
            error_str = str(skipped_failures[pg]).replace('\n', ' ')
            error_msg = error_str[:200]  # type: ignore
            f.write(f"ERROR_{pg}: {error_msg}\n")

    return skip_path


def _remove_skip_file(folder_path):
    """Remove the _skipped.txt file if it exists."""
    skip_path = os.path.join(folder_path, '_skipped.txt')
    if os.path.exists(skip_path):
        try:
            os.remove(skip_path)
        except OSError:
            pass


def process_folder(folder_path, total_pages, ocr_client, max_workers, lang):
    """OCR all page images in a folder."""
    folder_name = os.path.basename(folder_path)
    parent_name = os.path.basename(os.path.dirname(folder_path))

    # Find the text output file name
    txt_name = 'data.txt'
    txt_path = os.path.join(folder_path, txt_name)

    print(f"\n  📁 {parent_name}/{folder_name}")
    print(f"    Pages: {total_pages}")

    # Determine which pages need OCR (resume support)
    done_pages = set()
    existing_content: dict[int, str] = {}
    if os.path.exists(txt_path):
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
                parts = re.split(r'\{\[\((\d+)\)\]\}', content)
                i = 1
                while i < len(parts):
                    if parts[i].isdigit():
                        page = int(parts[i])
                        done_pages.add(page)
                        if i + 1 < len(parts):
                            existing_content[page] = parts[i + 1].strip()
                    i += 2
        except Exception:
            pass

    todo_pages = [p for p in range(1, total_pages + 1) if p not in done_pages]

    if not todo_pages:
        print(f"    ✓ All pages already OCR'd — skipping")
        # Clean up images and marker
        _cleanup_images(folder_path, total_pages)
        _remove_skip_file(folder_path)
        _remove_marker(folder_path)
        return True

    if done_pages:
        print(f"    Resuming: {len(done_pages)} done, {len(todo_pages)} remaining")

    # Build tasks from existing page images
    tasks: list[tuple[int, str]] = []
    missing_images = []
    for page_num in todo_pages:
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(folder_path, img_name)
        if os.path.exists(img_path):
            tasks.append((page_num, img_path))
        else:
            missing_images.append(page_num)

    if missing_images:
        print(f"    ⚠ {len(missing_images)} page image(s) missing — they may still be rendering")
        if not tasks:
            print(f"    No images ready for OCR — skipping this folder for now")
            return False

    if not tasks:
        print(f"    No page images found — skipping")
        return False

    # ── Pass 1: OCR all pages ──
    results, failures, aborted = _run_ocr_pass(tasks, ocr_client, max_workers, lang, "OCR")

    # ── Pass 2: Retry failed pages (skip if aborted) ──
    if failures and not aborted:
        failed_pages = sorted(failures.keys())
        print(f"    ⚠ {len(failures)} pages failed — retrying...")

        retry_tasks = []
        for page_num in failed_pages:
            img_name = f"page_{page_num:03d}.png"
            img_path = os.path.join(folder_path, img_name)
            if os.path.exists(img_path):
                retry_tasks.append((page_num, img_path))

        if retry_tasks:
            retry_results, retry_failures, retry_aborted = _run_ocr_pass(
                retry_tasks, ocr_client, max_workers, lang, "Retry")

            if retry_aborted:
                aborted = True

            # Merge retry successes
            for pg, txt in retry_results.items():
                results[pg] = txt
                failures.pop(pg, None)

            # Update failures
            for pg, err in retry_failures.items():
                failures[pg] = err

    if aborted:
        # If interrupted, treat any unprocessed tasks as failures to trigger the skip file
        for page_num, _ in tasks:
            if page_num not in results and page_num not in failures:
                failures[page_num] = "Interrupted by user"

    # Merge results with existing content
    all_content: dict[int, str] = dict(existing_content)  # type: ignore
    for page, text in results.items():
        all_content[page] = text

    # Write output text file
    with open(txt_path, 'w', encoding='utf-8') as f:
        for page in sorted(all_content.keys()):
            f.write(f"{{[({page})]}}\n\n{all_content[page]}\n\n")

    # Move successfully OCR'd page images to backup
    for page_num in results.keys():
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(folder_path, img_name)
        _move_to_backup(folder_path, img_path)

    # Also move images for already-done pages to backup
    for page_num in done_pages:
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(folder_path, img_name)
        _move_to_backup(folder_path, img_path)

    # Report results
    if failures or missing_images or aborted:
        all_failures: dict[int, str] = dict(failures)  # type: ignore
        for pg in missing_images:
            if pg not in all_content:
                all_failures[pg] = "Image not found"

        if all_failures:
            skipped_pages = sorted(all_failures.keys())
            if aborted:
                print(f"    ⚠ Aborted. Partial: {len(results)} succeeded, {len(all_failures)} skipped/pending")
            else:
                print(f"    ⚠ Partial: {len(results)} succeeded, {len(all_failures)} skipped")
            print(f"    Skipped pages: {', '.join(map(str, skipped_pages[:20]))}")  # type: ignore
            if len(skipped_pages) > 20:
                print(f"    ... and {len(skipped_pages) - 20} more")

            skip_path = _write_skip_file(folder_path, total_pages, all_failures)
            print(f"    📝 Skip file: {os.path.basename(skip_path)}")
            print(f"    📌 Images kept for failed/pending pages")
            _remove_marker(folder_path)
            
            if aborted:
                sys.exit(1)
            return False
        else:
            # Missing images but all found pages are done
            print(f"    ✓ All available pages OCR'd ({len(results)} new)")
            _remove_skip_file(folder_path)
            if len(all_content) == total_pages:
                _cleanup_images(folder_path, total_pages)
                _remove_marker(folder_path)
            
            if aborted:
                sys.exit(1)
            return True
    else:
        print(f"    ✓ All {len(tasks)} pages OCR'd successfully")
        _remove_skip_file(folder_path)
        if len(all_content) == total_pages:
            _cleanup_images(folder_path, total_pages)
            _remove_marker(folder_path)
        return True


def _cleanup_images(folder_path, total_pages):
    """Move all page images in the folder to backup."""
    moved: int = 0
    for page_num in range(1, total_pages + 1):
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(folder_path, img_name)
        if os.path.exists(img_path):
            _move_to_backup(folder_path, img_path)
            moved = moved + 1  # type: ignore
    if moved > 0:
        print(f"    📦 Moved {moved} page image(s) to backup")


def _remove_marker(folder_path):
    """Delete the _pages.txt marker file."""
    marker_path = os.path.join(folder_path, '_pages.txt')
    try:
        if os.path.exists(marker_path):
            os.remove(marker_path)
            print(f"    🗑 Removed _pages.txt marker")
    except OSError:
        pass


# =============================================================================
# MAIN
# =============================================================================

def load_ocr_client(api_url=None, api_key=None):
    """Initializes client for Samshodhanam OCR API."""
    url = api_url or os.environ.get('SAMSHO_OCR_API_URL', 'http://localhost:5001/api/v1/ocr')
    key = api_key or os.environ.get('SAMSHO_OCR_API_KEY', '')
    print(f"Using OCR API: {url}")
    return RemoteOcrClient(url, key)


def main():
    class Args(argparse.Namespace):
        folder: str
        api_url: str
        api_key: str
        workers: int
        lang: str

    parser = argparse.ArgumentParser(
        description='OCR page images using Samshodhanam Cloud OCR API')
    parser.add_argument('-f', '--folder', required=True,
                        help='Folder to scan for _pages.txt markers')
    parser.add_argument('--api-url', default='',
                        help='OCR API URL (default: from SAMSHO_OCR_API_URL or central server)')
    parser.add_argument('--api-key', default='',
                        help='OCR API Key (optional)')
    parser.add_argument('--workers', type=int, default=2,
                        help='Number of parallel workers (default: 2)')
    parser.add_argument('--lang', default='sa',
                        help='OCR language hint (default: sa for Sanskrit)')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit instead of continuous re-scanning')
    args = parser.parse_args(namespace=Args())

    if not os.path.isdir(args.folder):
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)

    # Use absolute paths with Windows long path prefix
    args.folder = ensure_long_path(args.folder)

    print(f"{'=' * 60}")
    print(f"  Image OCR Processor")
    print(f"  Folder: {os.path.abspath(args.folder)}")
    print(f"  Language: {args.lang}")
    mode_str = "Single Pass" if args.once else "Continuous (re-scans for new _pages.txt markers)"
    print(f"  Mode:   {mode_str}")
    print(f"{'=' * 60}")

    # Load OCR client
    ocr_client = load_ocr_client(args.api_url, args.api_key)

    total_success: int = 0
    total_fail: int = 0
    scan_round: int = 0

    try:
        while True:
            scan_round = scan_round + 1

            # Scan for ready folders
            ready = find_ready_folders(args.folder)

            if not ready:
                if scan_round == 1:
                    print(f"\nNo _pages.txt markers found in: {args.folder}")
                else:
                    print(f"\n{'=' * 60}")
                    print(f"  ✓ All done! No more images to OCR.")
                    print(f"  Total: {total_success} succeeded, {total_fail} failed")
                    print(f"{'=' * 60}")
                break

            if scan_round > 1:
                print(f"\n{'─' * 60}")
                print(f"  🔄 Re-scan #{scan_round}: Found {len(ready)} folder(s) ready")
                print(f"{'─' * 60}")
            else:
                print(f"\n  Folders ready for OCR: {len(ready)}")

            # Process each ready folder
            for idx, (fpath, total_pages) in enumerate(ready):
                print(f"\n[{idx + 1}/{len(ready)}]", end='')
                try:
                    ok = process_folder(
                        fpath, total_pages, ocr_client, args.workers, args.lang)
                    if ok:
                        total_success = total_success + 1  # type: ignore
                    else:
                        total_fail = total_fail + 1  # type: ignore
                except Exception as e:
                    print(f"    ✗ Unexpected error: {e}")
                    total_fail = total_fail + 1  # type: ignore

            if args.once:
                print(f"\n  [INFO] Single pass mode enabled. Exiting.")
                print(f"\n{'=' * 60}")
                print(f"  ✓ Completed pass.")
                print(f"  Total: {total_success} succeeded, {total_fail} failed")
                print(f"{'=' * 60}")
                break

            # Wait briefly then re-scan
            print(f"\n  ⏳ Waiting {args.wait}s before re-scanning...")
            time.sleep(args.wait)

    except KeyboardInterrupt:
        print(f"\n\n  OCR interrupted by user.")
        print(f"  Total: {total_success} succeeded, {total_fail} failed")


if __name__ == '__main__':
    main()
