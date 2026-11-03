import os
import io
import json
import zipfile
import threading
import uuid
import pandas as pd
from flask import request, jsonify, render_template, session, send_file
from functools import wraps
from admin_pipeline import login_required, superadmin_only
import config
from ai_search import load_book_full_text, chunk_text_by_paragraph, get_page_map, get_page_for_index, embed_pre_chunked_book, get_embedded_book_names, get_book_chunks, delete_book_embeddings

APP_DIR = os.path.dirname(os.path.abspath(__file__))

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


BULK_IMPORT_STATUS = {}

def run_bulk_import_in_background(task_id, file_bytes, is_zip, commit_directly, api_key, single_json_book_name=None):
    try:
        books_to_process = {} # book_name -> chunks_list
        
        if is_zip:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                json_files = [name for name in z.namelist() if name.endswith('.json') and not name.startswith('__MACOSX')]
                BULK_IMPORT_STATUS[task_id]['total'] = len(json_files)
                for name in json_files:
                    book_name = os.path.splitext(os.path.basename(name))[0]
                    try:
                        content = z.read(name).decode('utf-8')
                        chunks_data = json.loads(content)
                        if isinstance(chunks_data, list):
                            books_to_process[book_name] = chunks_data
                        else:
                            BULK_IMPORT_STATUS[task_id]['errors'].append(f"{name} is not a valid JSON array of chunks.")
                    except Exception as e:
                        BULK_IMPORT_STATUS[task_id]['errors'].append(f"Error parsing JSON file {name}: {str(e)}")
        else:
            # Single JSON file
            try:
                chunks_data = json.loads(file_bytes.decode('utf-8'))
                if isinstance(chunks_data, list):
                    books_to_process[single_json_book_name] = chunks_data
                else:
                    BULK_IMPORT_STATUS[task_id]['status'] = 'failed'
                    BULK_IMPORT_STATUS[task_id]['errors'].append("JSON file is not a valid array of chunks.")
                    BULK_IMPORT_STATUS[task_id]['done'] = True
                    return
            except Exception as e:
                BULK_IMPORT_STATUS[task_id]['status'] = 'failed'
                BULK_IMPORT_STATUS[task_id]['errors'].append(f"Error parsing JSON file: {str(e)}")
                BULK_IMPORT_STATUS[task_id]['done'] = True
                return
        
        total_books = len(books_to_process)
        BULK_IMPORT_STATUS[task_id]['total'] = total_books
        
        if total_books == 0:
            BULK_IMPORT_STATUS[task_id]['status'] = 'completed'
            BULK_IMPORT_STATUS[task_id]['done'] = True
            return

        for idx, (book_name, chunks) in enumerate(books_to_process.items()):
            try:
                from sdl import get_metadata_from_folder
                tags_str = ''
                dest_path = os.path.join(config.UPLOAD_FOLDER, book_name)
                if os.path.exists(dest_path):
                    metadata = get_metadata_from_folder(dest_path)
                    tags_str = metadata.get('tags', '')
                    
                success, err = embed_pre_chunked_book(book_name, chunks, tags_str, api_key)
                if not success:
                    BULK_IMPORT_STATUS[task_id]['errors'].append(f"Failed to embed '{book_name}': {err}")
                else:
                    BULK_IMPORT_STATUS[task_id]['processed_books'].append(book_name)
            except Exception as e:
                BULK_IMPORT_STATUS[task_id]['errors'].append(f"Error processing book '{book_name}': {str(e)}")
            
            BULK_IMPORT_STATUS[task_id]['progress'] = idx + 1
            
        BULK_IMPORT_STATUS[task_id]['status'] = 'completed'
        BULK_IMPORT_STATUS[task_id]['done'] = True
    except Exception as e:
        BULK_IMPORT_STATUS[task_id]['status'] = 'failed'
        BULK_IMPORT_STATUS[task_id]['errors'].append(f"Fatal bulk import error: {str(e)}")
        BULK_IMPORT_STATUS[task_id]['done'] = True

def register_chunking_routes(app):
    @app.route('/admin/vector-hub')
    @login_required
    def admin_vector_hub_page():
        if session.get('admin_role') != 'super':
            return render_template('admin/forbidden.html', permission="SUPERADMIN"), 403
        return render_template('admin/admin_chunk_tool.html')

    @app.route('/admin/verify-chunks')
    @login_required
    def admin_verify_chunks_page():
        from flask import redirect
        return redirect('/admin/vector-hub', 301)

    @app.route('/api/admin/library-books')
    @login_required
    @superadmin_only
    def api_library_books():
        upload_folder = config.UPLOAD_FOLDER
        if not os.path.exists(upload_folder):
            return jsonify({'success': True, 'books': []})
            
        books = []
        for name in os.listdir(upload_folder):
            if os.path.isdir(os.path.join(upload_folder, name)):
                books.append(name)
        return jsonify({'success': True, 'books': sorted(books)})

    @app.route('/api/admin/load-book-for-chunking', methods=['POST'])
    @login_required
    @superadmin_only
    def api_load_book_for_chunking():
        data = request.json
        book_name = data.get('book_name')
        if not book_name:
            return jsonify({'error': 'No book_name provided'}), 400
            
        full_text, err = load_book_full_text(book_name, config.UPLOAD_FOLDER)
        if err:
            return jsonify({'error': err}), 500
            
        from sdl import get_metadata_from_folder
        dest_path = os.path.join(config.UPLOAD_FOLDER, book_name)
        published = True
        if os.path.exists(dest_path):
            published = get_metadata_from_folder(dest_path).get('published', True)

        return jsonify({
            'success': True, 
            'full_text': full_text,
            'draft_chunks': None,
            'published': published
        })

    @app.route('/api/admin/commit-chunks', methods=['POST'])
    @login_required
    @superadmin_only
    def api_commit_chunks():
        data = request.json
        book_name = data.get('book_name')
        chunks_data = data.get('chunks', [])
        
        if not book_name or not chunks_data:
            return jsonify({'error': 'Missing book_name or chunks data'}), 400
            
        # Backend validation for empty chunks
        for chunk in chunks_data:
            has_text = False
            for k, v in chunk.items():
                if k in ("chunk_index", "page_number", "id", "tags", "book_name"):
                    continue
                if isinstance(v, list):
                    v_str = "".join(map(str, v)).strip()
                else:
                    v_str = str(v or "").strip()
                if v_str:
                    has_text = True
                    break
            if not has_text:
                return jsonify({'error': 'Blank chunks are not allowed when committing to Vector DB.'}), 400

        # Get tags string from metadata
        from sdl import get_metadata_from_folder
        metadata = get_metadata_from_folder(os.path.join(config.UPLOAD_FOLDER, book_name))
        tags_str = metadata.get('tags', '')
        
        # We need the api key
        from ai_search import load_api_key
        api_key = load_api_key()
        if not api_key:
            return jsonify({'error': 'Gemini API key not configured'}), 500
            
        success, err = embed_pre_chunked_book(book_name, chunks_data, tags_str, api_key)
        
        if not success:
            return jsonify({'error': err}), 500
            
        return jsonify({'success': True})

    @app.route('/api/admin/embedded-books')
    @login_required
    @superadmin_only
    def api_embedded_books():
        """Return list of book names that already have embeddings in ChromaDB."""
        names = get_embedded_book_names()
        book_info = []
        from ai_search import get_collection
        
        for name in sorted(names):
            chunk_count = 0
            try:
                collection = get_collection()
                res = collection.get(where={"book_name": name}, include=["metadatas"])
                chunk_count = len(res['ids']) if res and res.get('ids') else 0
            except Exception:
                chunk_count = 0
                
            book_info.append({
                'name': name,
                'chunk_count': chunk_count,
                'has_draft': False,
                'has_embeddings': True
            })
            
        return jsonify({'success': True, 'embedded_books': book_info})

    @app.route('/api/admin/load-embedded-chunks', methods=['POST'])
    @login_required
    @superadmin_only
    def api_load_embedded_chunks():
        """Load all chunks for a specific book from ChromaDB."""
        data = request.json
        book_name = data.get('book_name')
        if not book_name:
            return jsonify({'error': 'No book_name provided'}), 400
        
        # Check published status
        from sdl import get_metadata_from_folder
        dest_path = os.path.join(config.UPLOAD_FOLDER, book_name)
        published = True
        if os.path.exists(dest_path):
            published = get_metadata_from_folder(dest_path).get('published', True)

        chunks = get_book_chunks(book_name)
        if not chunks:
            return jsonify({'error': 'No chunks found for this book in ChromaDB'}), 404
        
        return jsonify({'success': True, 'chunks': chunks, 'total': len(chunks), 'is_draft': False, 'published': published})

    @app.route('/api/admin/set-publish-status', methods=['POST'])
    @login_required
    @superadmin_only
    def api_set_publish_status():
        data = request.json or {}
        book_name = data.get('book_name')
        published = data.get('published', True)
        if not book_name:
            return jsonify({'error': 'No book_name provided'}), 400
            
        from sdl import get_metadata_from_folder, CATALOG_METADATA_CACHE, save_catalog_cache
        dest_path = os.path.join(config.UPLOAD_FOLDER, book_name)
        if not os.path.exists(dest_path):
            return jsonify({'error': f"Book folder for '{book_name}' not found"}), 404
            
        metadata = get_metadata_from_folder(dest_path, bypass_cache=True)
        metadata_path = os.path.join(dest_path, 'metadata.txt')
        
        source_link = metadata.get('source', '')
        tags = sanitize_tags_against_taxonomy(metadata.get('tags', ''), published=published)
        subbooks_raw = metadata.get('subbooks_raw', '')
        notes = metadata.get('notes', '')
        
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                if source_link:
                    f.write(f"Source: {source_link}\n")
                if tags:
                    f.write(f"Tags: {tags}\n")
                if metadata.get('levels_raw'):
                    f.write(f"Level: {metadata['levels_raw']}\n")
                if notes:
                    escaped_notes = notes.replace('\r\n', '\n').replace('\n', '\\n')
                    f.write(f"Notes: {escaped_notes}\n")
                f.write(f"Published: {'true' if published else 'false'}\n")
                
            if book_name in CATALOG_METADATA_CACHE:
                del CATALOG_METADATA_CACHE[book_name]
            save_catalog_cache()
            
            return jsonify({'success': True, 'published': published})
        except Exception as e:
            return jsonify({'error': f"Failed to update publish status: {str(e)}"}), 500


    @app.route('/api/admin/delete-embedding', methods=['POST'])
    @login_required
    @superadmin_only
    def api_delete_embedding():
        """Delete all embeddings for a specific book from ChromaDB."""
        data = request.json
        book_name = data.get('book_name')
        if not book_name:
            return jsonify({'error': 'No book_name provided'}), 400
        
        # Delete embeddings in ChromaDB
        success = delete_book_embeddings(book_name)
        if not success:
            return jsonify({'error': 'Failed to delete embeddings from ChromaDB'}), 500
            
        return jsonify({'success': True})

    @app.route('/api/admin/export-book-zip/<book_name>')
    @login_required
    @superadmin_only
    def api_export_book_zip(book_name):
        import io
        import zipfile
        import json
        from flask import send_file
        
        chunks = get_book_chunks(book_name)
        if not chunks:
            return jsonify({'error': 'No chunks found for this book in ChromaDB'}), 404
            
        formatted_chunks = []
        for idx, c in enumerate(chunks):
            chunk_copy = dict(c)
            if 'chunk_index' not in chunk_copy:
                chunk_copy['chunk_index'] = idx
            if 'page_number' not in chunk_copy:
                chunk_copy['page_number'] = 0
            formatted_chunks.append(chunk_copy)
            
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            json_str = json.dumps(formatted_chunks, ensure_ascii=False, indent=2)
            z.writestr(f"{book_name}.json", json_str.encode('utf-8'))
        out.seek(0)
        
        return send_file(
            out,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{book_name}_chunks.zip"
        )

    @app.route('/api/admin/export-all-zip')
    @login_required
    @superadmin_only
    def api_export_all_zip():
        import io
        import zipfile
        import json
        from flask import send_file
        
        names = get_embedded_book_names()
        if not names:
            return jsonify({'error': 'No books/chunks found to export'}), 404
            
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for book_name in sorted(names):
                chunks = get_book_chunks(book_name)
                if chunks:
                    formatted_chunks = []
                    for idx, c in enumerate(chunks):
                        chunk_copy = dict(c)
                        if 'chunk_index' not in chunk_copy:
                            chunk_copy['chunk_index'] = idx
                        if 'page_number' not in chunk_copy:
                            chunk_copy['page_number'] = 0
                        formatted_chunks.append(chunk_copy)
                    json_str = json.dumps(formatted_chunks, ensure_ascii=False, indent=2)
                    z.writestr(f"{book_name}.json", json_str.encode('utf-8'))
                    
        out.seek(0)
        return send_file(
            out,
            mimetype='application/zip',
            as_attachment=True,
            download_name="all_books_chunks.zip"
        )

    @app.route('/api/admin/import-book-chunks/<book_name>', methods=['POST'])
    @login_required
    @superadmin_only
    def api_import_book_chunks(book_name):
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        filename = file.filename.lower()
        chunks = []
        import io
        import json
        import zipfile
        
        try:
            file_bytes = file.read()
            if filename.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    json_files = [name for name in z.namelist() if name.endswith('.json') and not name.startswith('__MACOSX')]
                    if not json_files:
                        return jsonify({'error': 'No JSON file found in ZIP'}), 400
                    content = z.read(json_files[0]).decode('utf-8')
                    chunks = json.loads(content)
                    if not isinstance(chunks, list):
                        return jsonify({'error': 'JSON content in ZIP is not a list of chunks'}), 400
            elif filename.endswith('.json'):
                chunks = json.loads(file_bytes.decode('utf-8'))
                if not isinstance(chunks, list):
                    return jsonify({'error': 'JSON content is not a list of chunks'}), 400
            else:
                return jsonify({'error': 'Unsupported file format. Please upload .zip or .json'}), 400
        except Exception as e:
            return jsonify({'error': f"Failed to parse file: {str(e)}"}), 500
            
        if not chunks:
            return jsonify({'error': 'No chunks found in file'}), 400
            
        from ai_search import load_api_key
        api_key = load_api_key()
        if not api_key:
            return jsonify({'error': 'Gemini API key not configured'}), 500
            
        from sdl import get_metadata_from_folder
        tags_str = ''
        dest_path = os.path.join(config.UPLOAD_FOLDER, book_name)
        if os.path.exists(dest_path):
            metadata = get_metadata_from_folder(dest_path)
            tags_str = metadata.get('tags', '')
            
        success, err = embed_pre_chunked_book(book_name, chunks, tags_str, api_key)
        if not success:
            return jsonify({'error': f"Embedding failed: {err}"}), 500
                
        return jsonify({'success': True, 'chunks': chunks, 'is_draft': False})

    @app.route('/api/admin/import-bulk-chunks', methods=['POST'])
    @login_required
    @superadmin_only
    def api_import_bulk_chunks():
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        filename = file.filename.lower()
        
        if filename.endswith('.zip'):
            is_zip = True
            single_json_book_name = None
        elif filename.endswith('.json'):
            is_zip = False
            single_json_book_name = os.path.splitext(os.path.basename(file.filename))[0]
        else:
            return jsonify({'error': 'Unsupported file format. Please upload a .zip or .json file.'}), 400
            
        file_bytes = file.read()
        
        from ai_search import load_api_key
        api_key = load_api_key()
        if not api_key:
            return jsonify({'error': 'Gemini API key not configured'}), 500
        
        import uuid
        import threading
        task_id = str(uuid.uuid4())[:8]
        BULK_IMPORT_STATUS[task_id] = {
            'status': 'processing',
            'progress': 0,
            'total': 0,
            'processed_books': [],
            'errors': [],
            'done': False
        }
        
        thread = threading.Thread(
            target=run_bulk_import_in_background,
            args=(task_id, file_bytes, is_zip, True, api_key),
            kwargs={'single_json_book_name': single_json_book_name}
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'task_id': task_id})

    @app.route('/api/admin/import-tasks/<task_id>')
    @login_required
    @superadmin_only
    def api_import_task_status(task_id):
        status = BULK_IMPORT_STATUS.get(task_id)
        if not status:
            return jsonify({'error': 'Task not found'}), 404
        return jsonify(status)

    @app.route('/api/admin/import-vector-db', methods=['POST'])
    @login_required
    @superadmin_only
    def api_import_vector_db():
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        filename = file.filename.lower()
        import io
        import json
        import zipfile
        
        try:
            file_bytes = file.read()
            if filename.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    json_files = [name for name in z.namelist() if name.endswith('.json') and not name.startswith('__MACOSX')]
                    if not json_files:
                        return jsonify({'error': 'No JSON file found in ZIP'}), 400
                    content = z.read(json_files[0]).decode('utf-8')
                    vector_data = json.loads(content)
            elif filename.endswith('.json'):
                vector_data = json.loads(file_bytes.decode('utf-8'))
            else:
                return jsonify({'error': 'Unsupported file format. Please upload .json or .zip'}), 400
        except Exception as e:
            return jsonify({'error': f"Failed to parse file: {str(e)}"}), 500
            
        if not isinstance(vector_data, list):
            if isinstance(vector_data, dict) and 'vectors' in vector_data:
                vector_data = vector_data['vectors']
            else:
                return jsonify({'error': 'JSON content must be a list of vector objects'}), 400
                
        if not vector_data:
            return jsonify({'error': 'No vector data found in file'}), 400
            
        from ai_search import init_chroma_db, get_collection
        
        reset_collection = request.form.get('reset_collection') == 'true'
        if reset_collection:
            try:
                client = init_chroma_db()
                client.delete_collection("sdl_book_chunks")
            except Exception as reset_err:
                print(f"Reset collection warning: {str(reset_err)}")
                
        try:
            collection = get_collection()
            
            ids = []
            embeddings = []
            metadatas = []
            
            for item in vector_data:
                if 'embedding' not in item or not item['embedding']:
                    continue
                    
                book_name = item.get('book_name', 'unknown')
                chunk_index = item.get('chunk_index', 0)
                page_number = item.get('page_number', 0)
                
                chunk_id = item.get('id') or f"{book_name}_c{chunk_index}"
                
                metadata_dict = {
                    'book_name': book_name,
                    'chunk_index': int(chunk_index),
                    'page_number': int(page_number)
                }
                
                ids.append(chunk_id)
                embeddings.append(item['embedding'])
                metadatas.append(metadata_dict)
                
            if not ids:
                return jsonify({'error': 'No valid vector embedding objects found in file'}), 400
                
            # Perform upsert in batches of 500
            batch_size = 500
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i+batch_size]
                batch_embeddings = embeddings[i:i+batch_size]
                batch_metadatas = metadatas[i:i+batch_size]
                
                collection.upsert(
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas
                )
                
            return jsonify({
                'success': True,
                'message': f"Successfully imported {len(ids)} vector embeddings into ChromaDB."
            })
        except Exception as e:
            err_msg = str(e)
            if "dimension" in err_msg or "expecting" in err_msg:
                import re
                expected_match = re.search(r'expecting.*dimension of (\d+)', err_msg, re.IGNORECASE)
                got_match = re.search(r'got (\d+)', err_msg, re.IGNORECASE)
                expected_dim = expected_match.group(1) if expected_match else "4096"
                got_dim = got_match.group(1) if got_match else "3072"
                
                return jsonify({
                    'success': False,
                    'dimension_mismatch': True,
                    'expected': expected_dim,
                    'got': got_dim,
                    'error': f"Dimension mismatch: The collection is set to {expected_dim} dimensions, but the file has {got_dim} dimensions. Reset is required to load these vectors."
                }), 400
            return jsonify({'error': f"ChromaDB import error: {str(e)}"}), 500

    # =========================================================================
    # USER VECTOR REQUESTS & DOWNLOAD ACTIONS
    # =========================================================================

    @app.route('/api/user/vector-requests')
    def api_user_vector_requests():
        from sdl import user_login_required
        from db import common_db
        @user_login_required
        def handle():
            user_id = session.get('user_id')
            all_embedded_books = get_embedded_book_names()
            user_reqs = {r['book_name']: r for r in common_db.get_user_vector_requests(user_id)}
            
            result = []
            for book_name in all_embedded_books:
                req = user_reqs.get(book_name)
                status = 'none'
                if req:
                    status = req['status']
                result.append({
                    'book_name': book_name,
                    'status': status
                })
            return jsonify({'success': True, 'requests': result})
        return handle()

    @app.route('/api/user/request-vector-download', methods=['POST'])
    def api_user_request_vector_download():
        from sdl import user_login_required
        from db import common_db
        from cryptography.fernet import Fernet
        @user_login_required
        def handle():
            user_id = session.get('user_id')
            data = request.json or {}
            book_name = data.get('book_name')
            if not book_name:
                return jsonify({'error': 'book_name is required'}), 400
                
            all_embedded_books = get_embedded_book_names()
            if book_name not in all_embedded_books:
                return jsonify({'error': 'Book is not indexed in ChromaDB yet'}), 400
                
            existing = common_db.get_vector_request(user_id, book_name)
            if existing and existing['status'] in ('pending', 'approved'):
                return jsonify({'success': True, 'message': 'Request already exists', 'status': existing['status']})
                
            key = Fernet.generate_key().decode()
            success = common_db.create_vector_request(user_id, book_name, key)
            if success:
                return jsonify({'success': True, 'message': 'Request submitted successfully', 'status': 'pending'})
            else:
                return jsonify({'error': 'Failed to submit request'}), 500
        return handle()

    @app.route('/api/user/download-vector-db/<book_name>')
    def api_user_download_vector_db(book_name):
        from sdl import user_login_required
        from db import common_db
        from ai_search import get_collection, unpack_metadata
        from cryptography.fernet import Fernet
        import io
        import zipfile
        @user_login_required
        def handle():
            try:
                user_id = session.get('user_id')
                
                # Create request if not exists
                req = common_db.get_vector_request(user_id, book_name)
                if not req:
                    key = Fernet.generate_key().decode()
                    common_db.create_vector_request(user_id, book_name, key)
                    req = common_db.get_vector_request(user_id, book_name)
                    
                decryption_key = req['decryption_key']
                
                try:
                    collection = get_collection()
                    res = collection.get(
                        where={"book_name": book_name},
                        include=["metadatas", "embeddings"]
                    )
                except Exception as e:
                    return jsonify({'error': f"ChromaDB error: {str(e)}"}), 500
                    
                if not res or not res.get('metadatas'):
                    return jsonify({'error': f"No vector data found for '{book_name}'"}), 404
                    
                data_to_export = []
                for idx, meta in enumerate(res['metadatas']):
                    has_embeddings = res.get('embeddings') is not None and len(res['embeddings']) > idx
                    embedding_raw = res['embeddings'][idx] if has_embeddings else []
                    
                    if hasattr(embedding_raw, 'tolist'):
                        embedding = embedding_raw.tolist()
                    elif embedding_raw is not None:
                        embedding = list(embedding_raw)
                    else:
                        embedding = []
                        
                    chunk_id = res['ids'][idx] if res.get('ids') else f"{book_name}_c{idx}"
                    unpacked = unpack_metadata(meta)
                    
                    data_to_export.append({
                        'id': chunk_id,
                        'book_name': book_name,
                        'chunk_index': unpacked.get('chunk_index', idx),
                        'page_number': unpacked.get('page_number', 0),
                        'embedding': embedding
                    })
                    
                json_str = json.dumps(data_to_export, ensure_ascii=False, indent=2)
                fernet = Fernet(decryption_key.encode())
                encrypted_data = fernet.encrypt(json_str.encode('utf-8'))
                
                guidelines_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Vector DB Decryption Guidelines</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #0f172a; color: #e2e8f0; }}
        h1, h2 {{ color: #38bdf8; }}
        code {{ background-color: #1e293b; color: #f472b6; padding: 2px 6px; border-radius: 4px; font-family: 'Courier New', Courier, monospace; font-size: 14px; }}
        pre {{ background-color: #1e293b; padding: 15px; border-radius: 8px; overflow-x: auto; border: 1px solid #334155; }}
        .note {{ background-color: #1e1b4b; border-left: 4px solid #6366f1; padding: 15px; border-radius: 4px; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>🔑 Vector Database Decryption Guidelines</h1>
    <p>This archive contains the encrypted vector embedding dataset for <strong>"{book_name}"</strong>.</p>
    
    <div class="note">
        <strong>IMPORTANT:</strong> The dataset file <code>vector_data.enc</code> is encrypted using AES-128 (via Fernet). 
        You will receive your unique decryption key by email (at your registered address) once the Super Admin approves your access request.
    </div>

    <h2>How to Decrypt and Use</h2>
    <p>Once you receive the decryption key in your email, you can use the following Python script to decrypt the data. Make sure you have the <code>cryptography</code> library installed (run <code>pip install cryptography</code> if needed).</p>

    <pre><code>import json
from cryptography.fernet import Fernet

# Paste the unique key sent to your email here
DECRYPTION_KEY = "YOUR_RECEIVED_KEY_HERE"

# Load the encrypted data
with open("vector_data.enc", "rb") as f:
    encrypted_data = f.read()

# Decrypt
fernet = Fernet(DECRYPTION_KEY.encode())
decrypted_bytes = fernet.decrypt(encrypted_data)
vector_data = json.loads(decrypted_bytes.decode('utf-8'))

print(f"Decrypted {{len(vector_data)}} vector embeddings successfully!")
# Example of vector data structure:
# [
#   {{
#     "id": "{book_name}_c0",
#     "book_name": "{book_name}",
#     "chunk_index": 0,
#     "page_number": 1,
#     "embedding": [...]
#   }},
#   ...
# ]
</code></pre>

    <h2>Terms of Use</h2>
    <p>This vector dataset is provided for <strong>non-commercial educational and research AI purposes only</strong>. The raw corpus text has been completely omitted to comply with source distribution guidelines.</p>
</body>
</html>"""

                out = io.BytesIO()
                with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr("vector_data.enc", encrypted_data)
                    z.writestr("guidelines.html", guidelines_html.encode('utf-8'))
                out.seek(0)
                
                return send_file(
                    out,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f"{book_name}_encrypted_vectors.zip"
                )
            except Exception as err:
                import traceback
                traceback.print_exc()
                return jsonify({'error': f"Internal server error: {str(err)}", 'traceback': traceback.format_exc()}), 500
        return handle()

    # =========================================================================
    # SUPER ADMIN APPROVALS & VECTOR ACTIONS
    # =========================================================================

    @app.route('/api/admin/vector-download-requests')
    @login_required
    @superadmin_only
    def api_admin_vector_download_requests():
        from db import common_db
        reqs = common_db.get_all_vector_requests()
        return jsonify({'success': True, 'requests': reqs})

    @app.route('/api/admin/approve-vector-requests', methods=['POST'])
    @login_required
    @superadmin_only
    def api_admin_approve_vector_requests():
        from db import common_db
        from sdl import send_vector_approval_email
        data = request.json or {}
        request_ids = data.get('request_ids', [])
        if not request_ids:
            return jsonify({'error': 'No request IDs provided'}), 400
            
        approved_reqs = common_db.approve_vector_requests(request_ids)
        email_count = 0
        for req in approved_reqs:
            success = send_vector_approval_email(req['email'], req['book_name'], req['decryption_key'])
            if success:
                email_count += 1
                 
        return jsonify({'success': True, 'message': f'Approved {len(approved_reqs)} requests. Sent {email_count} emails.'})

    @app.route('/api/admin/reject-vector-requests', methods=['POST'])
    @login_required
    @superadmin_only
    def api_admin_reject_vector_requests():
        from db import common_db
        data = request.json or {}
        request_ids = data.get('request_ids', [])
        if not request_ids:
            return jsonify({'error': 'No request IDs provided'}), 400
            
        success = common_db.reject_vector_requests(request_ids)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to reject requests'}), 500

    @app.route('/api/admin/download-vector-db/<book_name>')
    @login_required
    @superadmin_only
    def api_admin_download_vector_db(book_name):
        from ai_search import get_collection, unpack_metadata
        import io
        import zipfile
        
        try:
            try:
                collection = get_collection()
                res = collection.get(
                    where={"book_name": book_name},
                    include=["metadatas", "embeddings"]
                )
            except Exception as e:
                return jsonify({'error': f"ChromaDB error: {str(e)}"}), 500
                
            if not res or not res.get('metadatas'):
                return jsonify({'error': f"No vector data found for '{book_name}'"}), 404
                
            data_to_export = []
            for idx, meta in enumerate(res['metadatas']):
                has_embeddings = res.get('embeddings') is not None and len(res['embeddings']) > idx
                embedding_raw = res['embeddings'][idx] if has_embeddings else []
                
                if hasattr(embedding_raw, 'tolist'):
                    embedding = embedding_raw.tolist()
                elif embedding_raw is not None:
                    embedding = list(embedding_raw)
                else:
                    embedding = []
                    
                chunk_id = res['ids'][idx] if res.get('ids') else f"{book_name}_c{idx}"
                unpacked = unpack_metadata(meta)
                
                data_to_export.append({
                    'id': chunk_id,
                    'book_name': book_name,
                    'chunk_index': unpacked.get('chunk_index', idx),
                    'page_number': unpacked.get('page_number', 0),
                    'embedding': embedding
                })
                
            json_str = json.dumps(data_to_export, ensure_ascii=False, indent=2)
            
            guidelines_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Vector DB Decryption Guidelines</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #0f172a; color: #e2e8f0; }}
        h1, h2 {{ color: #38bdf8; }}
        code {{ background-color: #1e293b; color: #f472b6; padding: 2px 6px; border-radius: 4px; font-family: 'Courier New', Courier, monospace; font-size: 14px; }}
        pre {{ background-color: #1e293b; padding: 15px; border-radius: 8px; overflow-x: auto; border: 1px solid #334155; }}
    </style>
</head>
<body>
    <h1>🔑 Plain Vector Database</h1>
    <p>This archive contains the plain vector embedding dataset for <strong>"{book_name}"</strong>.</p>
    <p>Since you are a Super Admin, this file is not encrypted.</p>
    <h2>Vector Structure</h2>
    <p>The vector data is loaded directly from <code>vector_data.json</code>.</p>
</body>
</html>"""

            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr("vector_data.json", json_str.encode('utf-8'))
                z.writestr("guidelines.html", guidelines_html.encode('utf-8'))
            out.seek(0)
            
            return send_file(
                out,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{book_name}_vectors.zip"
            )
        except Exception as err:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f"Internal server error: {str(err)}", 'traceback': traceback.format_exc()}), 500

    @app.route('/api/admin/bulk-delete-embeddings', methods=['POST'])
    @login_required
    @superadmin_only
    def api_admin_bulk_delete_embeddings():
        data = request.json or {}
        books = data.get('books', [])
        if not books:
            return jsonify({'error': 'No books provided'}), 400
            
        deleted_count = 0
        for book_name in books:
            success = delete_book_embeddings(book_name)
            if success:
                deleted_count += 1
                 
        return jsonify({'success': True, 'deleted': deleted_count, 'total': len(books)})

    @app.route('/api/admin/bulk-export-zip', methods=['POST'])
    @login_required
    @superadmin_only
    def api_admin_bulk_export_zip():
        import io
        import zipfile
        import json
        
        data = request.json or {}
        books = data.get('books', [])
        if not books:
            return jsonify({'error': 'No books provided'}), 400
            
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for book_name in books:
                chunks = get_book_chunks(book_name)
                if chunks:
                    formatted_chunks = []
                    for idx, c in enumerate(chunks):
                        chunk_copy = dict(c)
                        if 'chunk_index' not in chunk_copy:
                            chunk_copy['chunk_index'] = idx
                        if 'page_number' not in chunk_copy:
                            chunk_copy['page_number'] = 0
                        formatted_chunks.append(chunk_copy)
                    json_str = json.dumps(formatted_chunks, ensure_ascii=False, indent=2)
                    z.writestr(f"{book_name}.json", json_str.encode('utf-8'))
                     
        out.seek(0)
        return send_file(
            out,
            mimetype='application/zip',
            as_attachment=True,
            download_name="selected_books_chunks.zip"
        )



