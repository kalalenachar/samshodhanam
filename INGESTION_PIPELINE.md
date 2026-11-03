# Sanskrit Digital Library — Book Ingestion & Processing Pipeline

> Technical specification for bulk downloading, digitizing, OCR processing, proofreading, chunking, and vector embedding of Sanskrit texts.

---

## 1. Overview & Pipeline Lifecycle

The ingestion pipeline converts raw digital manuscripts and PDF books into high-quality, searchable, and AI-queryable digital assets through a 7-step automated process:

```
[ Step 1: Download ]   ──> Fetch book PDF from Archive.org or digital repositories
[ Step 2: Convert ]    ──> Render and split PDF pages into high-resolution images
[ Step 3: Scan (OCR) ] ──> Extract Devanagari / Indic text via Cloud Vision OCR
[ Step 4: Proofread ]  ──> Normalize orthography & correct OCR errors via LLM / Human QA
[ Step 5: Chunk ]      ──> Split text into semantically coherent paragraph blocks
[ Step 6: Embed ]      ──> Generate dense vector embeddings via Gemini Embedding models
[ Step 7: Index ]      ──> Persist vectors into ChromaDB for sub-second semantic search
```

---

## 2. Detailed Pipeline Stages

### Stage 1: Download & Metadata Extraction
- Fetches publication metadata (source identifier, title, tags, date) from Archive.org.
- Downloads PDF assets using atomic downloads (`.part` temporary file with checksum validation).
- Implements auto-resume to gracefully handle network interruptions.

### Stage 2: Page Image Rendering
- Uses **PyMuPDF (`fitz`)** to render vector/raster PDF pages into optimized PNG/JPEG images.
- Generates a `_pages.txt` marker log tracking extracted page counts and resolution metrics.

### Stage 3: OCR Processing
- Leverages authenticated Google Drive / OCR workers with automatic error handling and exponential backoff retry.
- Compiles extracted text with standardized page markers:
  ```text
  ========== PAGE 1 ==========
  [Extracted Sanskrit text]
  ========== PAGE 2 ==========
  [Extracted Sanskrit text]
  ```
- Unprocessed or unreadable pages are logged to a retry queue (`_skipped.txt`).

### Stage 4: Linguistic Proofreading & Normalization
- Resolves common Sanskrit OCR inaccuracies (e.g., misrecognized conjunct consonants, broken anusvara, missing avagraha).
- Applies Sanskrit linguistic normalization (`sdl_web/sanskrit_utils.py`):
  - Visarga and pausal variant normalization.
  - Avagraha elision handling.
  - Compound word (Sandhi) boundary recognition.

### Stage 5: Semantic Chunking (`sdl_web/admin_chunking.py`)
- Segments continuous page text into cohesive paragraph-level units (typically 200–500 tokens per chunk).
- Preserves document hierarchy: each chunk retains references to the book identifier, page number, and paragraph index.

### Stage 6: Vector Embedding (`sdl_web/ai_search.py`)
- Passes text chunks to the embedding model (`models/gemini-embedding-2`).
- Embeddings are generated with task type `retrieval_document` to optimize subsequent retrieval quality.

### Stage 7: Vector Storage & Indexing (`sdl_web/ai_search.py`)
- Stores embedding vectors and associated text payloads in a persistent local **ChromaDB** collection (`sdl_book_chunks`).
- Enables cosine similarity searches for natural-language conceptual queries.

---

## 3. Processing Strategies

Depending on throughput requirements and computational availability, the pipeline supports three operational modes:

| Mode | Proofreading Strategy | Accuracy | Throughput | Use Case |
|---|---|---|---|---|
| **Standard Full Pipeline** | 100% LLM proofreading with human spot-checks | Highest | Standard | High-value classical literature, rare commentaries, Shastras |
| **Selective Proofreading** | Target low-confidence OCR pages (e.g., ~30%) | High | Fast | Large library collections with varying scan quality |
| **Direct Indexing (Minimalist)** | Skips LLM proofreading; proceeds directly to chunking & embedding | Good | Maximum | Rapid batch ingestion of clean, modern printed texts |

---

## 4. Hardware & System Recommendations

For continuous bulk ingestion and local embedding operations:

- **Compute**: 4–8 CPU cores for concurrent PDF rasterization and OCR payload dispatching.
- **Memory**: Minimum 8 GB RAM (16 GB+ recommended for large multi-page image buffers).
- **Temporary Storage**: 10–20 GB temporary disk buffer (raw page images are cleaned up immediately following OCR extraction).
- **Persistent Storage**: Sufficient SSD space for ChromaDB vector indexes and compressed book text files.
