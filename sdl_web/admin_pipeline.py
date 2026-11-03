import os
import subprocess
import threading
import time
import uuid
import json
import shutil
import zstandard as zstd
import tempfile
import sys
import re
import zipfile
from datetime import datetime
from flask import request, jsonify, render_template, session, send_file
from functools import wraps
def log_change(*args, **kwargs):
    pass
import config
from time_utils import get_ist_now

# Paths to CLI scripts (using local copies for production/git)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CLI_DIR = os.path.join(APP_DIR, "scripts")
DOWNLOAD_SCRIPT = os.path.join(CLI_DIR, "download_pdfs.py")
PDF2IMG_SCRIPT = os.path.join(CLI_DIR, "pdf_to_images.py")
OCR_SCRIPT = os.path.join(CLI_DIR, "ocr_images.py")
RETRY_SCRIPT = os.path.join(CLI_DIR, "retry_ocr.py")

# Global state for background tasks
PIPELINE_TASKS = {}

# Persistent folder for completed ZIP outputs — survives server restarts
ZIP_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pipeline_zips')
os.makedirs(ZIP_OUTPUT_DIR, exist_ok=True)


def sanitize_tags_against_taxonomy(tags_str, published=True):
    if not tags_str:
        return ""
    if not published:
        return tags_str
    taxonomy_file = os.path.join(APP_DIR, 'taxonomy.json')
    allowed_set = set()
    if os.path.exists(taxonomy_file):
        try:
            with open(taxonomy_file, 'r', encoding='utf-8') as f:
                tax = json.load(f)
                for node in tax.get('nodes', []):
                    for t in node.get('tags', []):
                        if t.strip():
                            allowed_set.add(t.strip())
        except Exception:
            pass
    if not allowed_set:
        return tags_str
    submitted = [t.strip() for t in tags_str.split(',') if t.strip()]
    return ', '.join([t for t in submitted if t in allowed_set])


def get_completed_zip_tasks():
    """Dynamically scan pipeline_zips/ and return a list of completed ZIP task dicts."""
    completed_tasks = []
    for task_id in os.listdir(ZIP_OUTPUT_DIR):
        if not re.match(r'^[a-f0-9]{8}$', task_id):
            continue
        task_dir = os.path.join(ZIP_OUTPUT_DIR, task_id)
        zip_path  = os.path.join(task_dir, 'output.zip')
        info_path = os.path.join(task_dir, 'info.json')
        if not os.path.isdir(task_dir) or not os.path.exists(zip_path):
            continue
            
        created_at_dt = datetime.fromtimestamp(os.path.getmtime(zip_path))
        book_count = 0
        books = []
        if os.path.exists(info_path):
            try:
                with open(info_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                created_at_dt = datetime.fromisoformat(info.get('created_at', created_at_dt.isoformat()))
                book_count = info.get('book_count', 0)
                books = info.get('books', [])
            except Exception:
                pass
                
        completed_tasks.append({
            'task_id': task_id,
            'created_at_dt': created_at_dt,
            'created_at': created_at_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'default_filename': created_at_dt.strftime("sdl_%Y%m%d_%H%M%S"),
            'done': True,
            'success': True,
            'staged_count': book_count,
            'books': books,
            'current_step': 'Ready for Download',
        })
    return completed_tasks



def extract_archive_id(url):
    """Extract item identifier and optional subpath (specific book) from URL."""
    if not url: return None
    import urllib.parse
    url = urllib.parse.unquote(url).strip(' "\'[]()<>')
    # Search for archive.org/(details|download)/IDENTIFIER[/SUBPATH...]
    match = re.search(r'archive\.org/(?:details|download)/([^/\\?]+)(?:/(.*))?', url)
    if match:
        identifier = match.group(1).strip().lower()
        subpath = match.group(2)
        if subpath:
            # Strip query params or fragments if any
            subpath = subpath.split('?')[0].split('#')[0].strip('/').lower()
            if subpath:
                return f"{identifier}/{subpath}"
        return identifier
    return None


def get_existing_archive_ids():
    """Scan uploads folder for existing archive IDs."""
    existing_ids = set()
    upload_folder = config.UPLOAD_FOLDER
    if not os.path.exists(upload_folder):
        return existing_ids

    for folder_name in os.listdir(upload_folder):
        folder_path = os.path.join(upload_folder, folder_name)
        if not os.path.isdir(folder_path):
            continue

        metadata_path = os.path.join(folder_path, 'metadata.txt')
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Source:'):
                            source_url = line.replace('Source:', '').strip()
                            idx = extract_archive_id(source_url)
                            if idx:
                                existing_ids.add(idx)
                            break
            except:
                pass
    return existing_ids


class PipelineTask:
    def __init__(self, task_id, links, lang, workers, auto_advance, initiator="Unknown", output_mode='upload', status='published', _skip_temp_mkdir=False):
        self.task_id = task_id
        self.links = links
        self.lang = lang
        self.workers = workers
        self.auto_advance = auto_advance
        self.initiator = initiator
        self.output_mode = output_mode          # 'upload' | 'zip'
        self.status = status
        self.logs = []
        self.current_step = "Idle"
        self.last_log_time = 0.0
        self.progress = 0
        self.done = False
        self.success = False
        self.process = None
        self.stop_requested = False
        self.created_at = get_ist_now()
        self.staged_folders = []               # Zip mode: paths of fully-packed book folders
        self._book_count = None                # Set after build_zip(); used for restored tasks
        self.books = []
        self.temp_output_dir = os.path.join(tempfile.gettempdir(), f"sdl_pipeline_{task_id}")
        if not _skip_temp_mkdir:
            os.makedirs(self.temp_output_dir, exist_ok=True)
            self._init_shared_state()

    def _init_shared_state(self):
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        shared_log = os.path.join(ZIP_OUTPUT_DIR, 'active_task.log.jsonl')
        if os.path.exists(shared_json):
            try: os.remove(shared_json)
            except: pass
        if os.path.exists(shared_log):
            try: os.remove(shared_log)
            except: pass
        self._update_shared_state()

    def _update_shared_state(self):
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        state = {
            'task_id': self.task_id,
            'created_at': self.created_at.strftime('%Y%m%d_%H%M%S'),
            'current_step': self.current_step,
            'done': self.done,
            'success': self.success,
            'output_mode': self.output_mode,
            'staged_count': self._book_count if self._book_count is not None else len(self.staged_folders),
            'abort_signal': self.stop_requested
        }
        try:
            with open(shared_json, 'w', encoding='utf-8') as f:
                json.dump(state, f)
        except:
            pass

    def _check_abort_signal(self):
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        if os.path.exists(shared_json):
            try:
                with open(shared_json, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    if state.get('abort_signal') and state.get('task_id') == self.task_id:
                        self.stop_requested = True
            except:
                pass

    def log(self, message):
        current_time = time.time()
        is_cr = message.startswith('\r')
        if is_cr:
            if current_time - self.last_log_time < 1.0:
                return
            self.last_log_time = current_time

        self.logs.append(message)
        print(f"[{self.task_id}] {message.strip()}")
        shared_log = os.path.join(ZIP_OUTPUT_DIR, 'active_task.log.jsonl')
        try:
            with open(shared_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(message) + '\n')
        except:
            pass

    def get_logs(self, start_index=0):
        return self.logs[start_index:]

    # ──────────────────────────────────────────────────────────────
    # Main pipeline entry point
    # ──────────────────────────────────────────────────────────────
    def run(self):
        try:
            # 0. Duplicate check
            self.current_step = "Checking for duplicates"
            existing_ids = get_existing_archive_ids()

            all_links = [l.strip() for l in self.links.split('\n')
                         if l.strip() and not l.strip().startswith('#')]
            filtered_links = []
            skipped_count = 0

            for link in all_links:
                url = link.split('|')[0].strip().strip(' "')
                idx = extract_archive_id(url)

                is_dup = False
                if idx:
                    if idx in existing_ids:
                        is_dup = True
                    elif '/' not in idx:
                        for ext_id in existing_ids:
                            if ext_id == idx:
                                is_dup = True
                                break
                            if '/' in ext_id:
                                ext_base, ext_sub = ext_id.split('/', 1)
                                if ext_base == idx and ext_sub in ext_base:
                                    is_dup = True
                                    break

                if is_dup:
                    self.log(f"[SKIP] Already in library: {idx}")
                    skipped_count += 1
                else:
                    filtered_links.append(link)

            if not filtered_links:
                if skipped_count > 0:
                    self.log(f"\n[INFO] All {skipped_count} link(s) already present. Nothing to do.")
                    self.success = True
                    return
                else:
                    self.log("\n[ERR] No valid links found.")
                    return

            if skipped_count > 0:
                self.log(f"[INFO] Skipping {skipped_count} existing item(s), "
                         f"processing {len(filtered_links)} new item(s).\n")

            total = len(filtered_links)
            failed_links = []

            # 1. Process each link sequentially
            for link_idx, link in enumerate(filtered_links, 1):
                if self.stop_requested:
                    self.log("\n[INFO] Pipeline aborted by user.\n")
                    break

                link_url = link.split('|')[0].strip()
                sep = '═' * 58
                self.log(f"\n{sep}\n")
                self.log(f"  [{link_idx}/{total}]  {link_url}\n")
                self.log(f"{sep}\n")

                ok = self._process_single_link(link, link_idx, total)
                if not ok:
                    failed_links.append(link_url)
                    self.log(f"\n[WARN] ✗ Link {link_idx}/{total} FAILED — "
                             f"continuing to next link...\n")
                else:
                    self.log(f"\n[OK] ✓ Link {link_idx}/{total} completed.\n")

            # 2. Summary
            if failed_links:
                self.log(f"\n[WARN] {len(failed_links)} link(s) failed:\n")
                for fl in failed_links:
                    self.log(f"  ✗ {fl}\n")

            successful = total - len(failed_links)
            if successful > 0:
                self.success = True
                if self.output_mode == 'zip':
                    self.log(f"\n[PIPELINE] DONE! {successful}/{total} book(s) ready — building ZIP...\n")
                else:
                    self.log(f"\n[PIPELINE] ALL STEPS COMPLETED! "
                             f"{successful}/{total} book(s) uploaded to library.\n")
            else:
                self.log("\n[PIPELINE] ALL LINKS FAILED — no books processed.\n")

        except Exception as e:
            self.log(f"\n[PIPELINE ERR] Critical Failure: {e}")
            import traceback
            self.log(traceback.format_exc())
        finally:
            if self.output_mode == 'upload':
                # Upload mode: clean up the now-empty temp root
                if os.path.exists(self.temp_output_dir):
                    try:
                        shutil.rmtree(self.temp_output_dir)
                        self.log(f"[INFO] Cleaned up temp directory.\n")
                    except Exception:
                        pass
            else:
                # ZIP mode: build the zip into the persistent output folder,
                # then clean up the temp staged dirs (no longer needed).
                if self.staged_folders:
                    self.log(f"[INFO] Building ZIP for {len(self.staged_folders)} book(s)...\n")
                    try:
                        self.build_zip()
                        self.log(f"[INFO] ZIP saved. Use the Download ZIP button.\n")
                    except Exception as e:
                        self.log(f"[WARN] ZIP build failed: {e}\n")
            self.done = True
            self._update_shared_state()


    # ──────────────────────────────────────────────────────────────
    # Per-link processing
    # ──────────────────────────────────────────────────────────────
    def _process_single_link(self, link, link_idx, total):
        """Run Download → PDF2Img → OCR → Pack for a single link.
        Returns True on success, False on any step failure."""
        link_url = link.split('|')[0].strip()
        safe_name = re.sub(r'[^\w\-]', '_', link_url.rstrip('/').split('/')[-1])[:40]
        link_temp_dir = os.path.join(self.temp_output_dir, f"{link_idx:03d}_{safe_name}")
        os.makedirs(link_temp_dir, exist_ok=True)

        try:
            # Write single-link input file
            links_file = os.path.join(link_temp_dir, "links.txt")
            with open(links_file, "w", encoding="utf-8") as f:
                f.write(link.strip())

            # Step 1: Download
            self.current_step = f"[{link_idx}/{total}] Downloading"
            self._update_shared_state()
            if not self._run_command([sys.executable, DOWNLOAD_SCRIPT,
                                      "-i", links_file,
                                      "-o", link_temp_dir,
                                      "--library-dir", config.UPLOAD_FOLDER,
                                      "--fast"]):
                if self.output_mode == 'upload':
                    self._rmdir(link_temp_dir)
                return False

            # Step 2: PDF → Images
            self.current_step = f"[{link_idx}/{total}] Extracting Images"
            self._update_shared_state()
            if not self._run_command([sys.executable, PDF2IMG_SCRIPT,
                                      "-f", link_temp_dir, "--once"]):
                if self.output_mode == 'upload':
                    self._rmdir(link_temp_dir)
                return False

            # Step 3: OCR
            self.current_step = f"[{link_idx}/{total}] OCR Processing"
            self._update_shared_state()
            ocr_cmd = [sys.executable, OCR_SCRIPT,
                       "-f", link_temp_dir,
                       "--workers", str(self.workers),
                       "--lang", self.lang,
                       "--once"]
            api_url = os.environ.get('SAMSHO_OCR_API_URL', '')
            api_key = os.environ.get('SAMSHO_OCR_API_KEY', '')
            if api_url:
                ocr_cmd.extend(["--api-url", api_url])
            if api_key:
                ocr_cmd.extend(["--api-key", api_key])
            if not self._run_command(ocr_cmd):
                if self.output_mode == 'upload':
                    self._rmdir(link_temp_dir)
                return False

            # Step 4: Pack & Finalize
            self.current_step = f"[{link_idx}/{total}] Packing"
            self._update_shared_state()
            stage = (self.output_mode == 'zip')
            self._pack_books(link_temp_dir, stage=stage)

            # Upload mode: clean up the now-empty per-link temp dir
            if not stage:
                self._rmdir(link_temp_dir)

            return True

        except Exception as e:
            self.log(f"[ERR] Exception during link {link_idx}: {e}\n")
            if self.output_mode == 'upload':
                self._rmdir(link_temp_dir)
            return False

    def _rmdir(self, path):
        """Safely remove a directory and all its contents."""
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Book packing helpers
    # ──────────────────────────────────────────────────────────────
    def _pack_books(self, base_dir, stage=False):
        """Find all book folders in base_dir and pack each one."""
        for entry in os.listdir(base_dir):
            entry_path = os.path.join(base_dir, entry)
            if not os.path.isdir(entry_path) or entry == "tokens":
                continue

            # Find folders that contain data.txt (direct or one level deeper)
            folders_to_process = []
            if os.path.exists(os.path.join(entry_path, 'data.txt')):
                folders_to_process.append(entry_path)
            else:
                for sub in os.listdir(entry_path):
                    sub_path = os.path.join(entry_path, sub)
                    if os.path.isdir(sub_path) and \
                            os.path.exists(os.path.join(sub_path, 'data.txt')):
                        folders_to_process.append(sub_path)

            for folder in folders_to_process:
                self._pack_single_book(folder, stage=stage)

    def _pack_single_book(self, folder, stage=False):
        """SDL-pack one book folder, clean intermediates, then move to uploads or stage for ZIP."""
        name = os.path.basename(folder)
        self.log(f"[INFO] Packing: {name}\n")

        data_txt = os.path.join(folder, 'data.txt')
        if not os.path.exists(data_txt):
            self.log(f"[WARN] No data.txt in {name} — skipping pack.\n")
            return

        # 1. Create .sdl file
        with open(data_txt, 'r', encoding='utf-8') as f:
            text_content = f.read()

        sdl_path = os.path.join(folder, f"{name}.sdl")
        sdl_data = bytearray()
        sdl_data.extend(b'SDL\x03')
        cctx = zstd.ZstdCompressor(level=7)
        compressed = cctx.compress(text_content.encode('utf-8'))
        sdl_data.extend(compressed)

        with open(sdl_path, 'wb') as f:
            f.write(sdl_data)

        # 2. Remove intermediates (PDFs, image backup, markers)
        for fn in os.listdir(folder):
            if fn.lower().endswith('.pdf'):
                os.remove(os.path.join(folder, fn))

        backup_dir = os.path.join(folder, 'backup')
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)

        if os.path.exists(data_txt):
            os.remove(data_txt)

        for marker in ['_pages.txt', '_skipped.txt']:
            p = os.path.join(folder, marker)
            if os.path.exists(p):
                os.remove(p)

        # 2.5 Update metadata.txt with selection
        metadata_path = os.path.join(folder, 'metadata.txt')
        source_url = ""
        tags = ""
        subbooks_raw = ""
        notes = ""
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Source:'):
                            source_url = line.replace('Source:', '').strip()
                        elif line.startswith('Tags:'):
                            tags = line.replace('Tags:', '').strip()
                        elif line.startswith('Subbook:'):
                            pass
                        elif line.startswith('Level:'):
                            levels_raw = line.split(':', 1)[1].strip()
                        elif line.startswith('Notes:'):
                            notes = line.replace('Notes:', '').strip().replace('\\n', '\n')
            except:
                pass
                
        is_published = (self.status == 'published')
        tags = sanitize_tags_against_taxonomy(tags, published=is_published)
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                if source_url:
                    f.write(f"Source: {source_url}\n")
                if tags:
                    f.write(f"Tags: {tags}\n")
                if levels_raw:
                    f.write(f"Level: {levels_raw}\n")
                if notes:
                    escaped_notes = notes.replace('\r\n', '\n').replace('\n', '\\n')
                    f.write(f"Notes: {escaped_notes}\n")
                f.write(f"Published: {'true' if is_published else 'false'}\n")
        except Exception as e:
            self.log(f"[WARN] Failed to write publish status: {e}\n")

        # 3. Move to library or stage for ZIP
        if stage:
            self.staged_folders.append(folder)
            self.log(f"[OK] Staged for ZIP: {name}\n")
        else:
            dest_path = os.path.join(config.UPLOAD_FOLDER, name)
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.move(folder, dest_path)
            self.log(f"[OK] Saved to uploads/{name}\n")

            log_change(
                username=self.initiator,
                action="CREATE",
                entity_type="BOOK",
                entity_id=name,
                previous_data=None,
                after_data={"status": "Success", "source": "OCR Pipeline", "lang": self.lang}
            )

    # ──────────────────────────────────────────────────────────────
    # ZIP builder
    # ──────────────────────────────────────────────────────────────
    def build_zip(self):
        """Build a ZIP from all staged book folders and save it to the
        persistent pipeline_zips/<task_id>/ directory.
        Returns the path to the zip file."""
        task_out_dir = os.path.join(ZIP_OUTPUT_DIR, self.task_id)
        os.makedirs(task_out_dir, exist_ok=True)
        zip_path = os.path.join(task_out_dir, 'output.zip')

        book_names = []
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder in self.staged_folders:
                if not os.path.exists(folder):
                    continue
                folder_name = os.path.basename(folder)
                book_names.append(folder_name)
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname   = os.path.join(
                            folder_name,
                            os.path.relpath(file_path, folder)
                        )
                        zf.write(file_path, arcname)

        # Write companion metadata (for display after restart)
        info = {
            'task_id':    self.task_id,
            'created_at': self.created_at.isoformat(),
            'book_count': len(book_names),
            'books':      book_names,
            'initiator':  self.initiator,
            'lang':       self.lang,
        }
        with open(os.path.join(task_out_dir, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(info, f, indent=2, ensure_ascii=False)

        # Record book count on the task object (for live UI display)
        self._book_count = len(book_names)
        self.books = book_names

        # Clean up the now-unneeded staged temp folders
        self._rmdir(self.temp_output_dir)

        return zip_path

    # ──────────────────────────────────────────────────────────────
    # Subprocess runner (unchanged from original)
    # ──────────────────────────────────────────────────────────────
    def _run_command(self, cmd):
        if self.stop_requested: return False
        self.log(f"\n[STEP] Running: {' '.join(cmd)}\n")

        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,  # Unbuffered to get \r immediately
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # Use an incremental decoder to handle multi-byte UTF-8 (like █) correctly
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        buffer = ""
        import time
        last_check = time.time()

        while True:
            if time.time() - last_check > 0.5:
                self._check_abort_signal()
                last_check = time.time()

            if self.stop_requested:
                self.process.terminate()
                self.log("\n[INFO] Process terminated by user.")
                return False

            # Read one byte
            chunk = self.process.stdout.read(1)
            if not chunk:
                if self.process.poll() is not None:
                    break
                time.sleep(0.01)
                continue

            try:
                char = decoder.decode(chunk)
                if not char:
                    continue

                if char == '\r':
                    if buffer:
                        self.log('\r' + buffer)
                        buffer = ""
                elif char == '\n':
                    self.log(buffer + '\n')
                    buffer = ""
                else:
                    buffer += char
            except Exception:
                buffer += '?'

        # Final flush
        if buffer:
            self.log(buffer)

        return_code = self.process.wait()
        if return_code != 0:
            self.log(f"\n[ERR] Command failed with code {return_code}")
            return False
        return True


# ──────────────────────────────────────────────────────────────
# Auth decorators
# ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


def superadmin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('admin_role') != 'super':
            return jsonify({'error': 'Superadmin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ──────────────────────────────────────────────────────────────
# Route registration
# ──────────────────────────────────────────────────────────────
def register_pipeline_routes(app):

    @app.route('/admin/pipeline')
    @login_required
    def admin_pipeline_page():
        if session.get('admin_role') != 'super':
            return render_template('admin/forbidden.html', permission="SUPERADMIN"), 403
        return render_template('admin/ocr_pipeline.html')

    # ── Active task probe (for reconnect on page refresh) ──────────
    @app.route('/admin/api/pipeline/active')
    @login_required
    @superadmin_only
    def pipeline_active():
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        if not os.path.exists(shared_json):
            return jsonify({'success': False})

        try:
            with open(shared_json, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except:
            return jsonify({'success': False})

        if state.get('done'):
            return jsonify({'success': False})

        response = jsonify({
            'success': True,
            'task_id': state.get('task_id'),
            'current_step': state.get('current_step', 'Running'),
            'done': state.get('done', False),
            'task_success': state.get('success', False),
            'output_mode': state.get('output_mode', 'upload'),
            'staged_count': state.get('staged_count', 0),
            'created_at': state.get('created_at', '')
        })
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response

    # ── Start a new pipeline run ────────────────────────────────────
    @app.route('/admin/api/pipeline/start', methods=['POST'])
    @login_required
    @superadmin_only
    def pipeline_start():
        data = request.json or {}
        links = data.get('links', '')
        lang = data.get('lang', 'sa')
        workers = data.get('workers', 5)
        auto = data.get('auto', True)
        output_mode = data.get('output_mode', 'upload')  # 'upload' | 'zip'
        status = data.get('status', 'published')

        if not links:
            return jsonify({'error': 'No links provided'}), 400

        task_id = str(uuid.uuid4())[:8]
        username = session.get('admin_username', 'System')
        task = PipelineTask(task_id, links, lang, workers, auto,
                            initiator=username, output_mode=output_mode, status=status)
        PIPELINE_TASKS[task_id] = task

        thread = threading.Thread(target=task.run)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'output_mode': output_mode,
            'created_at': task.created_at.strftime('%Y%m%d_%H%M%S')
        })

    # ── Status ─────────────────────────────────────────────────────
    @app.route('/admin/api/pipeline/status/<task_id>')
    @login_required
    @superadmin_only
    def pipeline_status(task_id):
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        if os.path.exists(shared_json):
            try:
                with open(shared_json, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                if state.get('task_id') == task_id:
                    response = jsonify({
                        'status': 'Running' if not state.get('done') else 'Finished',
                        'current_step': state.get('current_step', ''),
                        'done': state.get('done', False),
                        'success': state.get('success', False),
                        'output_mode': state.get('output_mode', 'upload'),
                        'staged_count': state.get('staged_count', 0)
                    })
                    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                    return response
            except:
                pass

        # If not active, check if it's a completed ZIP task on disk
        task_dir = os.path.join(ZIP_OUTPUT_DIR, task_id)
        if os.path.exists(os.path.join(task_dir, 'output.zip')):
            info_path = os.path.join(task_dir, 'info.json')
            staged_count = 0
            if os.path.exists(info_path):
                try:
                    with open(info_path, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                        staged_count = info.get('book_count', 0)
                except:
                    pass
            response = jsonify({
                'status': 'Finished',
                'current_step': 'Ready for Download',
                'done': True,
                'success': True,
                'output_mode': 'zip',
                'staged_count': staged_count
            })
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            return response

        return jsonify({'error': 'Task not found'}), 404

    # ── Streaming logs ─────────────────────────────────────────────
    @app.route('/admin/api/pipeline/logs/<task_id>')
    @login_required
    @superadmin_only
    def pipeline_logs(task_id):
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        state = {}
        if os.path.exists(shared_json):
            try:
                with open(shared_json, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            except:
                pass

        if state.get('task_id') != task_id:
            # Task is no longer active
            return jsonify({'error': 'Task not found or no longer active'}), 404

        shared_log = os.path.join(ZIP_OUTPUT_DIR, 'active_task.log.jsonl')
        raw_lines = []
        if os.path.exists(shared_log):
            try:
                with open(shared_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            raw_lines.append(line)
            except:
                pass

        last_idx = int(request.args.get('last', 0))
        limit = int(request.args.get('limit', 0))
        total_count = len(raw_lines)

        if limit > 0 and last_idx == 0:
            start_idx = max(0, total_count - limit)
            selected_lines = raw_lines[start_idx:]
        else:
            selected_lines = raw_lines[last_idx:]

        new_logs = []
        for line in selected_lines:
            try:
                new_logs.append(json.loads(line))
            except:
                pass

        response = jsonify({
            'logs': new_logs,
            'done': state.get('done', False),
            'success': state.get('success', False),
            'current_step': state.get('current_step', ''),
            'progress': 0,
            'output_mode': state.get('output_mode', 'upload'),
            'staged_count': state.get('staged_count', 0),
            'total_count': total_count
        })
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response

    # ── Stop / abort ───────────────────────────────────────────────
    @app.route('/admin/api/pipeline/stop/<task_id>', methods=['POST'])
    @login_required
    @superadmin_only
    def pipeline_stop(task_id):
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        if os.path.exists(shared_json):
            try:
                with open(shared_json, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                if state.get('task_id') == task_id:
                    state['abort_signal'] = True
                    with open(shared_json, 'w', encoding='utf-8') as f:
                        json.dump(state, f)
            except:
                pass

        task = PIPELINE_TASKS.get(task_id)
        if task:
            task.stop_requested = True
            
        return jsonify({'success': True})

    # ── List all ZIP-mode tasks (persistent queue) ─────────────────
    @app.route('/admin/api/pipeline/zip_tasks')
    @login_required
    @superadmin_only
    def pipeline_zip_tasks():
        zip_tasks = get_completed_zip_tasks()
        
        # Check active task
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        if os.path.exists(shared_json):
            try:
                with open(shared_json, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                if state.get('output_mode') == 'zip' and not state.get('done'):
                    try:
                        created_dt = datetime.strptime(state.get('created_at', ''), '%Y%m%d_%H%M%S')
                    except:
                        created_dt = get_ist_now()
                        
                    zip_tasks.append({
                        'task_id': state.get('task_id'),
                        'created_at_dt': created_dt,
                        'created_at': created_dt.strftime('%Y-%m-%d %H:%M:%S'),
                        'default_filename': created_dt.strftime("sdl_%Y%m%d_%H%M%S"),
                        'done': False,
                        'success': False,
                        'staged_count': state.get('staged_count', 0),
                        'books': [],
                        'current_step': state.get('current_step', '')
                    })
            except:
                pass
                
        # Sort chronologically descending (newest first)
        zip_tasks.sort(key=lambda x: x['created_at_dt'], reverse=True)
        # Remove created_at_dt for JSON serialization
        for t in zip_tasks:
            t.pop('created_at_dt', None)
            
        response = jsonify({'tasks': zip_tasks})
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response

    # ── Download ZIP (with optional rename via ?filename=) ─────────
    @app.route('/admin/api/pipeline/download/<task_id>')
    @login_required
    @superadmin_only
    def pipeline_download(task_id):
        # The ZIP lives in pipeline_zips/<task_id>/output.zip
        zip_path = os.path.join(ZIP_OUTPUT_DIR, task_id, 'output.zip')
        if not os.path.exists(zip_path):
            return jsonify({'error': 'ZIP file not found on disk or not complete'}), 404

        info_path = os.path.join(ZIP_OUTPUT_DIR, task_id, 'info.json')
        created_at_dt = datetime.fromtimestamp(os.path.getmtime(zip_path))
        if os.path.exists(info_path):
            try:
                with open(info_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                created_at_dt = datetime.fromisoformat(info.get('created_at', created_at_dt.isoformat()))
            except:
                pass

        filename = request.args.get(
            'filename',
            created_at_dt.strftime("sdl_%Y%m%d_%H%M%S")
        )
        if not filename.lower().endswith('.zip'):
            filename += '.zip'
        filename = re.sub(r'[^\w\-\. ]', '_', filename)

        return send_file(zip_path, as_attachment=True,
                         download_name=filename, mimetype='application/zip')

    # ── Manual clear — deletes the task's ZIP folder and removes it ─
    @app.route('/admin/api/pipeline/clear/<task_id>', methods=['POST'])
    @login_required
    @superadmin_only
    def pipeline_clear(task_id):
        # Check active task JSON to see if we're trying to clear a running task
        shared_json = os.path.join(ZIP_OUTPUT_DIR, 'active_task.json')
        if os.path.exists(shared_json):
            try:
                with open(shared_json, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                if state.get('task_id') == task_id and not state.get('done'):
                    return jsonify({'error': 'Cannot clear a task that is still running'}), 400
            except:
                pass

        # Check if directory exists on disk
        task_zip_dir = os.path.join(ZIP_OUTPUT_DIR, task_id)
        if os.path.exists(task_zip_dir):
            try:
                trash_dir = os.path.join(ZIP_OUTPUT_DIR, f"{task_id}_deleted_{int(time.time())}")
                os.rename(task_zip_dir, trash_dir)
                
                def remove_readonly(func, path, excinfo):
                    import stat
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass
                
                shutil.rmtree(trash_dir, onerror=remove_readonly)
            except Exception as e:
                # Fallback to direct deletion if rename fails
                try:
                    def remove_readonly(func, path, excinfo):
                        import stat
                        try:
                            os.chmod(path, stat.S_IWRITE)
                            func(path)
                        except Exception:
                            pass
                    shutil.rmtree(task_zip_dir, onerror=remove_readonly)
                except Exception as e2:
                    return jsonify({'error': f'Failed to delete files: {str(e2)}'}), 500
        else:
            return jsonify({'error': 'Task not found'}), 404

        # Clean up temp output dir if it exists
        temp_dir = os.path.join(tempfile.gettempdir(), f"sdl_pipeline_{task_id}")
        if os.path.exists(temp_dir):
            try:
                def remove_readonly(func, path, excinfo):
                    import stat
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass
                shutil.rmtree(temp_dir, onerror=remove_readonly)
            except Exception:
                pass

        # Attempt to clean up PIPELINE_TASKS if it happens to be resident on this worker
        if task_id in PIPELINE_TASKS:
            del PIPELINE_TASKS[task_id]
            
        return jsonify({'success': True})



# Removed _scan_zip_outputs() to prevent populating in-memory PIPELINE_TASKS
