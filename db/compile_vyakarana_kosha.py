import os
import zipfile
import json
import sqlite3
import time
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in path so we can import vidyut if needed
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from vidyut.lipi import Scheme, transliterate
    def to_slp1(text):
        try:
            return transliterate(text, Scheme.Devanagari, Scheme.Slp1)
        except Exception:
            return text
except ImportError:
    print("Vidyut library not found or import failed, using fallback empty SLP1 helper.")
    def to_slp1(text):
        return text

def compile_database():
    zip_path = os.path.join(project_root, "data-master.zip")
    db_path = os.path.join(project_root, "db", "vyakarana_kosha.db")

    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found.")
        return

    print("Starting database compilation...")
    start_time = time.time()

    # If database exists, delete it for a clean build
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("Removed existing database for a clean build.")
        except Exception as e:
            print(f"Warning: Could not remove old database: {e}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Set pragmas for ultra-fast inserts
    cursor.execute("PRAGMA journal_mode = OFF;")
    cursor.execute("PRAGMA synchronous = OFF;")
    cursor.execute("PRAGMA cache_size = 100000;")

    # 1. Create Tables
    print("Creating tables...")
    cursor.execute("""
    CREATE TABLE shivasutras (
        id INTEGER PRIMARY KEY,
        sutra TEXT,
        kashika TEXT,
        vyakhya TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE sutraani (
        idx INTEGER PRIMARY KEY,
        adhyaya INTEGER,
        pada INTEGER,
        number INTEGER,
        sutra TEXT,
        sutra_slp1 TEXT,
        sk_number INTEGER,
        lsk_number INTEGER,
        type TEXT,
        padachheda TEXT,
        sutrartha_english TEXT,
        kashika TEXT,
        kaumudi TEXT,
        laghukaumudi TEXT,
        bhashya TEXT,
        nyaas TEXT,
        padamanjari TEXT,
        tattvabodhini TEXT,
        balamanorama TEXT,
        praudhamanorama TEXT,
        sutrartha_sa TEXT,
        sutrartha_sd TEXT,
        vasu_english TEXT,
        vasu_english_summary TEXT,
        sarala TEXT,
        sudha TEXT,
        prakriyasarvasvam TEXT,
        laghushabdendushekhar TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE vartikas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sutra_ref TEXT,
        vartika TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE sutra_prayogas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sutra_ref TEXT,
        word TEXT,
        source_text TEXT,
        loc TEXT,
        url TEXT,
        pada TEXT,
        ref TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE kosha_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dict_name TEXT,
        word TEXT,
        word_slp1 TEXT,
        entry_indices TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE kosha_entries (
        dict_name TEXT,
        entry_idx TEXT,
        definition TEXT,
        PRIMARY KEY (dict_name, entry_idx)
    );
    """)

    cursor.execute("""
    CREATE TABLE amara_verses (
        num TEXT PRIMARY KEY,
        text TEXT,
        words_json TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE halayudha_verses (
        num TEXT PRIMARY KEY,
        text TEXT,
        words_json TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE ganapatha (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ind INTEGER,
        name TEXT,
        sutra TEXT,
        vartika TEXT,
        words TEXT,
        type TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE unadipatha (
        id TEXT PRIMARY KEY,
        sutra TEXT,
        pratyay TEXT,
        sk TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE linganushasanam (
        id TEXT PRIMARY KEY,
        adhikaar TEXT,
        sutra TEXT,
        sk TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE shiksha (
        id TEXT PRIMARY KEY,
        text TEXT,
        pc TEXT,
        anvaya TEXT,
        artha TEXT,
        tatparya TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE phitsutrani (
        id TEXT PRIMARY KEY,
        p TEXT,
        n TEXT,
        s TEXT,
        sk TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE yaadavakosha_verses (
        num TEXT PRIMARY KEY,
        text TEXT,
        words_json TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE mahabhashyam (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER,
        adhikarana_id TEXT,
        adhikarana_name TEXT,
        chunk_id TEXT,
        bhashya TEXT,
        pradeep TEXT,
        uddyot TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE vakyapadeeyam (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kanda TEXT,
        samuddesh TEXT,
        adhikaar TEXT,
        verse_num TEXT,
        text TEXT,
        artha TEXT,
        svopajna TEXT,
        ambakartri TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE paribhashendushekhar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        num TEXT,
        prelude TEXT,
        paribhasha TEXT,
        text TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE bhushanasara (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        num TEXT,
        section_id TEXT,
        section TEXT,
        kaarika_id TEXT,
        prelude TEXT,
        kaarika TEXT,
        vyakhyaa TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE paramalaghumanjoosha (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter TEXT,
        name TEXT,
        text TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE tarkasangraha (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT,
        category TEXT,
        topic TEXT,
        text TEXT,
        teeka TEXT
    );
    """)

    conn.commit()

    # Helper to load a simple idx-keyed commentary file
    def load_commentary(zip_ref, filename):
        """Load a commentary file that maps idx_str -> text_string"""
        try:
            with zip_ref.open(f"data-master/sutraani/{filename}") as f:
                data = json.loads(f.read().decode('utf-8'))
                if isinstance(data, dict):
                    return data
                return {}
        except Exception as e:
            print(f"  Warning: Could not load {filename}: {e}")
            return {}

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # --- 2. COMPILE SHIVA SUTRAS ---
        print("Compiling Shiva Sutras...")
        try:
            with zip_ref.open("data-master/shivasutra/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                for item in content.get("data", []):
                    cursor.execute(
                        "INSERT INTO shivasutras (id, sutra, kashika, vyakhya) VALUES (?, ?, ?, ?)",
                        (int(item["id"]), item["sutra"], item.get("kashika", ""), item.get("vyakhya", ""))
                    )
            conn.commit()
            print("  Shiva Sutras compiled successfully.")
        except Exception as e:
            print(f"  Error compiling Shiva Sutras: {e}")

        # --- 3. COMPILE ASHTADHYAYI SUTRAS & ALL COMMENTARIES ---
        print("Compiling Ashtadhyayi Sutras & Commentaries...")
        try:
            # Load primary sutra list
            sutras = []
            with zip_ref.open("data-master/sutraani/data.txt") as f:
                sutras = json.loads(f.read().decode('utf-8')).get("data", [])

            # Load ALL commentary files
            print("  Loading commentary files...")
            sutrartha_english = load_commentary(zip_ref, "sutrartha_english.txt")
            kashika_commentary = load_commentary(zip_ref, "kashika.txt")
            kaumudi_commentary = load_commentary(zip_ref, "kaumudi.txt")
            laghu_commentary = load_commentary(zip_ref, "laghukaumudi.txt")
            bhashya_commentary = load_commentary(zip_ref, "bhashya.txt")
            nyaas_commentary = load_commentary(zip_ref, "nyaas.txt")
            padamanjari_commentary = load_commentary(zip_ref, "padamanjari.txt")
            tattvabodhini_commentary = load_commentary(zip_ref, "tattvabodhini.txt")
            balamanorama_commentary = load_commentary(zip_ref, "balamanorama.txt")
            praudhamanorama_commentary = load_commentary(zip_ref, "praudhamanorama.txt")
            vasu_english_commentary = load_commentary(zip_ref, "vasu_english.txt")
            vasu_english_summary_commentary = load_commentary(zip_ref, "vasu_english_summary.txt")
            sarala_commentary = load_commentary(zip_ref, "sarala.txt")
            sudha_commentary = load_commentary(zip_ref, "sudha.txt")
            prakriyasarvasvam_commentary = load_commentary(zip_ref, "prakriyasarvasvam.txt")
            laghushabdendushekhar_commentary = load_commentary(zip_ref, "laghushabdendushekhar.txt")

            # Load sutrartha (has dict with sa/sd subkeys)
            sutrartha_data = load_commentary(zip_ref, "sutrartha.txt")

            print(f"  Commentary files loaded. Inserting {len(sutras)} sutras...")

            # Mapping of type codes to Sanskrit names
            mapping = {
                'S': '\u0938\u0902\u091c\u094d\u091e\u093e',
                'V': '\u0935\u093f\u0927\u093f',
                'P': '\u092a\u0930\u093f\u092d\u093e\u0937\u093e',
                'AT': '\u0905\u0924\u093f\u0926\u0947\u0936',
                'AD': '\u0905\u0927\u093f\u0915\u093e\u0930',
                'N': '\u0928\u093f\u092f\u092e'
            }

            # Insert sutras
            for s in sutras:
                idx = int(s["i"])
                idx_str = str(idx)
                
                # Parse numeric references
                adhyaya = int(s.get("a", 0))
                pada = int(s.get("p", 0))
                number = int(s.get("n", 0))
                
                sutra_text = s.get("s", "")
                sutra_slp1 = s.get("e", "")
                
                sk_num = int(s["skn"]) if s.get("skn") and s["skn"].isdigit() else None
                lsk_num = int(s["lskn"]) if s.get("lskn") and s["lskn"].isdigit() else None
                
                stype = s.get("type", "")
                
                # Split by '##' or '$##' or '##$'
                parts = re.split(r'\$?##\$?', stype)
                cleaned_parts = []
                
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    
                    sub_match = re.match(r'^([A-Z]+)\$(.*?)\$?$', part)
                    if sub_match:
                        code = sub_match.group(1)
                        val = sub_match.group(2).strip()
                        code_name = mapping.get(code, code)
                        
                        if val:
                            if code_name in val or val.startswith(code_name) or val.endswith(code_name) or (code == 'AT' and '\u0905\u0924\u093f\u0926\u0947\u0936' in val):
                                cleaned_parts.append(val)
                            else:
                                cleaned_parts.append(f"{code_name}: {val}")
                        else:
                            cleaned_parts.append(code_name)
                    else:
                        part_clean = part.replace('$', '').strip()
                        if part_clean in mapping:
                            cleaned_parts.append(mapping[part_clean])
                        elif part_clean:
                            cleaned_parts.append(part_clean)
                            
                stype = " | ".join(cleaned_parts) if cleaned_parts else "\u0935\u093f\u0927\u093f"
                
                padachheda = s.get("ss", "")
                
                # Get commentary values
                english = sutrartha_english.get(idx_str, "")
                kashika = kashika_commentary.get(idx_str, "")
                kaumudi = kaumudi_commentary.get(idx_str, "")
                laghu = laghu_commentary.get(idx_str, "")
                bhashya = bhashya_commentary.get(idx_str, "")
                nyaas = nyaas_commentary.get(idx_str, "")
                padamanjari = padamanjari_commentary.get(idx_str, "")
                tattvabodhini = tattvabodhini_commentary.get(idx_str, "")
                balamanorama = balamanorama_commentary.get(idx_str, "")
                praudhamanorama = praudhamanorama_commentary.get(idx_str, "")
                vasu_english = vasu_english_commentary.get(idx_str, "")
                vasu_english_summary = vasu_english_summary_commentary.get(idx_str, "")
                sarala = sarala_commentary.get(idx_str, "")
                sudha = sudha_commentary.get(idx_str, "")
                prakriyasarvasvam = prakriyasarvasvam_commentary.get(idx_str, "")
                laghushabdendushekhar = laghushabdendushekhar_commentary.get(idx_str, "")

                # Sutrartha has dict with sa/sd subkeys
                sutrartha_entry = sutrartha_data.get(idx_str, {})
                if isinstance(sutrartha_entry, dict):
                    sutrartha_sa = sutrartha_entry.get("sa", "")
                    sutrartha_sd = sutrartha_entry.get("sd", "")
                else:
                    sutrartha_sa = str(sutrartha_entry) if sutrartha_entry else ""
                    sutrartha_sd = ""

                cursor.execute("""
                INSERT INTO sutraani (
                    idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, 
                    type, padachheda, sutrartha_english, kashika, kaumudi, laghukaumudi,
                    bhashya, nyaas, padamanjari, tattvabodhini, balamanorama, praudhamanorama,
                    sutrartha_sa, sutrartha_sd, vasu_english, vasu_english_summary,
                    sarala, sudha, prakriyasarvasvam, laghushabdendushekhar
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    idx, adhyaya, pada, number, sutra_text, sutra_slp1, sk_num, lsk_num,
                    stype, padachheda, english, kashika, kaumudi, laghu,
                    bhashya, nyaas, padamanjari, tattvabodhini, balamanorama, praudhamanorama,
                    sutrartha_sa, sutrartha_sd, vasu_english, vasu_english_summary,
                    sarala, sudha, prakriyasarvasvam, laghushabdendushekhar
                ))
            conn.commit()
            print(f"  Ashtadhyayi Sutras compiled successfully. Count: {len(sutras)}")
        except Exception as e:
            import traceback
            print(f"  Error compiling Ashtadhyayi Sutras: {e}")
            traceback.print_exc()

        # --- 4. COMPILE VARTIKAS ---
        print("Compiling Vartikas...")
        try:
            with zip_ref.open("data-master/sutraani/vartika.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                vartika_list = content.get("data", [])
                batch = []
                for item in vartika_list:
                    if isinstance(item, dict):
                        sutra_ref = item.get("sutra", "")
                        vartika_text = item.get("vartika", "")
                        if sutra_ref and vartika_text:
                            batch.append((sutra_ref, vartika_text))
                cursor.executemany(
                    "INSERT INTO vartikas (sutra_ref, vartika) VALUES (?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Vartikas compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Vartikas: {e}")

        # --- 5. COMPILE SUTRA PRAYOGAS (Literary Usage Examples) ---
        print("Compiling Sutra Prayogas...")
        try:
            with zip_ref.open("data-master/sutraani/sutra_prayogas.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                prayoga_data = content.get("data", {})
                batch = []
                for sutra_ref, examples in prayoga_data.items():
                    if isinstance(examples, list):
                        for ex in examples:
                            if isinstance(ex, dict):
                                batch.append((
                                    sutra_ref,
                                    ex.get("word", ""),
                                    ex.get("text", ""),
                                    ex.get("loc", ""),
                                    ex.get("url", ""),
                                    ex.get("pada", ""),
                                    ex.get("ref", "")
                                ))
                cursor.executemany(
                    "INSERT INTO sutra_prayogas (sutra_ref, word, source_text, loc, url, pada, ref) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Sutra Prayogas compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Sutra Prayogas: {e}")

        # --- 6. COMPILE KOSHA DICTIONARIES ---
        dictionaries = [
            ("ap90", "data-master/kosha/ap90.json", "Apte Sanskrit-English"),
            ("mw", "data-master/kosha/mw.json", "Monier-Williams"),
            ("skd", "data-master/kosha/skd.json", "Shabda-Kalpadruma"),
            ("abhyankar", "data-master/kosha/abhyankar.json", "Abhyankar Grammar"),
            ("wil", "data-master/kosha/wil.json", "Wilson Sanskrit-English"),
            ("ben", "data-master/kosha/ben.json", "Benfey Sanskrit-English"),
            ("cae", "data-master/kosha/cae.json", "Cappeller Sanskrit-Worterbuch"),
            ("md", "data-master/kosha/md.json", "Macdonell Sanskrit-English"),
            ("shs", "data-master/kosha/shs.json", "Shabda-Sagara"),
            ("yat", "data-master/kosha/yat.json", "Yates Sanskrit-English"),
            ("vcp", "data-master/kosha/vcp.json", "Vacaspatyam"),
            
            ("ae", "data-master/kosha/ae.json", "Apte Student English-Sanskrit"),
            ("armh", "data-master/kosha/armh.json", "Abhidhanaratnamala of Halayudha"),
            ("bharati", "data-master/kosha/bharati.json", "Bharati Sanskrit Dictionary"),
            ("bhs", "data-master/kosha/bhs.json", "Edgerton Buddhist Hybrid Sanskrit"),
            ("bop", "data-master/kosha/bop.json", "Bopp Sanskrit-Latin"),
            ("bor", "data-master/kosha/bor.json", "Böhtlingk Sanskrit-English"),
            ("bur", "data-master/kosha/bur.json", "Burnouf Sanskrit-French"),
            ("ccs", "data-master/kosha/ccs.json", "Cappeller Sanskrit-German"),
            ("gra", "data-master/kosha/gra.json", "Grassman Rigveda Dictionary"),
            ("gst", "data-master/kosha/gst.json", "Geschichte der Sanskrit-Philologie"),
            ("ieg", "data-master/kosha/ieg.json", "Indian Epigraphical Glossary"),
            ("inm", "data-master/kosha/inm.json", "Index to Monier-Williams"),
            ("krm", "data-master/kosha/krm.json", "Kṛdanta-rūpa-mālā"),
            ("lan", "data-master/kosha/lan.json", "Lanman Sanskrit Reader Vocabulary"),
            ("mci", "data-master/kosha/mci.json", "Mahabharata Cultural Index"),
            ("mw72", "data-master/kosha/mw72.json", "Monier-Williams 1872"),
            ("mwe", "data-master/kosha/mwe.json", "Monier-Williams English-Sanskrit"),
            ("pe", "data-master/kosha/pe.json", "Practical Sanskrit-English"),
            ("pgn", "data-master/kosha/pgn.json", "Personal Names in Pāṇini"),
            ("pui", "data-master/kosha/pui.json", "Puranic Encyclopedia"),
            ("pw", "data-master/kosha/pw.json", "Böhtlingk Sanskrit-Wörterbuch (Shorter)"),
            ("pwg", "data-master/kosha/pwg.json", "Böhtlingk & Roth Grosses Petersburger"),
            ("sch", "data-master/kosha/sch.json", "Schmidt Sanskrit-German"),
            ("snp", "data-master/kosha/snp.json", "Sanskrit Names of Plants"),
            ("stc", "data-master/kosha/stc.json", "Schmidt Sanskrit-German Nachträge"),
            ("vei", "data-master/kosha/vei.json", "Vedic Index of Names and Subjects"),
            ("acc", "data-master/kosha/acc.json", "Aufrecht Catalogus Catalogorum"),
            ("aptehindi", "data-master/kosha/aptehindi.json", "Apte Sanskrit-Hindi"),
            ("skk", "data-master/kosha/skk.json", "Shabda-Kautubha (शब्दकौस्तुभः)"),
        ]

        for dict_name, zip_file, display_name in dictionaries:
            print(f"  Compiling dictionary: {display_name} ({dict_name})...")
            try:
                with zip_ref.open(zip_file) as f:
                    content = json.loads(f.read().decode('utf-8'))
                    kosha_data = content.get("data", {})
                    
                    if "words" in kosha_data:
                        # Index-mapped structured dictionary (e.g. Apte, MW, SKD)
                        words = kosha_data.get("words", {})
                        entries = kosha_data.get("text", {}) or kosha_data.get("meanings", {})

                        words_batch = []
                        for w, indices in words.items():
                            if isinstance(indices, list):
                                indices_str = ",".join(map(str, indices))
                            else:
                                indices_str = str(indices)
                            words_batch.append((dict_name, w, to_slp1(w), indices_str))
                        
                        cursor.executemany(
                            "INSERT INTO kosha_words (dict_name, word, word_slp1, entry_indices) VALUES (?, ?, ?, ?)",
                            words_batch
                        )
                        conn.commit()

                        entries_batch = []
                        for idx_str, entry_data in entries.items():
                            definition = ""
                            if isinstance(entry_data, list) and len(entry_data) > 0:
                                definition = entry_data[0]
                            else:
                                definition = str(entry_data)
                            entries_batch.append((dict_name, str(idx_str), definition))
                        
                        cursor.executemany(
                            "INSERT INTO kosha_entries (dict_name, entry_idx, definition) VALUES (?, ?, ?)",
                            entries_batch
                        )
                        conn.commit()
                        print(f"    {len(words)} words, {len(entries)} entries loaded.")
                    else:
                        # Flat dictionary structure (e.g. Abhyankar, Halayudha)
                        words_batch = []
                        entries_batch = []
                        idx_counter = 1
                        for w, entry_data in kosha_data.items():
                            idx_str = str(idx_counter)
                            words_batch.append((dict_name, w, to_slp1(w), idx_str))
                            
                            definition = ""
                            if isinstance(entry_data, list):
                                joined_meanings = []
                                for item in entry_data:
                                    if isinstance(item, dict):
                                        parts = []
                                        for k, v in item.items():
                                            parts.append(f"<b>{k}</b>: {v}")
                                        joined_meanings.append("<br>".join(parts))
                                    else:
                                        joined_meanings.append(str(item))
                                definition = "<hr style='margin: 8px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.08);'>".join(joined_meanings)
                            elif isinstance(entry_data, dict):
                                parts = []
                                for k, v in entry_data.items():
                                    parts.append(f"<b>{k}</b>: {v}")
                                definition = "<br>".join(parts)
                            else:
                                definition = str(entry_data)
                            entries_batch.append((dict_name, idx_str, definition))
                            idx_counter += 1
                            
                        cursor.executemany(
                            "INSERT INTO kosha_words (dict_name, word, word_slp1, entry_indices) VALUES (?, ?, ?, ?)",
                            words_batch
                        )
                        cursor.executemany(
                            "INSERT INTO kosha_entries (dict_name, entry_idx, definition) VALUES (?, ?, ?)",
                            entries_batch
                        )
                        conn.commit()
                        print(f"    {len(words_batch)} words loaded (flat).")
                        
                    print(f"    Dictionary '{display_name}' compiled successfully.")
            except Exception as e:
                print(f"    Error compiling dictionary {dict_name}: {e}")

        # --- 7. COMPILE AMARAKOSHA SYNONYMS ---
        print("Compiling Amarakosha...")
        try:
            with zip_ref.open("data-master/kosha/amara.json") as f:
                content = json.loads(f.read().decode('utf-8'))
                verses = content.get("data", [])
                
                verses_batch = []
                for item in verses:
                    num = item.get("num", "")
                    text = item.get("text", "")
                    words_list = item.get("words", [])
                    verses_batch.append((num, text, json.dumps(words_list, ensure_ascii=False)))
                
                cursor.executemany(
                    "INSERT INTO amara_verses (num, text, words_json) VALUES (?, ?, ?)",
                    verses_batch
                )
                conn.commit()
            print(f"  Amarakosha compiled successfully. Count: {len(verses)}")
        except Exception as e:
            print(f"  Error compiling Amarakosha: {e}")

        # --- 7.5. COMPILE HALAYUDHA KOSHA ---
        print("Compiling Halayudha Kosha...")
        try:
            with zip_ref.open("data-master/kosha/halayudha.json") as f:
                content = json.loads(f.read().decode('utf-8'))
                verses = content.get("data", [])
                
                verses_batch = []
                for item in verses:
                    num = item.get("num", "")
                    text = item.get("text", "")
                    words_list = item.get("words", [])
                    verses_batch.append((num, text, json.dumps(words_list, ensure_ascii=False)))
                
                cursor.executemany(
                    "INSERT INTO halayudha_verses (num, text, words_json) VALUES (?, ?, ?)",
                    verses_batch
                )
                conn.commit()
            print(f"  Halayudha Kosha compiled successfully. Count: {len(verses)}")
        except Exception as e:
            print(f"  Error compiling Halayudha Kosha: {e}")

        # --- 8. COMPILE GANAPATHA ---
        print("Compiling Ganapatha...")
        try:
            with zip_ref.open("data-master/ganapath/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", []) if isinstance(content, dict) else content
                batch = []
                for item in items:
                    batch.append((
                        item.get("ind"),
                        item.get("name", ""),
                        item.get("sutra", ""),
                        item.get("vartika", ""),
                        item.get("words", ""),
                        item.get("type", "")
                    ))
                cursor.executemany(
                    "INSERT INTO ganapatha (ind, name, sutra, vartika, words, type) VALUES (?, ?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Ganapatha compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Ganapatha: {e}")

        # --- 9. COMPILE UNADIPATHA ---
        print("Compiling Unadipatha...")
        try:
            with zip_ref.open("data-master/unaadi/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", []) if isinstance(content, dict) else content
                batch = []
                for item in items:
                    batch.append((
                        item.get("i", ""),
                        item.get("sutra", ""),
                        item.get("pratyay", ""),
                        item.get("sk", "")
                    ))
                cursor.executemany(
                    "INSERT INTO unadipatha (id, sutra, pratyay, sk) VALUES (?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Unadipatha compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Unadipatha: {e}")

        # --- 10. COMPILE LINGANUSHASANAM ---
        print("Compiling Linganushasanam...")
        try:
            with zip_ref.open("data-master/linganushasanam/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", []) if isinstance(content, dict) else content
                batch = []
                for item in items:
                    batch.append((
                        item.get("id", ""),
                        item.get("adhikaar", ""),
                        item.get("sutra", ""),
                        item.get("sk", "")
                    ))
                cursor.executemany(
                    "INSERT INTO linganushasanam (id, adhikaar, sutra, sk) VALUES (?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Linganushasanam compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Linganushasanam: {e}")

        # --- 11. COMPILE PANINIYA SHIKSHA ---
        print("Compiling Paniniya Shiksha...")
        try:
            with zip_ref.open("data-master/shiksha/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", []) if isinstance(content, dict) else content
                batch = []
                for item in items:
                    batch.append((
                        item.get("id", ""),
                        item.get("text", ""),
                        item.get("pc", ""),
                        item.get("anvaya", ""),
                        item.get("artha", ""),
                        item.get("tatparya", "")
                    ))
                cursor.executemany(
                    "INSERT INTO shiksha (id, text, pc, anvaya, artha, tatparya) VALUES (?, ?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Paniniya Shiksha compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Paniniya Shiksha: {e}")

        # --- 12. COMPILE PHIT SUTRAS ---
        print("Compiling Phit Sutras...")
        try:
            with zip_ref.open("data-master/fit/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", []) if isinstance(content, dict) else content
                batch = []
                for item in items:
                    batch.append((
                        item.get("i", ""),
                        item.get("p", ""),
                        item.get("n", ""),
                        item.get("s", ""),
                        item.get("sk", "")
                    ))
                cursor.executemany(
                    "INSERT INTO phitsutrani (id, p, n, s, sk) VALUES (?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                print(f"  Phit Sutras compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Phit Sutras: {e}")

        # --- 13. COMPILE MAHABHASHYAM ---
        print("Compiling Mahabhashyam...")
        try:
            mahabhashya_batch = []
            for file_id, file_path in [(1, "data-master/mahabhashyam/1.txt"), (2, "data-master/mahabhashyam/2.txt")]:
                with zip_ref.open(file_path) as f:
                    content = json.loads(f.read().decode('utf-8'))
                    items = content.get("data", [])
                    for item in items:
                        mahabhashya_batch.append((
                            file_id,
                            item.get("adhikarana_id", ""),
                            item.get("adhikarana_name", ""),
                            item.get("chunk_id", ""),
                            item.get("bhashya", ""),
                            item.get("pradeep", ""),
                            item.get("uddyot", "")
                        ))
            cursor.executemany(
                "INSERT INTO mahabhashyam (file_id, adhikarana_id, adhikarana_name, chunk_id, bhashya, pradeep, uddyot) VALUES (?, ?, ?, ?, ?, ?, ?)",
                mahabhashya_batch
            )
            conn.commit()
            print(f"  Mahabhashyam compiled successfully. Count: {len(mahabhashya_batch)}")
        except Exception as e:
            print(f"  Error compiling Mahabhashyam: {e}")

        # --- 14. COMPILE VAKYAPADEEYAM ---
        print("Compiling Vakyapadeeyam...")
        try:
            svopajna = {}
            try:
                with zip_ref.open("data-master/vakyapadeeyam/swopajna.txt") as f:
                    svopajna = json.loads(f.read().decode('utf-8')).get("data", {})
            except Exception as e:
                print(f"  Warning: Could not load swopajna: {e}")

            svopajna2 = {}
            try:
                with zip_ref.open("data-master/vakyapadeeyam/swopajna2.txt") as f:
                    svopajna2 = json.loads(f.read().decode('utf-8')).get("data", {})
            except Exception as e:
                print(f"  Warning: Could not load swopajna2: {e}")

            svopajna.update(svopajna2)

            ambakartri = {}
            try:
                with zip_ref.open("data-master/vakyapadeeyam/ambakartri.txt") as f:
                    ambakartri = json.loads(f.read().decode('utf-8')).get("data", {})
            except Exception as e:
                print(f"  Warning: Could not load ambakartri: {e}")

            with zip_ref.open("data-master/vakyapadeeyam/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                verses = content.get("data", [])
                
                vakyapadeeya_batch = []
                for item in verses:
                    kanda = item.get("kanda", "")
                    samuddesh = item.get("samuddesh", "")
                    adhikaar = item.get("adhikaar", "")
                    id_val = item.get("id", "")
                    text = item.get("text", "")
                    artha = item.get("artha", "")
                    
                    if kanda and samuddesh and id_val:
                        lookup_key = f"{kanda}.{samuddesh}.{id_val}"
                    elif kanda and id_val:
                        lookup_key = f"{kanda}.{id_val}"
                    else:
                        lookup_key = ""
                    
                    comm_svo = svopajna.get(lookup_key, "") if lookup_key else ""
                    comm_amba = ambakartri.get(lookup_key, "") if lookup_key else ""
                    
                    vakyapadeeya_batch.append((
                        kanda,
                        samuddesh,
                        adhikaar,
                        lookup_key,
                        text,
                        artha,
                        comm_svo,
                        comm_amba
                    ))
                
                cursor.executemany(
                    "INSERT INTO vakyapadeeyam (kanda, samuddesh, adhikaar, verse_num, text, artha, svopajna, ambakartri) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    vakyapadeeya_batch
                )
                conn.commit()
            print(f"  Vakyapadeeyam compiled successfully. Count: {len(vakyapadeeya_batch)}")
        except Exception as e:
            print(f"  Error compiling Vakyapadeeyam: {e}")

        # --- 15. COMPILE PARIBHASHENDUSHEKHAR ---
        print("Compiling Paribhashendushekhar...")
        try:
            with zip_ref.open("data-master/paribhashendushekhar/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", [])
                batch = []
                for item in items:
                    batch.append((
                        item.get("num", ""),
                        item.get("prelude", ""),
                        item.get("paribhasha", ""),
                        item.get("text", "")
                    ))
                cursor.executemany(
                    "INSERT INTO paribhashendushekhar (num, prelude, paribhasha, text) VALUES (?, ?, ?, ?)",
                    batch
                )
                conn.commit()
            print(f"  Paribhashendushekhar compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Paribhashendushekhar: {e}")

        # --- 16. COMPILE BHUSHANASARA ---
        print("Compiling Bhushanasara...")
        try:
            with zip_ref.open("data-master/bhushanasara/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", [])
                batch = []
                for item in items:
                    batch.append((
                        item.get("num", ""),
                        item.get("section_id", ""),
                        item.get("section", ""),
                        item.get("kaarika_id", ""),
                        item.get("prelude", ""),
                        item.get("kaarika", ""),
                        item.get("vyakhyaa", "")
                    ))
                cursor.executemany(
                    "INSERT INTO bhushanasara (num, section_id, section, kaarika_id, prelude, kaarika, vyakhyaa) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
            print(f"  Bhushanasara compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Bhushanasara: {e}")

        # --- 17. COMPILE PARAMALAGHUMANJOOSHA ---
        print("Compiling Paramalaghumanjoosha...")
        try:
            with zip_ref.open("data-master/paramalaghumanjoosha/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", [])
                batch = []
                for item in items:
                    batch.append((
                        item.get("chapter", ""),
                        item.get("name", ""),
                        item.get("text", "")
                    ))
                cursor.executemany(
                    "INSERT INTO paramalaghumanjoosha (chapter, name, text) VALUES (?, ?, ?)",
                    batch
                )
                conn.commit()
            print(f"  Paramalaghumanjoosha compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Paramalaghumanjoosha: {e}")

        # --- 18. COMPILE TARKASANGRAHA ---
        print("Compiling Tarkasangraha...")
        try:
            with zip_ref.open("data-master/tarkasangraha/data.txt") as f:
                content = json.loads(f.read().decode('utf-8'))
                items = content.get("data", [])
                batch = []
                for item in items:
                    batch.append((
                        item.get("id", ""),
                        item.get("category", ""),
                        item.get("topic", ""),
                        item.get("text", ""),
                        item.get("teeka", "")
                    ))
                cursor.executemany(
                    "INSERT INTO tarkasangraha (item_id, category, topic, text, teeka) VALUES (?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
            print(f"  Tarkasangraha compiled successfully. Count: {len(batch)}")
        except Exception as e:
            print(f"  Error compiling Tarkasangraha: {e}")

        # --- 19. COMPILE YAADAVAKOSHA ---
        print("Compiling Yadavakosha...")
        try:
            with zip_ref.open("data-master/kosha/yaadavakosha.json") as f:
                content = json.loads(f.read().decode('utf-8'))
                verses = content.get("data", [])
                
                verses_batch = []
                for item in verses:
                    num = item.get("num", "")
                    text = item.get("text", "")
                    words_list = item.get("words", [])
                    verses_batch.append((num, text, json.dumps(words_list, ensure_ascii=False)))
                
                cursor.executemany(
                    "INSERT INTO yaadavakosha_verses (num, text, words_json) VALUES (?, ?, ?)",
                    verses_batch
                )
                conn.commit()
            print(f"  Yadavakosha compiled successfully. Count: {len(verses)}")
        except Exception as e:
            print(f"  Error compiling Yadavakosha: {e}")

    # 8. Create Indexes
    print("Creating database indexes for fast lookups...")
    cursor.execute("CREATE INDEX idx_kosha_words_word ON kosha_words(word);")
    cursor.execute("CREATE INDEX idx_kosha_words_word_slp1 ON kosha_words(word_slp1);")
    cursor.execute("CREATE INDEX idx_kosha_words_dict ON kosha_words(dict_name);")
    cursor.execute("CREATE INDEX idx_sutraani_sutra ON sutraani(sutra);")
    cursor.execute("CREATE INDEX idx_sutraani_sutra_slp1 ON sutraani(sutra_slp1);")
    cursor.execute("CREATE INDEX idx_sutraani_nums ON sutraani(adhyaya, pada, number);")
    cursor.execute("CREATE INDEX idx_vartikas_ref ON vartikas(sutra_ref);")
    cursor.execute("CREATE INDEX idx_prayogas_ref ON sutra_prayogas(sutra_ref);")
    cursor.execute("CREATE INDEX idx_ganapatha_sutra ON ganapatha(sutra);")
    
    cursor.execute("CREATE INDEX idx_mahabhashyam_chunk ON mahabhashyam(adhikarana_id, chunk_id);")
    cursor.execute("CREATE INDEX idx_vakyapadeeyam_num ON vakyapadeeyam(verse_num);")
    cursor.execute("CREATE INDEX idx_paribhasha_num ON paribhashendushekhar(num);")
    cursor.execute("CREATE INDEX idx_bhushanasara_num ON bhushanasara(num);")
    cursor.execute("CREATE INDEX idx_paramalaghu_chap ON paramalaghumanjoosha(chapter);")
    cursor.execute("CREATE INDEX idx_tarkasangraha_id ON tarkasangraha(item_id);")
    conn.commit()

    conn.close()
    elapsed = time.time() - start_time
    print(f"\nCompilation finished successfully in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    compile_database()
