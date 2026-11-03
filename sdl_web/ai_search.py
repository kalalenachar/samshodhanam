import os
import re
import json
import time
import tempfile
import warnings
import zstandard as zstd

# Silence legacy package deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import chromadb
except ImportError:
    chromadb = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

import config

_chroma_client = None

def init_chroma_db():
    global _chroma_client
    if chromadb is None:
        return None
    if _chroma_client is None:
        os.makedirs(config.CHROMA_DB_PATH, exist_ok=True)
        # Using persistent client to write and read database locally
        _chroma_client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
    return _chroma_client

def get_collection():
    client = init_chroma_db()
    # We manage the embeddings manually, so no default embedding function is needed.
    return client.get_or_create_collection(name="sdl_book_chunks")

def is_system_key(api_key):
    """Check if the provided API key is the configured system key."""
    if not api_key:
        return True
    system_key = config.get_gemini_api_key()
    return api_key == system_key

def get_gemini_embedding(text, api_key, is_query=False):
    """Generate embedding vector using models/gemini-embedding-2."""
    try:
        effective_key = api_key or config.get_gemini_api_key()
        genai.configure(api_key=effective_key)
        task_type = "retrieval_query" if is_query else "retrieval_document"
        response = genai.embed_content(
            model="models/gemini-embedding-2",
            content=text,
            task_type=task_type
        )
        return response['embedding']
    except Exception as e:
        print(f"Error calling Gemini embedding: {e}")
        return None

def get_page_map(text_content):
    """Build a map of character indices to page numbers using {[(N)]} format."""
    page_map = []
    page_pattern = r'\{\[\((\d+)\)\]\}'
    for match in re.finditer(page_pattern, text_content):
        end = match.end()
        try:
            page_num = int(match.group(1))
            page_map.append((end, page_num))
        except ValueError:
            pass
    return page_map

def get_page_for_index(index, page_map):
    """Find the page number corresponding to a character index."""
    if not page_map:
        return 0
    current_page = 0
    for start_pos, page_num in page_map:
        if start_pos <= index:
            current_page = page_num
        else:
            break
    return current_page

def split_long_paragraph(start_idx, end_idx, text_segment, max_chunk_size):
    """Fallback utility to split a long paragraph by newlines or words."""
    lines = []
    pattern = re.compile(r'\r?\n')
    last_end = 0
    for match in pattern.finditer(text_segment):
        start, end = match.span()
        if start > last_end:
            lines.append((last_end, start, text_segment[last_end:start]))
        last_end = end
    if last_end < len(text_segment):
        lines.append((last_end, len(text_segment), text_segment[last_end:]))
    
    chunks = []
    current_chunk_parts = []
    current_chunk_start = 0
    current_chunk_len = 0
    
    for l_start, l_end, l_text in lines:
        if current_chunk_len + len(l_text) > max_chunk_size and current_chunk_parts:
            chunk_content = "".join([x[2] for x in current_chunk_parts])
            chunks.append((start_idx + current_chunk_start, start_idx + l_start, chunk_content))
            current_chunk_parts = []
            current_chunk_start = l_start
            current_chunk_len = 0
        
        current_chunk_parts.append((l_start, l_end, l_text))
        current_chunk_len += len(l_text)
        
    if current_chunk_parts:
        chunk_content = "".join([x[2] for x in current_chunk_parts])
        chunks.append((start_idx + current_chunk_start, end_idx, chunk_content))
        
    # Final word-level split fallback if still too long
    final_chunks = []
    for c_start, c_end, c_text in chunks:
        if len(c_text) > max_chunk_size:
            words = c_text.split(' ')
            sub_chunk_parts = []
            sub_chunk_start = 0
            sub_chunk_len = 0
            for word in words:
                if sub_chunk_len + len(word) + 1 > max_chunk_size and sub_chunk_parts:
                    sub_content = " ".join(sub_chunk_parts)
                    final_chunks.append((c_start + sub_chunk_start, c_start + sub_chunk_start + len(sub_content), sub_content))
                    sub_chunk_start += len(sub_content) + 1
                    sub_chunk_parts = [word]
                    sub_chunk_len = len(word)
                else:
                    sub_chunk_parts.append(word)
                    sub_chunk_len += len(word) + 1
            if sub_chunk_parts:
                sub_content = " ".join(sub_chunk_parts)
                final_chunks.append((c_start + sub_chunk_start, c_end, sub_content))
        else:
            final_chunks.append((c_start, c_end, c_text))
            
    return final_chunks

def chunk_text_by_paragraph(text, min_chunk_size=150, max_chunk_size=1200):
    """Split text into paragraph-level chunks with minimum/maximum constraints."""
    raw_paragraphs = []
    pattern = re.compile(r'(\r?\n\s*){2,}')
    last_end = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_end:
            raw_paragraphs.append((last_end, start, text[last_end:start]))
        last_end = end
    if last_end < len(text):
        raw_paragraphs.append((last_end, len(text), text[last_end:]))
        
    processed_paragraphs = []
    for start, end, p_text in raw_paragraphs:
        if len(p_text.strip()) == 0:
            continue
        if len(p_text) > max_chunk_size:
            sub_chunks = split_long_paragraph(start, end, p_text, max_chunk_size)
            processed_paragraphs.extend(sub_chunks)
        else:
            processed_paragraphs.append((start, end, p_text))
            
    merged_chunks = []
    curr_start = None
    curr_parts = []
    curr_len = 0
    
    for start, end, p_text in processed_paragraphs:
        if curr_start is None:
            curr_start = start
        
        curr_parts.append(p_text)
        curr_len += len(p_text)
        
        if curr_len >= min_chunk_size:
            merged_chunks.append((curr_start, end, "\n\n".join(curr_parts)))
            curr_start = None
            curr_parts = []
            curr_len = 0
            
    if curr_parts:
        last_content = "\n\n".join(curr_parts)
        if merged_chunks and (len(last_content) + len(merged_chunks[-1][2]) <= max_chunk_size):
            prev_start, prev_end, prev_content = merged_chunks.pop()
            merged_chunks.append((prev_start, end, prev_content + "\n\n" + last_content))
        else:
            merged_chunks.append((curr_start or 0, len(text), last_content))
            
    return merged_chunks

def get_cached_file_content(file_path):
    """Self-contained helper to read / decompress file content."""
    if file_path.endswith('.sdl'):
        with open(file_path, 'rb') as f:
            data = f.read()
        if data.startswith(b'SDL\x03'):
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(data[4:]).decode('utf-8')
        return ""
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

def load_book_full_text(book_name, upload_folder):
    """Read all text and .sdl files inside a book folder."""
    folder_path = os.path.join(upload_folder, book_name)
    if not os.path.exists(folder_path):
        return None, "Folder does not exist"
    
    txt_files = [f for f in sorted(os.listdir(folder_path)) 
                if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
    
    if not txt_files:
        return None, "No text/sdl files found"
        
    full_text = ""
    for txt_file in txt_files:
        try:
            full_text += get_cached_file_content(os.path.join(folder_path, txt_file)) + "\n"
        except Exception as e:
            print(f"Error reading file {txt_file} in {book_name}: {e}")
            
    return full_text, None

def embed_book(book_name, upload_folder, api_key, progress_callback=None):
    """Decompress, chunk, embed, and index a book folder's contents in ChromaDB."""
    full_text, err = load_book_full_text(book_name, upload_folder)
    if err:
        return False, err
        
    from sdl import get_metadata_from_folder
    metadata = get_metadata_from_folder(os.path.join(upload_folder, book_name))
    tags_str = metadata.get('tags', '')
    
    page_map = get_page_map(full_text)
    raw_chunks = chunk_text_by_paragraph(full_text)
    
    delete_book_embeddings(book_name)
    
    collection = get_collection()
    total_chunks = len(raw_chunks)
    if total_chunks == 0:
        return True, None
        
    batch_size = 100
    for i in range(0, total_chunks, batch_size):
        batch = raw_chunks[i:i+batch_size]
        
        texts_to_embed = []
        ids = []
        metadatas = []
        documents = []
        
        for idx, (start_idx, end_idx, chunk_text) in enumerate(batch):
            chunk_num = i + idx
            clean_text = re.sub(r'\{\[\((\d+)\)\]\}', '', chunk_text).strip()
            if not clean_text:
                continue
                
            page_num = get_page_for_index(end_idx, page_map)
            chunk_id = f"{book_name}_c{chunk_num}"
            
            texts_to_embed.append(clean_text)
            ids.append(chunk_id)
            metadatas.append({
                "book_name": book_name,
                "page_number": int(page_num),
                "chunk_index": int(chunk_num),
                "tags": tags_str
            })
            documents.append(clean_text)
            
        if not texts_to_embed:
            continue
            
        try:
            effective_key = api_key or config.get_gemini_api_key()
            genai.configure(api_key=effective_key)
            response = genai.embed_content(
                model="models/gemini-embedding-2",
                content=texts_to_embed,
                task_type="retrieval_document"
            )
            embeddings = response['embedding']
            
            collection.add(
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents,
                ids=ids
            )
        except Exception as e:
            return False, f"Gemini API Error: {str(e)}"
            
        if progress_callback:
            if progress_callback(i + len(batch), total_chunks) is False:
                raise InterruptedError("Cancelled by user")
            
def make_embeddable_text(json_chunk):
    """Automatically converts any arbitrary JSON chunk into a formatted document string."""
    system_keys = ("chunk_index", "page_number", "id", "tags", "book_name")
    custom_keys = [k for k in json_chunk.keys() if k not in system_keys]
    
    if len(custom_keys) == 1 and custom_keys[0] == "text":
        return str(json_chunk.get("text", "")).strip()
        
    lines = []
    for key in custom_keys:
        value = json_chunk[key]
        display_key = key.replace("_", " ").title()
        if isinstance(value, list):
            value_str = ", ".join(map(str, value))
        else:
            value_str = str(value).strip()
            
        if value_str:
            lines.append(f"{display_key}: {value_str}")
            
    return "\n".join(lines)

def prepare_dynamic_metadata(json_chunk, book_name):
    """Prepares arbitrary JSON structures for ChromaDB metadata."""
    metadata = {
        "book_name": book_name
    }
    for key, value in json_chunk.items():
        if key in ("book_name",):
            continue
        # ChromaDB metadata does not support nested lists/dicts directly
        if isinstance(value, (list, dict)):
            metadata[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, (str, int, float, bool)):
            metadata[key] = value
        elif value is None:
            metadata[key] = ""
        else:
            metadata[key] = str(value)
    return metadata

def unpack_metadata(meta):
    """Automatically unpacks serialized JSON strings back to lists/dicts."""
    import json
    unpacked = {}
    for k, v in meta.items():
        if isinstance(v, str):
            # Try to see if it's a serialized JSON list/dict
            if (v.startswith('[') and v.endswith(']')) or (v.startswith('{') and v.endswith('}')):
                try:
                    unpacked[k] = json.loads(v)
                    continue
                except:
                    pass
        unpacked[k] = v
    return unpacked

def embed_pre_chunked_book(book_name, chunks_data, tags_str, api_key):
    """Embeds manually verified chunks and saves them to a persistent dataset."""
    import json
    # 1. Save Dataset
    dataset_dir = os.path.join(os.path.dirname(__file__), 'verified_training_data')
    os.makedirs(dataset_dir, exist_ok=True)
    dataset_path = os.path.join(dataset_dir, f"{book_name}.json")
    with open(dataset_path, 'w', encoding='utf-8') as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)

    # 2. Embed and Index in ChromaDB
    delete_book_embeddings(book_name)
    collection = get_collection()
    
    total_chunks = len(chunks_data)
    if total_chunks == 0:
        return True, None
        
    batch_size = 100
    for i in range(0, total_chunks, batch_size):
        batch = chunks_data[i:i+batch_size]
        
        texts_to_embed = []
        ids = []
        metadatas = []
        documents = []
        
        for idx, chunk_obj in enumerate(batch):
            chunk_num = i + idx
            clean_text = make_embeddable_text(chunk_obj)
            if not clean_text:
                continue
                
            page_num = chunk_obj.get("page_number", 0)
            chunk_id = f"{book_name}_c{chunk_num}"
            
            meta = prepare_dynamic_metadata(chunk_obj, book_name)
            meta["page_number"] = int(page_num)
            meta["chunk_index"] = int(chunk_num)
            meta["tags"] = tags_str
            
            texts_to_embed.append(clean_text)
            ids.append(chunk_id)
            metadatas.append(meta)
            documents.append(clean_text)
            
        if not texts_to_embed:
            continue
            
        try:
            effective_key = api_key or config.get_gemini_api_key()
            import google.generativeai as genai
            genai.configure(api_key=effective_key)
            response = genai.embed_content(
                model="models/gemini-embedding-2",
                content=texts_to_embed,
                task_type="retrieval_document"
            )
            embeddings = response['embedding']
            
            collection.add(
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents,
                ids=ids
            )
        except Exception as e:
            return False, f"Gemini API Error: {str(e)}"
            
    return True, None

def delete_book_embeddings(book_name):
    """Remove all vectors for a given book name."""
    try:
        collection = get_collection()
        collection.delete(where={"book_name": book_name})
        return True
    except Exception as e:
        print(f"Error deleting embeddings for {book_name}: {e}")
        return False

def semantic_search(query, api_key, tags_filter=None, book_filter=None, top_k=10, include_unpublished=False):
    """Perform semantic search against ChromaDB vectors."""
    # Expand query using AI to bridge the Sanskrit semantic gap
    search_query = query
    try:
        expansion = parse_query_with_ai(query, api_key)
        keywords = expansion.get('keywords', [])
        if keywords:
            search_query = f"{query} " + " ".join(keywords)
    except Exception as e:
        print(f"Query expansion warning: {e}")

    query_vector = get_gemini_embedding(search_query, api_key, is_query=True)
    if not query_vector:
        return []
        
    collection = get_collection()
    
    # Construct filters
    # If filters are requested, we determine the list of matching book names
    from sdl import CATALOG_METADATA_CACHE
    
    matching_books = set(CATALOG_METADATA_CACHE.keys())
    if not include_unpublished:
        matching_books = {b for b in matching_books if CATALOG_METADATA_CACHE[b].get('published', True)}
    
    # 1. Filter by tags if tags_filter is provided
    if tags_filter:
        tag_books = set()
        for book_name, meta in CATALOG_METADATA_CACHE.items():
            book_tags = [t.strip().lower() for t in meta.get('tags', '').split(',') if t.strip()]
            # Check if any tag matches
            if any(tf.lower() in book_tags for tf in tags_filter):
                tag_books.add(book_name)
        matching_books = matching_books.intersection(tag_books)
        
    # 2. Filter by book name if book_filter is provided
    if book_filter:
        book_filter_lower = [bf.lower() for bf in book_filter]
        title_books = set()
        for book_name in CATALOG_METADATA_CACHE.keys():
            if book_name.lower() in book_filter_lower:
                title_books.add(book_name)
        matching_books = matching_books.intersection(title_books)
        
    # If filters are applied and no books match, return empty results
    if (tags_filter or book_filter) and not matching_books:
        return []
        
    where_clause = None
    if len(matching_books) < len(CATALOG_METADATA_CACHE):
        # We need to construct the filter list
        books_list = list(matching_books)
        if len(books_list) == 1:
            where_clause = {"book_name": books_list[0]}
        else:
            # ChromaDB supports $in
            where_clause = {"book_name": {"$in": books_list}}
            
    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where_clause
        )
        
        # Format results
        formatted_results = []
        if results and results.get('documents') and results['documents'][0]:
            docs = results['documents'][0]
            metas = results['metadatas'][0]
            ids = results['ids'][0]
            distances = results['distances'][0] if results.get('distances') else [0.0] * len(docs)
            
            # Map distance to similarity score based on space
            space = collection.metadata.get('hnsw:space', 'l2') if collection.metadata else 'l2'
            
            for idx, doc in enumerate(docs):
                meta = metas[idx]
                dist = distances[idx]
                
                if space == 'cosine':
                    similarity = max(0.0, min(1.0, 1.0 - dist))
                else:  # 'l2' or 'ip'
                    similarity = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
                
                result_meta = unpack_metadata(meta)
                book_name = result_meta.get('book_name')
                chunk_index_val = result_meta.get('chunk_index')
                
                text = doc
                if not text and book_name and chunk_index_val is not None:
                    text = retrieve_chunk_text_fallback(book_name, int(chunk_index_val))
                    
                res_obj = {
                    "id": ids[idx],
                    "text": text or "",
                    "book_name": book_name,
                    "page_number": result_meta.get('page_number'),
                    "chunk_index": chunk_index_val,
                    "similarity": round(similarity, 3),
                    "metadata": result_meta
                }
                for k, v in result_meta.items():
                    if k not in res_obj:
                        res_obj[k] = v
                formatted_results.append(res_obj)
        return formatted_results
    except Exception as e:
        print(f"Error querying ChromaDB: {e}")
        return []

def retrieve_chunk_text_fallback(book_name, chunk_index):
    """Fallback to load chunk text from local text files if database doc is empty."""
    try:
        upload_folder = config.UPLOAD_FOLDER if hasattr(config, 'UPLOAD_FOLDER') else None
        if not upload_folder:
            upload_folder = os.path.join(os.path.dirname(config.CHROMA_DB_PATH), '..', 'uploads')
        folder_path = os.path.join(upload_folder, book_name)
        if not os.path.isdir(folder_path):
            return ""
            
        txt_files = [
            f for f in sorted(os.listdir(folder_path))
            if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')
        ]
        if not txt_files:
            return ""
            
        txt_path = os.path.join(folder_path, txt_files[0])
        content = get_cached_file_content(txt_path)
        
        from ai_search import chunk_text_by_paragraph
        raw_chunks = chunk_text_by_paragraph(content)
        
        if 0 <= chunk_index < len(raw_chunks):
            chunk_text = raw_chunks[chunk_index][2]
            clean = re.sub(r'\{\[\((\d+)\)\]\}', '', chunk_text).strip()
            return clean
    except Exception as e:
        print(f"Error loading fallback chunk text: {e}")
    return ""

def parse_query_with_ai(query, api_key):
    """Use Gemini to expand a natural language query into Sanskrit/English keywords and suggest tag filters.
    
    Returns a dict:
        {
            'keywords': ['word1', 'word2', ...],  # All search terms to look for
            'suggested_tags': ['tag1', 'tag2', ...]  # Catalog tags to restrict search scope
        }
    """
    try:
        # Gather all known tags from the catalog
        from sdl import CATALOG_METADATA_CACHE
        all_tags = set()
        for meta in CATALOG_METADATA_CACHE.values():
            tags_str = meta.get('tags', '')
            for t in tags_str.split(','):
                t = t.strip()
                if t:
                    all_tags.add(t)
        tags_list_str = ', '.join(sorted(all_tags)) if all_tags else 'None'

        prompt = (
            f"You are a Sanskrit library assistant. A user submitted this search query:\n"
            f"Query: {query}\n\n"
            f"Your task:\n"
            f"1. Extract 3-8 primary search keywords that would appear verbatim in Sanskrit texts. "
            f"If the query is a question asking for a definition or explanation of a term (e.g., 'X किम्' or 'X नाम किम्'), "
            f"you MUST include the expected technical Sanskrit definition, key concepts, or synonyms of X in Sanskrit. "
            f"Include Devanagari, ITRANS transliteration, and short English equivalents where useful.\n"
            f"2. From the following available library tag/category list, identify which tags are most relevant "
            f"to restrict the search scope. Only suggest tags that are clearly relevant to the query. "
            f"Return an empty list if unsure.\n"
            f"Available tags: {tags_list_str}\n\n"
            f"Respond ONLY with valid JSON in this exact format (no explanation, no markdown):\n"
            f'{{"keywords": ["word1", "word2"], "suggested_tags": ["tag1", "tag2"]}}'
        )

        effective_key = api_key or config.get_gemini_api_key()
        genai.configure(api_key=effective_key)
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw = response.text

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```[a-z]*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)

        parsed = json.loads(cleaned)
        keywords = [k.strip() for k in parsed.get('keywords', []) if k.strip()]
        suggested_tags = [t.strip() for t in parsed.get('suggested_tags', []) if t.strip()]
        # Always include the original query words as a fallback keyword
        for word in query.split():
            w = word.strip()
            if len(w) >= 3 and w not in keywords:
                keywords.append(w)
        return {'keywords': keywords, 'suggested_tags': suggested_tags}
    except Exception as e:
        print(f"parse_query_with_ai error: {e}")
        # Fallback: use raw query words as keywords, no tag suggestions
        keywords = [w.strip() for w in query.split() if len(w.strip()) >= 3]
        return {'keywords': keywords, 'suggested_tags': []}


def check_query_ambiguity(query, api_key):
    """Use Gemini 2.5 Flash to detect if a search query is highly ambiguous in Sanskrit philosophy/literature.
    Returns:
        A dict: {'status': 'ambiguous', 'message': '...', 'options': [...]}
        Or: {'status': 'clear'}
    """
    try:
        # Prompt designed to instruct Gemini on how to detect ambiguity and form options.
        prompt = (
            f"You are a helpful Sanskrit librarian and Indian philosophy expert. A user searched for:\n"
            f"Query: \"{query}\"\n\n"
            f"Sanskrit terms often have completely different, distinct meanings or contexts across different systems "
            f"(e.g., Karma meaning physical motion in Vaisheshika vs. duty/destiny in Bhagavad Gita vs. rituals in Purva Mimamsa; "
            f"or Dharma meaning righteousness vs. characteristics in Nyaya; or Maya meaning illusion in Advaita vs. physical nature in Sankhya).\n\n"
            f"Evaluate if the user's search query has multiple distinct meanings/contexts in Sanskrit literature or philosophy that would benefit from clarification.\n"
            f"If the query is already specific (e.g. mentions 'karma in gita' or 'dharma definition in nyaya') or is not ambiguous, return status 'clear'.\n\n"
            f"Respond ONLY with a valid JSON object in one of these two exact structures (no explanations, no markdown):\n\n"
            f"If ambiguous:\n"
            f'{{"status": "ambiguous", "message": "The term \'{query}\' has multiple meanings in Sanskrit philosophy. Which context do you mean?", "options": [{{"label": "Option Label (e.g., Gita - Duty)", "refined_query": "specific refined query string"}}]}}\n\n'
            f"If clear:\n"
            f'{{"status": "clear"}}'
        )

        effective_key = api_key or config.get_gemini_api_key()
        genai.configure(api_key=effective_key)
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw = response.text

        cleaned = raw.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```[a-z]*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)

        parsed = json.loads(cleaned)
        if parsed.get('status') == 'ambiguous' and parsed.get('options'):
            # Validate structure and limit options to max 4
            return {
                'status': 'ambiguous',
                'message': parsed.get('message', f"The term '{query}' has multiple meanings. Please choose a context:"),
                'options': parsed.get('options')[:4]
            }
    except Exception as e:
        print(f"check_query_ambiguity error: {e}")
        
    return {'status': 'clear'}


def keyword_search(query, api_key, tags_filter=None, book_filter=None, top_k=10, include_unpublished=False):
    """Hyper Mode: AI-expanded keyword search across the library.
    
    1. Calls parse_query_with_ai to get expanded keywords + suggested tags.
    2. Merges user-specified filters with AI suggestions.
    3. Scans matching book files for any keyword (OR logic).
    4. If no matches in filtered books, falls back to scanning all books.
    5. Returns top_k results ranked by keyword match frequency.
    """
    from sdl import CATALOG_METADATA_CACHE
    import unicodedata

    # Step 1: AI query expansion
    expansion = parse_query_with_ai(query, api_key)
    keywords = expansion.get('keywords', [])
    ai_tags = expansion.get('suggested_tags', [])

    if not keywords:
        keywords = [w.strip() for w in query.split() if len(w.strip()) >= 3]

    # Step 2: Build effective tag filter (merge user + AI suggestions)
    effective_tags = set()
    if tags_filter:
        for t in tags_filter:
            effective_tags.add(t.lower().strip())
    for t in ai_tags:
        effective_tags.add(t.lower().strip())

    # Step 3: Determine book candidates using CATALOG_METADATA_CACHE
    def book_matches_filters(book_name, meta, use_tag_filter):
        if not include_unpublished:
            if not meta.get('published', True):
                return False
        if book_filter:
            if book_name.lower() not in [bf.lower() for bf in book_filter]:
                return False
        if use_tag_filter and effective_tags:
            book_tags = set(t.strip().lower() for t in meta.get('tags', '').split(',') if t.strip())
            if not effective_tags.intersection(book_tags):
                return False
        return True

    def scan_books(candidate_books):
        """Scan a list of (book_name, meta) tuples and return ranked passages."""
        results = []
        for book_name, meta in candidate_books:
            upload_folder = config.UPLOAD_FOLDER if hasattr(config, 'UPLOAD_FOLDER') else None
            if not upload_folder:
                # Derive upload folder from CHROMA_DB_PATH
                upload_folder = os.path.join(os.path.dirname(config.CHROMA_DB_PATH), '..', 'uploads')
            folder_path = os.path.join(upload_folder, book_name)
            if not os.path.isdir(folder_path):
                continue

            txt_files = [
                f for f in sorted(os.listdir(folder_path))
                if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')
            ]

            for txt_file in txt_files:
                txt_path = os.path.join(folder_path, txt_file)
                try:
                    content = get_cached_file_content(txt_path)
                except Exception:
                    continue

                content_lower = content.lower()
                # Pre-filter: skip file entirely if no keyword found
                if not any(kw.lower() in content_lower for kw in keywords):
                    continue

                # Build page map for page number lookup
                from ai_search import get_page_map, get_page_for_index, chunk_text_by_paragraph
                page_map = get_page_map(content)
                raw_chunks = chunk_text_by_paragraph(content)

                for (start_idx, end_idx, chunk_text) in raw_chunks:
                    clean = re.sub(r'\{\[\((\d+)\)\]\}', '', chunk_text).strip()
                    if not clean:
                        continue
                    clean_lower = clean.lower()
                    # Count how many distinct keywords match (OR logic)
                    matched_kws = [kw for kw in keywords if kw.lower() in clean_lower]
                    if not matched_kws:
                        continue

                    page_num = get_page_for_index(end_idx, page_map)
                    score = len(matched_kws) / max(len(keywords), 1)  # Frequency-based score

                    results.append({
                        'id': f"{book_name}_kw_{start_idx}",
                        'text': clean,
                        'book_name': book_name,
                        'page_number': int(page_num),
                        'chunk_index': start_idx,
                        'similarity': round(min(1.0, score), 3),
                        'matched_keywords': matched_kws
                    })

        # Sort by score descending, deduplicate by (book_name, page_number)
        results.sort(key=lambda x: x['similarity'], reverse=True)
        seen = set()
        deduped = []
        for r in results:
            key = (r['book_name'], r['page_number'])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped[:top_k]

    # Resolve upload_folder
    upload_folder = getattr(config, 'UPLOAD_FOLDER', None)
    if not upload_folder:
        upload_folder = os.path.join(os.path.dirname(config.CHROMA_DB_PATH), '..', 'uploads')

    # Step 4: First scan with tag filters applied
    filtered_candidates = [
        (name, meta) for name, meta in CATALOG_METADATA_CACHE.items()
        if book_matches_filters(name, meta, use_tag_filter=True)
    ]
    matches = scan_books(filtered_candidates)

    # Step 5: Fallback — if no matches, scan all books (ignore tag filter)
    if not matches:
        all_candidates = [
            (name, meta) for name, meta in CATALOG_METADATA_CACHE.items()
            if book_matches_filters(name, meta, use_tag_filter=False)
        ]
        matches = scan_books(all_candidates)

    return matches, keywords


def summarize_results(query, results, api_key):
    """Generate conversational RAG response from Gemini based on retrieved results."""
    if not results:
        # Direct AI fallback: answer using general knowledge when no library passages are available
        try:
            fallback_prompt = (
                f"You are a knowledgeable Sanskrit library assistant specializing in Sanskrit, "
                f"Hindu philosophy, Vedanta, Yoga, and related traditions. "
                f"A user asked the following question but no matching passages were found in the library.\n\n"
                f"Please answer the question comprehensively using your general knowledge of Sanskrit traditions. "
                f"Be accurate, well-structured, and cite relevant texts or authors where applicable.\n\n"
                f"User's question: {query}\n\nAnswer:"
            )
            effective_key = api_key or config.get_gemini_api_key()
            genai.configure(api_key=effective_key)
            model = genai.GenerativeModel("models/gemini-2.5-flash")
            response = model.generate_content(fallback_prompt)
            return response.text
        except Exception as e:
            return f"Unable to generate an answer at this time. Please try again. ({str(e)})"
        
    context_parts = []
    for idx, r in enumerate(results):
        context_parts.append(
            f"Source Book: {r['book_name']}\n"
            f"Page: {r['page_number']}\n"
            f"Content: {r['text']}\n"
            f"---"
        )
    context_text = "\n".join(context_parts)
    
    prompt = (
        f"You are a helpful assistant for the Sanskrit Digital Library. "
        f"You are given the following search query and a set of relevant source passages retrieved from Sanskrit/Hindi books. "
        f"Based on the source passages, answer the search query. "
        f"Be comprehensive, accurate, and structured. Highlight which book and page you got the information from if relevant. "
        f"If the sources do not contain information to answer the query, say that you couldn't find the answer in the provided passages, but still summarize what the passages contain. "
        f"Do not make up facts or use external knowledge not contained in the sources.\n\n"
        f"Query: {query}\n\n"
        f"Source Passages:\n{context_text}\n\n"
        f"Answer:"
    )
    
    try:
        effective_key = api_key or config.get_gemini_api_key()
        genai.configure(api_key=effective_key)
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating summary: {str(e)}"

def prune_orphaned_chromadb_folders():
    """Removes orphaned HNSW index folders from disk that are no longer referenced in SQLite."""
    try:
        import shutil
        sqlite_path = os.path.join(config.CHROMA_DB_PATH, 'chroma.sqlite3')
        if not os.path.exists(sqlite_path):
            return
            
        import sqlite3
        conn = sqlite3.connect(sqlite_path)
        cur = conn.cursor()
        cur.execute("SELECT id FROM segments")
        active_segments = {r[0] for r in cur.fetchall()}
        conn.close()
        
        # Check all items in CHROMA_DB_PATH
        for name in os.listdir(config.CHROMA_DB_PATH):
            dir_path = os.path.join(config.CHROMA_DB_PATH, name)
            if os.path.isdir(dir_path) and len(name) == 36: # UUID length is 36
                if name not in active_segments:
                    shutil.rmtree(dir_path)
                    print(f"Cleaned up orphaned ChromaDB index folder: {name}")
    except Exception as e:
        print(f"Error pruning orphaned folders: {e}")

def vacuum_chromadb_sqlite():
    """Forces SQLite to merge WAL logs and reclaim disk space."""
    try:
        import sqlite3
        sqlite_path = os.path.join(config.CHROMA_DB_PATH, 'chroma.sqlite3')
        if os.path.exists(sqlite_path):
            conn = sqlite3.connect(sqlite_path, isolation_level=None)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
            conn.close()
        
        # Prune folders
        prune_orphaned_chromadb_folders()
    except Exception as e:
        print(f"ChromaDB vacuum warning: {e}")

def get_db_stats():
    """Calculate and return ChromaDB size and statistics."""
    vacuum_chromadb_sqlite()
    try:
        collection = get_collection()
        total_chunks = collection.count()
    except Exception:
        total_chunks = 0
        
    storage_size_bytes = 0
    if total_chunks > 0 and os.path.exists(config.CHROMA_DB_PATH):
        for root, dirs, files in os.walk(config.CHROMA_DB_PATH):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    storage_size_bytes += os.path.getsize(fp)
                except OSError:
                    pass
                    
    storage_size_bits = storage_size_bytes * 8
    if storage_size_bits < 1024:
        size_str = f"{storage_size_bits} bits"
    elif storage_size_bits < 1024 * 1024:
        size_str = f"{storage_size_bits / 1024:.2f} Kb"
    else:
        size_str = f"{storage_size_bits / (1024 * 1024):.2f} Mb"
        
    last_updated_ts = 0
    if total_chunks > 0 and os.path.exists(config.CHROMA_DB_PATH):
        for root, dirs, files in os.walk(config.CHROMA_DB_PATH):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(fp)
                    if mtime > last_updated_ts:
                        last_updated_ts = mtime
                except OSError:
                    pass
                    
    last_updated_str = "Never"
    if last_updated_ts > 0:
        last_updated_str = time.strftime('%Y-%m-%d', time.localtime(last_updated_ts))
        
    return {
        "total_chunks": total_chunks,
        "storage_size": size_str,
        "last_updated": last_updated_str
    }

def get_book_embedding_status(book_names):
    """Determine embedding status for a list of book folders."""
    status = {name: False for name in book_names}
    if not book_names:
        return status
        
    try:
        collection = get_collection()
        for i in range(0, len(book_names), 200):
            batch = book_names[i:i+200]
            res = collection.get(where={"book_name": {"$in": batch}}, include=["metadatas"])
            if res and res.get('metadatas'):
                for meta in res['metadatas']:
                    b_name = meta.get('book_name')
                    if b_name in status:
                        status[b_name] = True
    except Exception as e:
        print(f"Error querying book embedding status: {e}")
        
    return status

def get_embedded_book_names():
    """Get a sorted list of unique book names that have embeddings in ChromaDB."""
    try:
        collection = get_collection()
        total = collection.count()
        if total == 0:
            return []
        # Fetch all metadatas to extract unique book names
        res = collection.get(include=["metadatas"], limit=total)
        if res and res.get('metadatas'):
            names = set()
            for meta in res['metadatas']:
                b_name = meta.get('book_name')
                if b_name:
                    names.add(b_name)
            return sorted(names)
    except Exception as e:
        print(f"Error fetching embedded book names: {e}")
    return []

def get_book_chunks(book_name):
    """Retrieve all chunks for a specific book from ChromaDB, ordered by chunk_index."""
    try:
        collection = get_collection()
        res = collection.get(
            where={"book_name": book_name},
            include=["documents", "metadatas"]
        )
        if res and res.get('documents'):
            chunks = []
            for idx, doc in enumerate(res['documents']):
                meta = res['metadatas'][idx] if res.get('metadatas') else {}
                unpacked = unpack_metadata(meta)
                
                if 'chunk_index' not in unpacked:
                    unpacked['chunk_index'] = idx
                if 'page_number' not in unpacked:
                    unpacked['page_number'] = 0
                if 'text' not in unpacked:
                    unpacked['text'] = doc
                    
                unpacked['id'] = res['ids'][idx] if res.get('ids') else f"{book_name}_c{idx}"
                chunks.append(unpacked)
            # Sort by chunk_index
            chunks.sort(key=lambda c: c['chunk_index'])
            return chunks
    except Exception as e:
        print(f"Error fetching chunks for {book_name}: {e}")
    return []

def load_api_key():
    """Load Gemini API Key from environment or common_db."""
    return config.get_gemini_api_key()

def test_api_key(api_key):
    """Test API key validity by generating a small embedding."""
    try:
        genai.configure(api_key=api_key)
        genai.embed_content(
            model="models/gemini-embedding-2",
            content="test connection",
            task_type="retrieval_query"
        )
        return True, None
    except Exception as e:
        return False, str(e)
