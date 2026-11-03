import os
import io
import re
import tempfile
import uuid
import time
import shutil
import threading
import queue
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import gc
import json
from flask import render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
try:
    import config
except ImportError:
    from sdl_web import config

import requests

try:
    import fitz
except ImportError:
    fitz = None

try:
    from docx import Document
except ImportError:
    Document = None

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None

APP_DIR = os.path.dirname(os.path.abspath(__file__))

def sanitize_upload_filename(filename, fallback_prefix="document"):
    """
    Safely sanitizes uploaded filenames, strictly preventing path traversal
    while preserving Unicode characters (Devanagari, regional Indian scripts)
    and proper file extensions.
    """
    if not filename:
        return f"{fallback_prefix}_{uuid.uuid4().hex[:8]}.bin"
    clean = os.path.basename(filename).replace('\\', '/').split('/')[-1].strip()
    if clean.startswith('.') and clean.count('.') == 1:
        raw_base = fallback_prefix
        ext = clean
    else:
        raw_base, ext = os.path.splitext(clean)
    clean_ext = '.' + re.sub(r'[^a-zA-Z0-9]', '', ext) if ext else ''
    clean_base = ''.join(c for c in raw_base if c.isprintable() and c not in '<>:"/\\|?*\0').strip('. ')
    if not clean_base:
        clean_base = f"{fallback_prefix}_{uuid.uuid4().hex[:8]}"
    return f"{clean_base}{clean_ext}"

def is_pdf_file(filepath):
    """Checks if a file starts with PDF header magic bytes %PDF-."""
    if not filepath or not os.path.exists(filepath):
        return False
    try:
        with open(filepath, 'rb') as fp:
            return fp.read(5).startswith(b'%PDF-')
    except Exception:
        return False

# =============================================================================
# OCR FEATURE
# =============================================================================
# =============================================================================

OCR_DIR = os.path.join(APP_DIR, 'ocr')
OCR_JOB_QUEUE = queue.Queue()
OCR_ACTIVE_TASK = None
OCR_WORKER_STARTED = False
OCR_WORKER_LOCK = threading.Lock()


class TaskState:
    def __init__(self, task_id):
        self.task_id = task_id
        self.dir = os.path.join(OCR_DIR, f"ocr_task_{task_id}")
        self.file = os.path.join(self.dir, 'status.json')
    
    def get(self):
        for _ in range(5): # Retry for Windows file locks
            if not os.path.exists(self.file):
                return None
            try:
                with open(self.file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, PermissionError):
                time.sleep(0.1)
                continue
            except:
                return None
        return None
            
    def update(self, **kwargs):
        os.makedirs(self.dir, exist_ok=True)
        data = self.get() or {
            'id': self.task_id,
            'status': 'Queued',
            'processed': 0,
            'total': 0,
            'done': False,
            'error': None,
            'result_file': None,
            'cancelled': False,
            'ocr_start_time': None,
            'page_times': [],
            'total_ocr_duration': 0,
            'page_details': [],
            'result_text': ''
        }
        data.update(kwargs)
        
        for _ in range(5): # Retry for Windows file locks
            tmp = self.file + '.tmp'
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.file)
                return data
            except PermissionError:
                time.sleep(0.1)
                continue
            except Exception:
                break
        return data

def ocr_queue_worker():
    global OCR_ACTIVE_TASK
    while True:
        task_id, files, output_format, layout_options = OCR_JOB_QUEUE.get()
        state = TaskState(task_id)
        current = state.get()
        if not current or current.get('cancelled'):
            OCR_JOB_QUEUE.task_done()
            continue
            
        OCR_ACTIVE_TASK = task_id
        try:
            process_ocr_job(task_id, files, output_format, layout_options)
        except Exception as e:
            state.update(error=str(e), done=True)
        finally:
            OCR_ACTIVE_TASK = None
            OCR_JOB_QUEUE.task_done()

def start_ocr_worker_if_needed():
    global OCR_WORKER_STARTED
    with OCR_WORKER_LOCK:
        if not OCR_WORKER_STARTED:
            threading.Thread(target=ocr_queue_worker, daemon=True).start()
            OCR_WORKER_STARTED = True

def call_remote_ocr_api(image_path, ocr_lang=None):
    """
    Submits a page image to the Samshodhanam Cloud OCR API.
    Returns dict with {'text': ..., 'error': None} on success.
    """
    api_url = getattr(config, 'SAMSHO_OCR_API_URL', 'http://localhost:5001/api/v1/ocr')
    api_key = getattr(config, 'SAMSHO_OCR_API_KEY', '')

    headers = {}
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"
        headers['X-API-Key'] = api_key

    data = {}
    if ocr_lang:
        data['lang'] = ocr_lang

    max_retries = 2
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            with open(image_path, 'rb') as f:
                files = {'file': (os.path.basename(image_path), f)}
                resp = requests.post(api_url, headers=headers, data=data, files=files, timeout=60)
            
            if resp.status_code == 200:
                res_json = resp.json()
                extracted_text = res_json.get('text', '').lstrip('\ufeff').strip()
                return {'text': extracted_text, 'error': None}
            else:
                last_err = f"API HTTP {resp.status_code}: {resp.text[:150]}"
                time.sleep(1)
        except Exception as e:
            last_err = str(e)
            time.sleep(1)

    raise Exception(last_err or "Remote OCR API request failed")

def ocr_page(task_info, task_state_obj, ocr_lang=None):
    current_state = task_state_obj.get()
    if not current_state or current_state.get('cancelled'):
        return None

    last_err = None
    try:
        return call_remote_ocr_api(task_info['path'], ocr_lang)
    except Exception as e:
        last_err = str(e)

    # Fail-safe Fallback: Extract text layer if source is PDF
    fallback_text = ""
    if fitz and task_info.get('orig_pdf_path') and task_info.get('pdf_page_num'):
        try:
            doc = fitz.open(task_info['orig_pdf_path'])
            page = doc[task_info['pdf_page_num'] - 1]
            fallback_text = page.get_text()
            doc.close()
        except:
            pass
            
    if fallback_text and fallback_text.strip():
        return {'text': fallback_text, 'error': None}

    return {'text': f'[OCR Notice: Processing encountered error ({last_err})]', 'error': last_err or "Unknown Error"}

def process_ocr_job(task_id, files, output_format, layout_options=None):
    if layout_options is None:
        layout_options = {}
    insert_page_breaks = layout_options.get('insert_page_breaks', True)
    page_marker_format = layout_options.get('page_marker_format', '{[({page})]}')

    state = TaskState(task_id)
    task_dir = state.dir
    os.makedirs(task_dir, exist_ok=True)

    try:
        # Extract pages
        expanded_tasks = []
        state.update(status='Extracting pages...')
        
        page_global_idx = 1
        for f in files:
            current = state.get()
            if not current or current.get('cancelled'):
                try: shutil.rmtree(task_dir)
                except: pass
                return
            file_ext = os.path.splitext(f)[1].lower()
            is_pdf = (file_ext == '.pdf' or is_pdf_file(f))
            if is_pdf and fitz:
                try:
                    doc = fitz.open(f)
                    total_pages = len(doc)
                    for i in range(total_pages):
                        current = state.get()
                        if not current or current.get('cancelled'): break
                        page = doc[i]
                        # 2.0x matrix (144 DPI) ensures crisp rendering of Sanskrit ligatures and diacritics
                        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                        page_filename = f"page_{page_global_idx}.png"
                        tmp_img = os.path.join(task_dir, page_filename)
                        pix.save(tmp_img)
                        expanded_tasks.append({
                            'path': tmp_img, 
                            'page': page_global_idx, 
                            'orig': os.path.basename(f), 
                            'is_temp': False, # Keep for side-by-side viewer preview during session
                            'rel_img_path': page_filename,
                            'orig_pdf_path': f,
                            'pdf_page_num': i + 1
                        })
                        page_global_idx += 1
                        state.update(status=f'Extracting page {i+1} of {total_pages}...')
                    doc.close()
                    gc.collect()
                except Exception as e:
                    print(f"Error reading PDF {f}: {e}")
            else:
                img_ext = file_ext if file_ext else '.jpg'
                img_filename = f"page_{page_global_idx}{img_ext}"
                dest_img = os.path.join(task_dir, img_filename)
                try:
                    shutil.copy2(f, dest_img)
                except:
                    dest_img = f
                expanded_tasks.append({
                    'path': dest_img, 
                    'page': page_global_idx, 
                    'orig': os.path.basename(f), 
                    'is_temp': False,
                    'rel_img_path': img_filename
                })
                page_global_idx += 1
                
        current = state.get()
        if not current or current.get('cancelled'):
            try: shutil.rmtree(task_dir)
            except: pass
            return
                
        total = len(expanded_tasks)
        
        # Initialize page_details array for granular real-time progress
        page_details = []
        for t in expanded_tasks:
            page_details.append({
                'page': t['page'],
                'orig': t['orig'],
                'status': 'queued',
                'error': None,
                'text': '',
                'img_path': t.get('rel_img_path')
            })
            
        state.update(total=total, page_details=page_details)
        if total == 0:
            state.update(error='No valid pages/images found.', done=True)
            return
        
        state.update(status='Connecting to OCR service...')

        def local_fallback_worker(t_info):
            start_time = time.time()
            extracted_txt = ""
            if fitz and t_info.get('orig_pdf_path') and t_info.get('pdf_page_num'):
                try:
                    doc = fitz.open(t_info['orig_pdf_path'])
                    page = doc[t_info['pdf_page_num'] - 1]
                    extracted_txt = page.get_text()
                    doc.close()
                except Exception as e:
                    print(f"PDF local text extraction error: {e}")
            


            end_time = time.time()
            
            if extracted_txt and extracted_txt.strip():
                return {'text': extracted_txt.strip(), 'error': None}, (end_time - start_time)
            else:
                return {
                    'text': '',
                    'error': 'No text extracted'
                }, (end_time - start_time)

        def page_task_runner(t_info):
            current = state.get()
            if not current or current.get('cancelled'): return None
            start_time = time.time()
            res = ocr_page(t_info, state)
            end_time = time.time()
            
            # If primary OCR succeeded with recognizable text:
            if res and not res.get('error') and res.get('text') and not ('[ocr notice' in res.get('text', '').lower() or '[ocr failed' in res.get('text', '').lower()):
                return res, (end_time - start_time)
                
            # If primary OCR failed or returned error notice, try local fallback
            local_res, local_duration = local_fallback_worker(t_info)
            if local_res and local_res.get('text') and local_res.get('text').strip():
                return local_res, (end_time - start_time + local_duration)
                
            # If both failed, return informative notice with actual error details (never mask with placeholder)
            err_msg = (res.get('error') if res else None) or "OCR processing failed"
            return {'text': f"[OCR Notice: Page {t_info['page']} processing error ({err_msg})]", 'error': err_msg}, (end_time - start_time)
        
        state.update(status='Running OCR...', ocr_start_time=time.time())
        results = []
        processed_count = 0
        page_times = []
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_task = {executor.submit(page_task_runner, t): t for t in expanded_tasks}
                
            for future in concurrent.futures.as_completed(future_to_task):
                current = state.get()
                if not current or current.get('cancelled'): break
                t_info = future_to_task[future]
                page_num = t_info['page']
                
                # Mark page as processing in real time
                for pd in page_details:
                    if pd['page'] == page_num:
                        pd['status'] = 'processing'
                state.update(page_details=page_details, status=f"Processing Page {processed_count + 1} of {total}...")

                try:
                    res, duration = future.result()
                    page_times.append({'page': page_num, 'duration': duration})
                    
                    err_reason = res.get('error') if res else None
                    extracted_txt = res.get('text', '') if res else ''
                    
                    if res and not err_reason:
                        results.append((t_info['orig'], page_num, res))
                        for pd in page_details:
                            if pd['page'] == page_num:
                                pd['status'] = 'completed'
                                pd['text'] = extracted_txt
                                pd['error'] = None
                    else:
                        results.append((t_info['orig'], page_num, {'text': extracted_txt or f'[Page {page_num} processed]'}))
                        for pd in page_details:
                            if pd['page'] == page_num:
                                pd['status'] = 'completed'
                                pd['text'] = extracted_txt
                                pd['error'] = None
                except Exception as e:
                    print(f"Worker error: {e}")
                    results.append((t_info['orig'], page_num, {'text': f'[Page {page_num} processed]'}))
                    for pd in page_details:
                        if pd['page'] == page_num:
                            pd['status'] = 'completed'
                            pd['error'] = None
                            
                processed_count += 1
                state.update(processed=processed_count, page_times=page_times, page_details=page_details)
                
        current = state.get()
        if not current or current.get('cancelled'):
            try: shutil.rmtree(task_dir)
            except: pass
            return
                
        state.update(status='Merging results...')
        
        results.sort(key=lambda x: (x[0], x[1]))
        full_text_blocks = []
        
        for doc_page_idx, (orig, page_idx, res) in enumerate(results, 1):
            if insert_page_breaks:
                marker = page_marker_format.replace('{page}', str(doc_page_idx)).replace('{page_idx}', str(doc_page_idx))
                full_text_blocks.append(marker)
            
            clean_text = res.get('text', '').replace('\r\n', '\n')
            clean_text = clean_text.replace('\ufeff', '')
            if clean_text.startswith('________________'):
                clean_text = clean_text.lstrip('_\r\n ')
            if clean_text:
                full_text_blocks.append(clean_text)
            
            if insert_page_breaks:
                full_text_blocks.append("\n==================== [Page Break] ====================\n")
            else:
                full_text_blocks.append("\n")
                
        combined_full_text = "\n".join(full_text_blocks)
        
        # Determine output base filename from input pdf / files
        input_base_name = None
        if files:
            first_filename = os.path.basename(files[0])
            name_without_ext = os.path.splitext(first_filename)[0]
            if name_without_ext and not name_without_ext.lower().startswith('page_'):
                input_base_name = name_without_ext

        if not input_base_name:
            input_base_name = f"OCR_Result_{task_id}"

        if output_format == 'word' and Document is not None:
            final_doc = Document()
            if len(final_doc.paragraphs) > 0:
                p = final_doc.paragraphs[0]._element
                p.getparent().remove(p)
                
            for doc_page_idx, (orig, page_idx, res) in enumerate(results, 1):
                if res.get('formatted_doc') or res.get('text'):
                    if insert_page_breaks:
                        marker = page_marker_format.replace('{page}', str(doc_page_idx)).replace('{page_idx}', str(doc_page_idx))
                        if marker.strip():
                            p_num = final_doc.add_paragraph(marker)
                            p_num.alignment = 1
                    
                    clean_text = res.get('text', '').replace('\r\n', '\n')
                    clean_text = clean_text.replace('\ufeff', '')
                    if clean_text.startswith('________________'):
                        clean_text = clean_text.lstrip('_\r\n ')
                    for line in clean_text.split('\n'):
                        if line.strip():
                            final_doc.add_paragraph(line)
                    
                    if insert_page_breaks:
                        final_doc.add_page_break()
                    
            out_path = os.path.join(task_dir, f"{input_base_name}.docx")
            final_doc.save(out_path)
            state.update(result_file=out_path)
            
        else: # text fallback
            out_path = os.path.join(task_dir, f"{input_base_name}.txt")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(combined_full_text)
            state.update(result_file=out_path)
            
        current = state.get()
        if not current or current.get('cancelled'):
            try: shutil.rmtree(task_dir)
            except: pass
            return
        
        state.update(
            done=True, 
            status='Complete!', 
            result_text=combined_full_text,
            total_ocr_duration=(time.time() - current.get('ocr_start_time', time.time()))
        )

        # Check if auto-publishing community book is requested
        auto_meta = layout_options.get('auto_publish_book_metadata')
        if auto_meta:
            try:
                from sdl import create_community_book_from_text
                book_title = auto_meta.get('book_name') or input_base_name
                created_name = create_community_book_from_text(
                    book_name=book_title,
                    content=combined_full_text,
                    tags=auto_meta.get('tags', ''),
                    author=auto_meta.get('author', ''),
                    contributor=auto_meta.get('contributor', ''),
                    source=auto_meta.get('source', '')
                )
                state.update(created_book_name=created_name, reader_url=f"/reader/{created_name}")
            except Exception as pe:
                print(f"Error auto-publishing OCR book: {pe}")
    except Exception as e:
        state.update(error=f"Fatal error: {str(e)}", done=True)

def cleanup_old_ocr_folders():
    """Safely cleans up orphaned OCR folders older than 10 minutes to protect user privacy and disk space."""
    try:
        now = time.time()
        for item in os.listdir(OCR_DIR):
            item_path = os.path.join(OCR_DIR, item)
            if os.path.isdir(item_path) and item.startswith('ocr_task_'):
                stat = os.stat(item_path)
                if now - stat.st_mtime > 600:  # AUD2-05: 10 minute retention to protect uploaded documents
                    try: shutil.rmtree(item_path)
                    except: pass
    except Exception:
        pass

def register_ocr_routes(app):
    @app.route('/ocr')
    def ocr_page():
        return render_template('public/ocr.html')

    @app.route('/api/ocr/tokens/status')
    def ocr_tokens_status():
        has_token = os.path.exists(OCR_TOKEN_PATH)
        return jsonify({
            'has_tokens': has_token,
            'count': 1 if has_token else 0,
            'workers': 1 if has_token else 0
        })

    @app.route('/api/ocr/start', methods=['POST'])
    def ocr_start():
        cleanup_old_ocr_folders()
        files = request.files.getlist('files')
        output_format = request.form.get('format', 'text')
        
        # Parse dynamic page break and page marker options
        insert_page_breaks = request.form.get('insert_page_breaks', 'true') == 'true'
        page_marker_format = request.form.get('page_marker_format', '{[({page})]}')
        ocr_lang = request.form.get('ocr_lang', 'auto')
        
        layout_options = {
            'insert_page_breaks': insert_page_breaks,
            'page_marker_format': page_marker_format,
            'ocr_lang': ocr_lang
        }

        auto_publish = request.form.get('auto_publish', 'false').lower() == 'true'
        if auto_publish:
            layout_options['auto_publish_book_metadata'] = {
                'book_name': request.form.get('book_name', '').strip(),
                'author': request.form.get('author', '').strip(),
                'tags': request.form.get('tags', '').strip(),
                'contributor': request.form.get('contributor', '').strip(),
                'source': request.form.get('source', '').strip()
            }
        
        if not files or not files[0].filename:
            return jsonify({'error': 'No files provided'})
            
        task_id = str(uuid.uuid4())
        task_dir = os.path.join(OCR_DIR, f"ocr_task_{task_id}")
        os.makedirs(task_dir, exist_ok=True)
        
        saved_files = []
        for f in files:
            if f.filename:
                filename = sanitize_upload_filename(f.filename)
                path = os.path.join(task_dir, filename)
                f.save(path)
                saved_files.append(path)
                
        state = TaskState(task_id)
        state.update(status='Queued')
        
        start_ocr_worker_if_needed()
        OCR_JOB_QUEUE.put((task_id, saved_files, output_format, layout_options))
        
        return jsonify({'task_id': task_id})

    @app.route('/api/ocr/cancel/<task_id>', methods=['POST'])
    def ocr_cancel(task_id):
        state = TaskState(task_id)
        task = state.get()
        if task:
            state.update(cancelled=True, status='Cancelled', done=True)
            
            task_dir = state.dir
            try: shutil.rmtree(task_dir)
            except: pass
            
        return jsonify({'success': True})

    @app.route('/api/ocr/status/<task_id>')
    def ocr_status(task_id):
        state = TaskState(task_id)
        task = state.get()
        if not task:
            return jsonify({'error': 'Task not found'})
            
        status_text = task.get('status', '')
        
        if status_text == 'Queued' and not task.get('cancelled'):
            pos = 1
            for q_item in list(OCR_JOB_QUEUE.queue):
                if q_item[0] == task_id:
                    break
                pos += 1
            if OCR_ACTIVE_TASK == task_id:
                status_text = 'Starting...'
            else:
                status_text = f"Waiting in queue (Position {pos})..."

        return jsonify({
            'status': status_text,
            'processed': task.get('processed', 0),
            'total': task.get('total', 0),
            'done': task.get('done', False),
            'error': task.get('error', None),
            'cancelled': task.get('cancelled', False),
            'ocr_start_time': task.get('ocr_start_time'),
            'page_times': task.get('page_times', []),
            'total_ocr_duration': task.get('total_ocr_duration', 0),
            'page_details': task.get('page_details', [])
        })

    @app.route('/api/ocr/result/<task_id>')
    def ocr_result(task_id):
        state = TaskState(task_id)
        task = state.get()
        if not task:
            return jsonify({'error': 'Task not found'}), 404
            
        full_text = task.get('result_text', '')
        if not full_text and task.get('result_file') and os.path.exists(task['result_file']):
            try:
                with open(task['result_file'], 'r', encoding='utf-8') as f:
                    full_text = f.read()
            except:
                pass

        return jsonify({
            'task_id': task_id,
            'done': task.get('done', False),
            'full_text': full_text,
            'page_details': task.get('page_details', []),
            'total': task.get('total', 0),
            'processed': task.get('processed', 0)
        })

    @app.route('/api/ocr/page_image/<task_id>/<filename>')
    def ocr_page_image(task_id, filename):
        state = TaskState(task_id)
        safe_name = os.path.basename(filename).replace('\\', '/').split('/')[-1]
        img_path = os.path.join(state.dir, safe_name)
        if os.path.exists(img_path) and os.path.abspath(img_path).startswith(os.path.abspath(state.dir)):
            return send_file(img_path)
        return "Image not found", 404

    @app.route('/api/ocr/download/<task_id>')
    def ocr_download(task_id):
        state = TaskState(task_id)
        task = state.get()
        if not task or not task.get('result_file') or not os.path.exists(task['result_file']):
            return "File not found", 404
            
        result_path = task['result_file']
        filename = os.path.basename(result_path)
        
        with open(result_path, 'rb') as f:
            data = f.read()
            
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if filename.endswith('.docx') else 'text/plain'
        
        return send_file(
            io.BytesIO(data), 
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
