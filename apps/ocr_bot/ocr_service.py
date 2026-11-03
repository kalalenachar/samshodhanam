"""
OCR Service Client for Samshodhanam Telegram OCR Bot.
Connects directly to the Central Samshodhanam Cloud OCR API.
Handles:
1. Central Samshodhanam Cloud OCR API Client
2. Multi-Page PDF Processing with Page Markers
"""

import os
import sys
import io
import time
import tempfile
import threading
import logging
from typing import List, Dict, Any, Callable, Optional

try:
    import apps.ocr_bot.config as config
except ImportError:
    import config


logger = logging.getLogger("ocr_service")

import requests

# Try importing fitz (PyMuPDF)
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    fitz = None
    HAS_FITZ = False


def get_ocr_api_url() -> str:
    """Returns the configured Samshodhanam OCR API URL."""
    return getattr(config, 'SAMSHO_OCR_API_URL', 'http://localhost:5001/api/v1/ocr')


def call_remote_ocr_api(image_path: str, ocr_lang: Optional[str] = None) -> Optional[str]:
    """Submits image to Central Samshodhanam Cloud OCR API."""
    api_url = get_ocr_api_url()
    api_key = getattr(config, 'SAMSHO_OCR_API_KEY', '')

    headers = {}
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"
        headers['X-API-Key'] = api_key

    data = {}
    if ocr_lang:
        data['lang'] = ocr_lang

    try:
        with open(image_path, 'rb') as f:
            files = {'file': (os.path.basename(image_path), f)}
            resp = requests.post(api_url, headers=headers, data=data, files=files, timeout=60)
        if resp.status_code == 200:
            res_json = resp.json()
            txt = res_json.get('text', '').lstrip('\ufeff').strip()
            if txt:
                return txt
        else:
            logger.warning(f"OCR API returned HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        logger.warning(f"Failed to reach OCR API: {e}")

    return None


def process_single_image(image_path: str, ocr_lang: Optional[str] = None) -> str:
    """Processes a single image through the Central Samshodhanam Cloud OCR API."""
    txt = call_remote_ocr_api(image_path, ocr_lang)
    if txt:
        return txt

    return "[OCR Notice: Unable to extract text or remote OCR service is unavailable]"


def process_ocr_file(file_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
    """
    Main entry point to process an image or multi-page PDF document.
    - Unlimited pages for PDF.
    - Returns formatted text with page markers.
    """
    # Process file
    ext = os.path.splitext(file_path)[1].lower()

    # 3. Check if PDF
    if ext == '.pdf':
        if not HAS_FITZ:
            raise Exception("PyMuPDF (fitz) is required to process PDF files.")

        doc = fitz.open(file_path)
        total_pages = len(doc)
        results = []

        work_dir = tempfile.mkdtemp(prefix="pdf_ocr_")
        try:
            for page_num in range(total_pages):
                if progress_callback:
                    try:
                        progress_callback(page_num + 1, total_pages)
                    except Exception:
                        pass

                page = doc[page_num]
                
                # Check if PDF already has embedded text layer
                embedded_text = page.get_text()
                if embedded_text and len(embedded_text.strip()) > 150:
                    results.append(f"========== PAGE {page_num + 1} ==========\n\n{embedded_text.strip()}\n")
                    continue

                # Render page image at high resolution (300 DPI)
                pix = page.get_pixmap(dpi=200)
                img_file = os.path.join(work_dir, f"page_{page_num + 1}.png")
                pix.save(img_file)

                # Process image
                ocr_text = process_single_image(img_file)
                results.append(f"========== PAGE {page_num + 1} ==========\n\n{ocr_text.strip()}\n")
        finally:
            doc.close()
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)

        return "\n".join(results)

    else:
        # Single image processing
        if progress_callback:
            progress_callback(1, 1)
        ocr_text = process_single_image(file_path)
        return ocr_text.strip()
