#!/usr/bin/env python3
"""
Tool 3: Retry OCR for Skipped Pages

Scans a folder for _skipped.txt files, re-OCRs only the failed pages,
and merges results into the existing text files.

Usage:
    python retry_ocr.py -f ./output
    python retry_ocr.py -f ./output/BookTitle

Features:
    - Reads _skipped.txt files to find exactly which pages need retry
    - Uses existing page images (kept from initial OCR) for retry
    - Falls back to PDF re-rendering if images are missing
    - Merges results into the existing .txt output file
    - Updates/removes _skipped.txt based on results
    - Cleans up page images after successful OCR
"""

import argparse
import os
import re
import sys
import time

# Import shared components from ocr_images
from ocr_images import (  # type: ignore
    RemoteOcrClient, process_page_ocr, load_ocr_client,
    _run_ocr_pass, _write_skip_file, _remove_skip_file, _move_to_backup
)

try:
    import fitz  # type: ignore
    fitz.TOOLS.mupdf_display_errors(False)
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


# =============================================================================
# LONG PATH SUPPORT
# =============================================================================

def ensure_long_path(path: str) -> str:
    """Convert path to absolute and add \\\\?\\ prefix on Windows for long paths."""
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return str(path)


# =============================================================================
# FIND SKIP FILES
# =============================================================================

def find_target_folders(folder_path, retry_short=False):
    """Recursively find folders that need processing."""
    targets = []
    for root, dirs, files in os.walk(folder_path):
        skip_file = None
        has_data_txt = False
        for f in files:
            if f == '_skipped.txt':
                skip_file = os.path.join(root, f)
            elif f == 'data.txt':
                has_data_txt = True
                
        if skip_file:
            targets.append((root, skip_file))
        elif retry_short and has_data_txt:
            targets.append((root, None))
            
    return sorted(targets, key=lambda x: x[0])


def parse_skip_file(skip_path):
    """Parse a _skipped.txt file. Returns (folder_name, [page_numbers], total_pages)."""
    folder_name = None
    pages = []
    total_pages = 0

    try:
        with open(skip_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('FOLDER:'):
                    folder_name = line[7:].strip()  # type: ignore
                elif line.startswith('PAGES:'):
                    page_str = line[6:].strip()  # type: ignore
                    pages = [int(p.strip()) for p in page_str.split(',') if p.strip().isdigit()]
                elif line.startswith('# Total pages:'):
                    # Parse "# Total pages: 291, Skipped: 2"
                    m = re.search(r'Total pages:\s*(\d+)', line)
                    if m:
                        total_pages = int(m.group(1))
    except Exception as e:
        print(f"    ✗ Cannot parse skip file: {e}")

    return folder_name, pages, total_pages


# =============================================================================
# PROCESS ONE SKIP FILE
# =============================================================================

def process_folder(folder_dir, skip_path, base_folder, ocr_client, max_workers, lang, retry_short=False):
    """Retry OCR for pages listed in a _skipped.txt file or with short text."""
    skip_dir = folder_dir
    folder_name = os.path.basename(skip_dir)

    print(f"\n  📋 {folder_name}")

    # Parse the skip file
    if skip_path and os.path.exists(skip_path):
        parsed_folder, pages, total_pages = parse_skip_file(skip_path)
        if not pages and not retry_short:
            print(f"    ✗ Invalid skip file (no pages found)")
            return False
    else:
        parsed_folder, pages, total_pages = None, [], 0

    if skip_path and pages:
        print(f"    Pages to retry: {len(pages)} → {', '.join(map(str, pages[:20]))}"  # type: ignore
              f"{'...' if len(pages) > 20 else ''}")

    # Find the text file in the same directory
    txt_path = os.path.join(skip_dir, 'data.txt')
    if not os.path.exists(txt_path):
        # Try to find any .txt file (not metadata.txt, not _skipped.txt)
        for f in os.listdir(skip_dir):
            if f.endswith('.txt') and f != 'metadata.txt' and not f.endswith('_skipped.txt'):
                txt_path = os.path.join(skip_dir, f)
                break

    # Load existing text content
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
                        if i + 1 < len(parts):
                            existing_content[page] = parts[i + 1].strip()
                    i += 2
        except Exception:
            pass

    # Skip pages that are already in the text file
    retry_pages = [p for p in pages if p not in existing_content]
    
    # If retry_short is enabled, add pages with < 100 chars
    short_pages = []
    if retry_short:
        for p, txt in existing_content.items():
            if len(txt.strip()) < 100 and p not in retry_pages:
                short_pages.append(p)
        retry_pages.extend(short_pages)

    if not retry_pages:
        if skip_path and os.path.exists(skip_path):
            print(f"    ✓ All skipped pages are already in text file (and no short pages found) — cleaning up")
            try:
                os.remove(skip_path)
                print(f"    🗑 Removed skip file")
            except OSError:
                pass
            _cleanup_retry_images(skip_dir, pages)
        else:
            print(f"    ✓ No short pages found to retry")
        return True

    print(f"    Retrying: {len(retry_pages)} pages" + (f" (including {len(short_pages)} short pages)" if short_pages else ""))

    # Build tasks from existing page images in the folder or backup
    tasks: list[tuple[int, str]] = []
    missing_images = []
    for page_num in retry_pages:
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(skip_dir, img_name)
        backup_img_path = os.path.join(skip_dir, 'backup', img_name)

        if os.path.exists(img_path):
            tasks.append((page_num, img_path))
        elif os.path.exists(backup_img_path):
            # Temporarily copy image from backup to main folder for processing
            import shutil
            try:
                shutil.copy2(backup_img_path, img_path)
                tasks.append((page_num, img_path))
            except OSError:
                missing_images.append(page_num)
        else:
            missing_images.append(page_num)

    # If some images are missing, try to render them from PDF
    if missing_images and HAS_FITZ:
        pdf_path = _find_pdf(skip_dir, folder_name)
        if pdf_path:
            print(f"    📄 Rendering {len(missing_images)} missing images from PDF...")
            try:
                doc = fitz.open(pdf_path)
                for page_num in missing_images:
                    if 1 <= page_num <= len(doc):
                        img_path = os.path.join(skip_dir, f"page_{page_num:03d}.png")
                        doc[page_num - 1].get_pixmap(matrix=fitz.Matrix(2, 2)).save(img_path)
                        tasks.append((page_num, img_path))
                doc.close()
            except Exception as e:
                print(f"    ⚠ Error rendering from PDF: {e}")
        elif missing_images:
            print(f"    ⚠ {len(missing_images)} page images missing and no PDF found")
    elif missing_images:
        print(f"    ⚠ {len(missing_images)} page images missing (PyMuPDF not available)")

    if not tasks:
        print(f"    ✗ No page images available for OCR")
        return False

    # OCR the pages
    results, failures, aborted = _run_ocr_pass(tasks, ocr_client, max_workers, lang, "Retry")

    # Merge results into existing content conditionally
    for page, text in results.items():
        if page in existing_content:
            if len(text.strip()) > len(existing_content[page].strip()):
                existing_content[page] = text
            else:
                # Revert text if the old one was better/longer
                pass 
        else:
            existing_content[page] = text

    # Write updated text file
    with open(txt_path, 'w', encoding='utf-8') as f:
        for page in sorted(existing_content.keys()):
            f.write(f"{{[({page})]}}\n\n{existing_content[page]}\n\n")

    # Move successfully OCR'd page images
    for page_num in results.keys():
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(skip_dir, img_name)
        _move_to_backup(skip_dir, img_path)

    # Handle results
    if failures:
        still_skipped = sorted(failures.keys())
        print(f"    ⚠ {len(results)} recovered, {len(failures)} still failing")
        print(f"    Still skipped: {', '.join(map(str, still_skipped[:20]))}"  # type: ignore
              f"{'...' if len(still_skipped) > 20 else ''}")

        # Update skip file with remaining failures
        _write_skip_file(skip_dir, total_pages or len(existing_content) + len(failures), failures)
        print(f"    📝 Updated skip file")
        return False
    else:
        print(f"    ✓ All {len(retry_pages)} retry pages recovered!")

        # Remove skip file
        if skip_path and os.path.exists(skip_path):
            try:
                os.remove(skip_path)
                print(f"    🗑 Removed skip file")
            except OSError:
                pass

        # Delete PDF if all pages are now complete and total_pages is known
        if total_pages and len(existing_content) >= total_pages:
            pdf_path = _find_pdf(skip_dir, folder_name)
            if pdf_path:
                try:
                    os.remove(pdf_path)
                    print(f"    🗑 Deleted PDF (fully complete)")
                except OSError:
                    pass
        return True


def _find_pdf(directory, folder_name):
    """Find a PDF file in the directory."""
    # Try folder_name.pdf first
    pdf_path = os.path.join(directory, folder_name + '.pdf')
    if os.path.exists(pdf_path):
        return pdf_path
    # Search for any .pdf
    for f in os.listdir(directory):
        if f.lower().endswith('.pdf'):
            return os.path.join(directory, f)
    return None


def _cleanup_retry_images(directory, pages):
    """Move page images for the given pages to backup."""
    moved: int = 0
    for page_num in pages:
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(directory, img_name)
        if os.path.exists(img_path):
            _move_to_backup(directory, img_path)
            moved = moved + 1  # type: ignore
    if moved > 0:
        print(f"    📦 Moved {moved} page image(s) to backup")


# =============================================================================
# MAIN
# =============================================================================

def main():
    class Args(argparse.Namespace):
        folder: str
        api_url: str
        api_key: str
        workers: int
        lang: str

    parser = argparse.ArgumentParser(
        description='Retry OCR for skipped pages (reads _skipped.txt files)')
    parser.add_argument('-f', '--folder', required=True,
                        help='Folder to scan for _skipped.txt files')
    parser.add_argument('--api-url', default='',
                        help='OCR API URL (default: from SAMSHO_OCR_API_URL or central server)')
    parser.add_argument('--api-key', default='',
                        help='OCR API Key (optional)')
    parser.add_argument('--workers', type=int, default=2,
                        help='Number of parallel workers (default: 2)')
    parser.add_argument('--lang', default='sa',
                        help='OCR language hint (default: sa for Sanskrit)')
    parser.add_argument('--retry-short', action='store_true',
                        help='Also retry OCR for pages with < 100 characters')
    args = parser.parse_args(namespace=Args())

    if not os.path.isdir(args.folder):
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)

    # Use absolute paths with Windows long path prefix
    args.folder = ensure_long_path(args.folder)

    # Find targets
    targets = find_target_folders(args.folder, args.retry_short)
    if not targets:
        if args.retry_short:
            print(f"No targets found (no _skipped.txt or text files) in: {args.folder}")
        else:
            print(f"No _skipped.txt files found in: {args.folder}")
        print(f"Nothing to retry!")
        sys.exit(0)

    print(f"{'=' * 60}")
    print(f"  Retry OCR — Skipped Pages")
    print(f"  Folder: {os.path.abspath(args.folder)}")
    print(f"  Folders to process: {len(targets)}")
    print(f"  Language: {args.lang}")
    print(f"{'=' * 60}")

    # List all targets
    for i, (folder_dir, sf) in enumerate(targets):
        rel = os.path.relpath(folder_dir, args.folder)
        if sf:
            _, pages, _ = parse_skip_file(sf)
            print(f"  {i + 1}. {rel} (skip file: {len(pages)} pages)")
        else:
            print(f"  {i + 1}. {rel} (checking for short pages)")

    # Load OCR client
    ocr_client = load_ocr_client(args.api_url, args.api_key)

    # Process each folder
    success_count: int = 0
    fail_count: int = 0

    try:
        for idx, (folder_dir, skip_path) in enumerate(targets):
            print(f"\n[{idx + 1}/{len(targets)}]", end='')
            try:
                ok = process_folder(
                    folder_dir, skip_path, args.folder, ocr_client, args.workers, args.lang, args.retry_short)
                if ok:
                    success_count = success_count + 1  # type: ignore
                else:
                    fail_count = fail_count + 1  # type: ignore
            except Exception as e:
                print(f"    ✗ Unexpected error: {e}")
                fail_count = fail_count + 1  # type: ignore
    except KeyboardInterrupt:
        print(f"\n\n  Retry interrupted by user.")

    print(f"\n{'=' * 60}")
    print(f"  Retry Done!  Recovered: {success_count}  |  Still failing: {fail_count}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
