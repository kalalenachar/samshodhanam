#!/usr/bin/env python3
"""
Rigveda Complete Data Scraper & Audio Archiver
Extracts all 10 Mandalas (1,028 Suktas, 10,552 Riks), Padapatha, Sayana Bhashya,
verse metadata, audio MP3s, and ancillary texts from rigveda.sanatana.in.
"""

import os
import sys
import re
import ssl
import time
import json
import sqlite3
import argparse
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'rigveda.db')
AUDIO_DIR = os.path.join(BASE_DIR, 'audio')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

BASE_URL = "https://rigveda.sanatana.in/"

# SSL context for macOS python compatibility
SSL_CTX = ssl._create_unverified_context()

# Sanskrit / Devanagari digit converter
DEVA_DIGITS = {'०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
               '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'}

def deva_to_int(text):
    if not text:
        return None
    cleaned = ''.join(DEVA_DIGITS.get(ch, ch) for ch in str(text))
    match = re.search(r'\d+', cleaned)
    return int(match.group(0)) if match else None

def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def get_html(url, retries=4, delay=1.0):
    """Fetch URL content with retry logic and standard user agent."""
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,sa;q=0.8'
        }
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                print(f"[Error fetching {url}]: {e}", file=sys.stderr)
                return None

def download_audio_file(audio_url, local_path, retries=3):
    """Download single MP3 file if not already present."""
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
        return True

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    req = urllib.request.Request(
        audio_url,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=25) as resp:
                data = resp.read()
                if len(data) > 500:
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    return True
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.0)
    return False

def clean_html(text):
    """Strip tags and normalize whitespace."""
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = ' '.join(text.split())
    return text.strip()

def scrape_rik_details(mandala, sukta, rik, download_audio=True):
    """Scrape details for a single Rik coordinate."""
    rik_id = f"{mandala}.{sukta}.{rik}"
    url = f"{BASE_URL}describe/rikMandala/{rik_id}"
    html = get_html(url)
    if not html:
        return None

    # 1. Samhita
    samhita_m = re.search(r'<p class=\"rik samhita\">(.*?)</p>', html, re.DOTALL)
    samhita = clean_html(samhita_m.group(1)) if samhita_m else ''

    # 2. Padapatha
    pada_m = re.search(r'<p class=\"rik pada-paatha\">(.*?)</p>', html, re.DOTALL)
    padapatha = clean_html(pada_m.group(1)) if pada_m else ''

    # 3. Sayana Bhashya
    sayana_m = re.search(r'<div class=\"sayanaBhashya\">(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
    sayana = clean_html(sayana_m.group(1)) if sayana_m else ''

    # 4. Aux metadata
    def get_aux(label):
        m = re.search(rf'<li>\s*<span class=\"dt\">{label}</span>\s*&nbsp;\s*<span class=\"dd\">(.*?)</span>\s*</li>', html, re.DOTALL)
        return clean_html(m.group(1)) if m else ''

    rishi = get_aux('ऋषिः')
    devata = get_aux('देवता')
    chandas = get_aux('छन्दः')
    anuvaka = deva_to_int(get_aux('अनुवाकः'))
    ashtaka = deva_to_int(get_aux('अष्टकः'))
    adhyaya = deva_to_int(get_aux('अध्यायः'))
    varga = deva_to_int(get_aux('वर्गः'))

    # 5. Audio
    audio_url = f"{BASE_URL}rigveda-audio/{mandala:03d}/{sukta:03d}/{rik:03d}.mp3"
    audio_local_rel = f"{mandala:03d}/{sukta:03d}/{rik:03d}.mp3"
    audio_local_abs = os.path.join(AUDIO_DIR, f"{mandala:03d}", f"{sukta:03d}", f"{rik:03d}.mp3")

    if download_audio:
        download_audio_file(audio_url, audio_local_abs)

    return {
        'id': rik_id,
        'mandala': mandala,
        'sukta': sukta,
        'rik': rik,
        'ashtaka': ashtaka,
        'adhyaya': adhyaya,
        'varga': varga,
        'anuvaka': anuvaka,
        'rishi': rishi,
        'devata': devata,
        'chandas': chandas,
        'samhita': samhita,
        'padapatha': padapatha,
        'sayana_bhashya': sayana,
        'audio_url': audio_url,
        'audio_file': audio_local_rel if os.path.exists(audio_local_abs) else None
    }

class RigvedaScraper:
    def __init__(self, workers=6, download_audio=True):
        self.workers = workers
        self.download_audio = download_audio
        self.db_lock = threading.Lock()
        init_db()

    def get_existing_rik_ids(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM riks")
        rows = cursor.fetchall()
        conn.close()
        return {r[0] for r in rows}

    def save_riks_batch(self, batch):
        """Save a batch of scraped riks to SQLite."""
        if not batch:
            return
        with self.db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            for r in batch:
                cur.execute("""
                    INSERT OR REPLACE INTO riks (
                        id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka,
                        rishi, devata, chandas, samhita, padapatha, sayana_bhashya,
                        audio_url, audio_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['id'], r['mandala'], r['sukta'], r['rik'], r['ashtaka'],
                    r['adhyaya'], r['varga'], r['anuvaka'], r['rishi'], r['devata'],
                    r['chandas'], r['samhita'], r['padapatha'], r['sayana_bhashya'],
                    r['audio_url'], r['audio_file']
                ))

                # Update FTS
                cur.execute("DELETE FROM riks_fts WHERE id = ?", (r['id'],))
                cur.execute("""
                    INSERT INTO riks_fts (
                        id, mandala, sukta, rik, samhita, padapatha, sayana_bhashya,
                        rishi, devata, chandas
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['id'], r['mandala'], r['sukta'], r['rik'], r['samhita'],
                    r['padapatha'], r['sayana_bhashya'], r['rishi'], r['devata'],
                    r['chandas']
                ))
            conn.commit()
            conn.close()

    def get_suktas_for_mandala(self, mandala, retries=3):
        """Get list of sukta numbers for a mandala with retries."""
        url = f"{BASE_URL}listing/sukta?mandala={mandala}"
        for attempt in range(retries):
            html = get_html(url)
            if html:
                suktas = []
                for m in re.finditer(r'data-sukta=\"(\d+)\"', html):
                    s_num = int(m.group(1))
                    if s_num not in suktas:
                        suktas.append(s_num)
                if suktas:
                    return sorted(suktas)
            time.sleep(1.0)
        return []

    def get_riks_for_sukta(self, mandala, sukta, retries=3):
        """Get list of rik coordinates for a sukta with retries."""
        url = f"{BASE_URL}listing/rikMandala?mandala={mandala}&sukta={sukta}"
        for attempt in range(retries):
            html = get_html(url)
            if html:
                riks = []
                for m in re.finditer(r'<li\s+id=\"(\d+)\.(\d+)\.(\d+)\"', html):
                    r_num = int(m.group(3))
                    if r_num not in riks:
                        riks.append(r_num)
                if riks:
                    return sorted(riks)
            time.sleep(1.0)
        return []

    def scrape_mandala(self, mandala):
        """Scrape all suktas and riks for a specific mandala."""
        existing_ids = self.get_existing_rik_ids()
        suktas = self.get_suktas_for_mandala(mandala)
        print(f"📖 Mandala {mandala}: Found {len(suktas)} suktas.")

        # Update mandalas table
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO mandalas (id, mandala, total_suktas) VALUES (?, ?, ?)",
                     (mandala, mandala, len(suktas)))
        conn.commit()
        conn.close()

        total_scraped_mandala = 0

        for s_idx, sukta in enumerate(suktas, 1):
            riks = self.get_riks_for_sukta(mandala, sukta)
            # Update suktas table
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO suktas (id, mandala, sukta, total_riks) VALUES (?, ?, ?, ?)",
                         (f"{mandala}.{sukta}", mandala, sukta, len(riks)))
            conn.commit()
            conn.close()

            # Filter un-scraped riks
            needed_riks = [r for r in riks if f"{mandala}.{sukta}.{r}" not in existing_ids]

            if not needed_riks:
                continue

            sukta_batch = []
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = {
                    executor.submit(scrape_rik_details, mandala, sukta, r, self.download_audio): r
                    for r in needed_riks
                }
                for f in as_completed(futures):
                    res = f.result()
                    if res:
                        sukta_batch.append(res)
                        existing_ids.add(res['id'])

            self.save_riks_batch(sukta_batch)
            total_scraped_mandala += len(sukta_batch)
            print(f"  [Mandala {mandala} | Sukta {sukta}/{len(suktas)}] Scraped {len(sukta_batch)}/{len(riks)} riks. (Total saved: {total_scraped_mandala})")

        print(f"✅ Finished Mandala {mandala}. Total riks scraped: {total_scraped_mandala}")

    def scrape_all(self):
        """Scrape all 10 mandalas."""
        print("🚀 Starting Complete Rigveda Archive Scraper...")
        for m in range(1, 11):
            self.scrape_mandala(m)
        print("🎉 Rigveda core scraping complete!")

    def scrape_ancillary_texts(self):
        """Scrape Niruktam, Aitareya Brahmana, and Brihaddevata."""
        print("📜 Scraping Ancillary Texts (Niruktam, Aitareya Brahmana, Brihaddevata)...")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 1. Niruktam
        nirukta_url = f"{BASE_URL}" + urllib.parse.quote("निरुक्तम्/")
        nirukta_html = get_html(nirukta_url)
        if nirukta_html:
            content_m = re.search(r'<div class=\"container-fluid maintext\">(.*?)<footer', nirukta_html, re.DOTALL)
            c_text = clean_html(content_m.group(1)) if content_m else ''
            cur.execute("""
                INSERT OR REPLACE INTO ancillary_texts (id, text_name, section, title, content)
                VALUES (?, ?, ?, ?, ?)
            """, ("niruktam_main", "niruktam", "प्रथमाष्टकः - प्रथमाध्यायः", "निरुक्तम्", c_text))

        # 2. Aitareya Brahmana
        aitareya_url = f"{BASE_URL}listing/aitareya_brahmana"
        ait_html = get_html(aitareya_url)
        if ait_html:
            content_m = re.search(r'<div class=\"container-fluid maintext\">(.*?)<footer', ait_html, re.DOTALL)
            c_text = clean_html(content_m.group(1)) if content_m else ''
            cur.execute("""
                INSERT OR REPLACE INTO ancillary_texts (id, text_name, section, title, content)
                VALUES (?, ?, ?, ?, ?)
            """, ("aitareya_main", "aitareya_brahmana", "ऐतरेयब्राह्मणम्", "ऐतरेयब्राह्मणम्", c_text))

        # 3. Brihaddevata
        brihad_url = f"{BASE_URL}listing/bruhaddevatha"
        brihad_html = get_html(brihad_url)
        if brihad_html:
            content_m = re.search(r'<div class=\"container-fluid maintext\">(.*?)<footer', brihad_html, re.DOTALL)
            c_text = clean_html(content_m.group(1)) if content_m else ''
            cur.execute("""
                INSERT OR REPLACE INTO ancillary_texts (id, text_name, section, title, content)
                VALUES (?, ?, ?, ?, ?)
            """, ("brihaddevata_main", "bruhaddevatha", "बृहद्देवता", "॥ बृहद्देवता॥", c_text))

        conn.commit()
        conn.close()
        print("✅ Ancillary texts indexed.")

def main():
    parser = argparse.ArgumentParser(description="Rigveda Complete Scraper")
    parser.add_argument('--mandala', type=int, choices=range(1, 11), help="Scrape only a specific Mandala (1-10)")
    parser.add_argument('--workers', type=int, default=6, help="Number of concurrent download workers")
    parser.add_argument('--no-audio', action='store_true', help="Skip downloading audio MP3 files")
    parser.add_argument('--ancillary-only', action='store_true', help="Scrape only ancillary texts")
    parser.add_argument('--test', action='store_true', help="Test scrape on 1.1 only (9 riks)")

    args = parser.parse_args()

    scraper = RigvedaScraper(workers=args.workers, download_audio=not args.no_audio)

    if args.ancillary_only:
        scraper.scrape_ancillary_texts()
        return

    if args.test:
        print("🧪 Testing scraper on Mandala 1, Sukta 1...")
        batch = []
        for r in range(1, 10):
            res = scrape_rik_details(1, 1, r, download_audio=not args.no_audio)
            if res:
                batch.append(res)
                print(f"  Scraped 1.1.{r} -> Samhita: {res['samhita'][:40]}... (Bhashya len: {len(res['sayana_bhashya'])})")
        scraper.save_riks_batch(batch)
        print(f"✅ Test completed! Successfully saved {len(batch)} riks.")
        return

    if args.mandala:
        scraper.scrape_mandala(args.mandala)
    else:
        scraper.scrape_all()
        scraper.scrape_ancillary_texts()

if __name__ == '__main__':
    main()
