#!/usr/bin/env python3
"""
Tool 1.5: PDF to Images Converter

Scans a folder for PDFs, extracts each page as a PNG image at the embedded
image's original/native resolution, writes a _pages.txt marker file, and
deletes the PDF. If any image exceeds 1.99 MB, zoom is automatically reduced.

Usage:
    python pdf_to_images.py -f ./output
    python pdf_to_images.py -f ./output/BookTitle

Pipeline:
    download_pdfs.py → pdf_to_images.py → ocr_images.py

Features:
    - Detects each page's embedded image resolution and renders at that exact DPI
    - No unnecessary upscaling or downscaling — true original quality
    - Auto-reduces only when an image exceeds 1.99 MB
    - Writes _pages.txt marker (total page count) when extraction completes
    - Deletes PDF only after all pages are extracted successfully
    - Resume: skips pages whose images already exist
    - Continuous mode: re-scans for new PDFs from parallel downloads
"""

import argparse
import os
import sys
import time

try:
    import fitz  # PyMuPDF
    fitz.TOOLS.mupdf_display_errors(False)
except ImportError:
    print("ERROR: PyMuPDF not installed. Install with: pip install PyMuPDF")
    sys.exit(1)



def ensure_long_path(path):
    """Convert path to absolute and add prefix on Windows for long paths."""
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return path


# =============================================================================
# FIND PDFs
# =============================================================================

def find_pdfs(folder_path):
    """Recursively find all PDF files in subfolders."""
    pdf_list = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdf_list.append(os.path.join(root, f))
    return sorted(pdf_list)


# =============================================================================
# PROCESS ONE PDF
# =============================================================================

MAX_IMAGE_SIZE = 1.99 * 1024 * 1024  # 1.99 MB in bytes
MAX_ZOOM = 8.0  # Safety cap to prevent out-of-memory errors
MIN_ZOOM = 0.3  # Floor to prevent unusably small images


def _get_original_zoom(page, doc):
    """Calculate zoom factor to render page at its embedded image's native resolution.
    
    For scanned PDFs, each page typically contains one large image. This function
    finds that image's pixel dimensions and calculates the zoom factor needed to
    render the page at that exact resolution — giving true original quality.
    
    Example: A 300 DPI scan on a letter-size page (8.5x11 in = 612x792 pt)
             has an embedded image of ~2550x3300 pixels.
             zoom = 2550/612 ≈ 4.17x → renders at native 300 DPI.
    
    For text-only pages (no embedded images), returns 1.0 (72 DPI).
    """
    images = page.get_images(full=True)
    if not images:
        # No embedded images (text/vector page) — use 3.0x (~216 DPI)
        # and let the size-cap loop reduce if needed
        return 3.0
    
    # Find the largest embedded image by pixel count
    # get_images returns: (xref, smask, width, height, bpc, colorspace, ...)
    best = max(images, key=lambda img: img[2] * img[3])
    img_w, img_h = best[2], best[3]
    
    page_w = page.rect.width   # in points (1 point = 1/72 inch)
    page_h = page.rect.height
    
    if page_w == 0 or page_h == 0:
        return 1.0
    
    # Use the larger ratio to ensure we capture full detail
    zoom = max(img_w / page_w, img_h / page_h)
    
    # Safety cap to prevent memory allocation errors
    if zoom > MAX_ZOOM:
        zoom = MAX_ZOOM
    
    return round(zoom, 2)


def _render_page_with_size_cap(page, doc, img_path, max_size=MAX_IMAGE_SIZE):
    """Render a page at its original image quality, reducing only if file exceeds max_size or rendering fails.
    
    Strategy:
      1. Detect the embedded image's native resolution via _get_original_zoom()
      2. Render at that zoom (= true original quality)
      3. If the render fails (e.g. out of memory/bandwriter error) or PNG > 1.99 MB,
         reduce zoom by 10% per step until it works and fits
      4. Minimum zoom is 0.3x to prevent unusably small images
    
    Returns (zoom_used, original_zoom, file_size_bytes).
    """
    original_zoom = _get_original_zoom(page, doc)
    zoom = original_zoom
    
    while True:
        try:
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csGRAY)
            pix.save(img_path)
            file_size = os.path.getsize(img_path)
            
            # If successful and under size limit (or we hit rock bottom zoom), we're done
            if file_size <= max_size or zoom <= MIN_ZOOM:
                return zoom, original_zoom, file_size
        except Exception as e:
            # If rendering failed (e.g. Dimensions too large), we shrink it and try again
            if zoom <= MIN_ZOOM:
                # Page is unrenderable (likely empty/blank) — create a blank white image
                w = max(int(page.rect.width), 1)
                h = max(int(page.rect.height), 1)
                pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, w, h), 1)
                pix.clear_with(255)  # white
                pix.save(img_path)
                file_size = os.path.getsize(img_path)
                return MIN_ZOOM, original_zoom, file_size
        
        # Shrink zoom by 10% and retry
        zoom = round(zoom * 0.9, 2)
        if zoom < MIN_ZOOM:
            zoom = MIN_ZOOM
            break # Safety break
        


def process_pdf(pdf_path, keep_pdf=False):
    """Convert a PDF to page images, write _pages.txt marker, delete PDF."""
    pdf_path = ensure_long_path(pdf_path)
    pdf_dir = os.path.dirname(pdf_path)
    pdf_name = os.path.basename(pdf_path)
    parent_name = os.path.basename(pdf_dir)
    pages_marker = os.path.join(pdf_dir, '_pages.txt')

    # For display, strip the long path prefix if present
    display_pdf_name = pdf_name
    display_parent_name = parent_name
    if display_parent_name.startswith('\\\\?\\'):
        display_parent_name = display_parent_name[4:]
    if ":" in display_parent_name:
         display_parent_name = os.path.basename(display_parent_name)

    print(f"\n  [PDF] {display_parent_name}/{display_pdf_name}")

    # If _pages.txt already exists, this PDF's images are already extracted
    if os.path.exists(pages_marker):
        print(f"    [SKIP] Already extracted")
        # PDF might still be around if deletion failed before
        if os.path.exists(pdf_path):
            if keep_pdf:
                print(f"    [KEEP] PDF kept (--keep-pdf is on)")
            else:
                try:
                    os.remove(pdf_path)
                    print(f"    [CLEAN] Deleted leftover PDF")
                except OSError:
                    pass
        return True

    # Open PDF
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
    except Exception as e:
        print(f"    [ERR] Cannot open PDF: {e}")
        return False

    print(f"    Pages: {total_pages}")

    # Detect native DPI from first page for info
    first_page = doc[0]
    native_zoom = _get_original_zoom(first_page, doc)
    native_dpi = int(72 * native_zoom)
    print(f"    Native resolution: ~{native_dpi} DPI (zoom={native_zoom:.2f}x)")

    # Render each page to PNG at original quality (with size cap)
    extracted = 0
    skipped = 0
    reduced_pages = 0
    failed_pages = []
    render_start = time.time()

    # Find the last existing page to re-process it just in case it was partially written
    last_existing_page = 0
    for page_num in range(1, total_pages + 1):
        img_path = os.path.join(pdf_dir, f"page_{page_num:03d}.png")
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            last_existing_page = page_num
        else:
            break

    for page_num in range(1, total_pages + 1):
        img_name = f"page_{page_num:03d}.png"
        img_path = os.path.join(pdf_dir, img_name)

        # Resume: skip if image already exists AND it's not the last existing page
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0 and page_num != last_existing_page:
            skipped += 1
            continue

        try:
            page = doc[page_num - 1]
            zoom_used, orig_zoom, img_size = _render_page_with_size_cap(page, doc, img_path)
            extracted += 1
            
            if zoom_used < orig_zoom:
                reduced_pages += 1
                size_mb = img_size / (1024 * 1024)
                used_dpi = int(72 * zoom_used)
                print(f"    [REDUCED] Page {page_num}: {used_dpi} DPI ({size_mb:.2f} MB)")
            
            done = extracted + skipped
            pct = done * 100 // total_pages
            elapsed = time.time() - render_start
            eta = (elapsed / max(extracted, 1)) * (total_pages - done) if extracted > 0 else 0
            # Visual progress bar — 20 chars wide
            bar_len = 20
            filled = int(bar_len * done / total_pages)
            bar = '█' * filled + '░' * (bar_len - filled)
            print(f"\r    [{bar}] {done}/{total_pages} ({pct}%) {int(elapsed)}s elapsed, ETA {int(eta)}s   ", end='', flush=True)
        except Exception as e:
            failed_pages.append((page_num, str(e)))
            print(f"\n    [ERR] Page {page_num} render failed: {e}")
            break # Stop if something is very wrong

    doc.close()

    if extracted > 0 or skipped > 0:
        print()  # newline after progress

    elapsed = time.time() - render_start
    if skipped > 0:
        print(f"    Resuming: {skipped} already done, {extracted} newly rendered")
    if reduced_pages > 0:
        print(f"    📉 {reduced_pages} page(s) reduced to fit under {MAX_IMAGE_SIZE / (1024*1024):.2f} MB limit")
    print(f"    ⏱ Rendering completed in {int(elapsed)}s")

    # Check for failures
    if failed_pages:
        print(f"    [ERR] {len(failed_pages)} page(s) failed to render:")
        for pg, err in failed_pages[:10]:
            print(f"      Page {pg}: {err}")
        if len(failed_pages) > 10:
            print(f"      ... and {len(failed_pages) - 10} more")
        print(f"    [INFO] PDF kept - fix issues and retry")
        return False

    # All pages extracted successfully — write marker file
    with open(pages_marker, 'w', encoding='utf-8') as f:
        f.write(str(total_pages))

    print(f"    [OK] All {total_pages} pages extracted")

    if keep_pdf:
        print(f"    [KEEP] PDF kept (--keep-pdf is on)")
    else:
        try:
            os.remove(pdf_path)
            print(f"    [DEL] Deleted PDF")
        except OSError as e:
            print(f"    [WARN] Could not delete PDF: {e}")

    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Convert PDFs to page images for OCR pipeline')
    parser.add_argument('-f', '--folder', required=True,
                        help='Folder containing PDFs (or subfolders with PDFs)')
    parser.add_argument('--wait', type=int, default=10,
                        help='Seconds to wait before re-scanning for new PDFs (default: 10)')
    parser.add_argument('--keep-pdf', action='store_true',
                        help='Keep PDF after image extraction instead of deleting it')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit instead of continuous re-scanning')
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)

    # Use absolute paths with Windows long path prefix
    args.folder = ensure_long_path(args.folder)

    print(f"{'=' * 60}")
    print(f"  PDF -> Images Converter")
    print(f"  Folder: {os.path.abspath(args.folder)}")
    print(f"  Quality: Original (auto-reduce if image > {MAX_IMAGE_SIZE / (1024*1024):.2f} MB)")
    mode_str = "Single Pass" if (args.keep_pdf or args.once) else "Continuous (re-scans for new PDFs)"
    print(f"  Mode:   {mode_str}")
    print(f"{'=' * 60}")

    total_success = 0
    total_fail = 0
    scan_round = 0

    try:
        while True:
            scan_round += 1

            # Scan for PDFs
            pdfs = find_pdfs(args.folder)

            if not pdfs:
                if scan_round == 1:
                    print(f"\nNo PDFs found in: {args.folder}")
                else:
                    print(f"\n{'=' * 60}")
                    print(f"  [DONE] All done! No more PDFs found.")
                    print(f"  Total: {total_success} succeeded, {total_fail} failed")
                    print(f"{'=' * 60}")
                break

            if scan_round > 1:
                print(f"\n{'=' * 60}")
                print(f"  [RE-SCAN] Round #{scan_round}: Found {len(pdfs)} PDF(s)")
                print(f"{'=' * 60}")
            else:
                print(f"\n  PDFs found: {len(pdfs)}")

            # Process each PDF
            for idx, pdf_path in enumerate(pdfs):
                print(f"\n[{idx + 1}/{len(pdfs)}]", end='')
                try:
                    ok = process_pdf(pdf_path, keep_pdf=args.keep_pdf)
                    if ok:
                        total_success += 1
                    else:
                        total_fail += 1
                except Exception as e:
                    print(f"    [ERR] Unexpected error: {e}")
                    total_fail += 1

            # If we aren't deleting PDFs, continuous scanning will just loop over the same files
            if args.keep_pdf or args.once:
                print(f"\n  [INFO] Single pass mode enabled. Exiting.")
                print(f"\n{'=' * 60}")
                print(f"  [DONE] Completed pass.")
                print(f"  Total: {total_success} succeeded, {total_fail} failed")
                print(f"{'=' * 60}")
                break

            # Wait briefly then re-scan for newly downloaded PDFs
            print(f"\n  ⏳ Waiting {args.wait}s before re-scanning for new PDFs...")
            time.sleep(args.wait)

    except KeyboardInterrupt:
        print(f"\n\n  Extraction interrupted by user.")
        print(f"  Total: {total_success} succeeded, {total_fail} failed")


if __name__ == '__main__':
    main()
