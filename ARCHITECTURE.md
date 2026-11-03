# Open-Samsho (संशोधन मन्दिरम्) — Software Architecture & System Design

> Comprehensive technical architecture, data structures, routing pipelines, and component design for the Open-Samsho computational linguistics, digital library, and AI platform.

---

## Table of Contents

1. [High-Level System Architecture](#1-high-level-system-architecture)
2. [Technology Stack](#2-technology-stack)
3. [Database Architecture & Schemas](#3-database-architecture--schemas)
4. [File & Storage Layout](#4-file--storage-layout)
5. [Server Setup & Deployment](#5-server-setup--deployment)
6. [WSGI Routing & URL Rewriting](#6-wsgi-routing--url-rewriting)
7. [Modules & Component Architecture](#7-modules--component-architecture)
   - 7.1 [Core Infrastructure & WSGI Chain](#71-core-infrastructure--wsgi-chain)
   - 7.2 [Sanskrit Digital Library (SDL)](#72-sanskrit-digital-library-sdl)
   - 7.3 [AI & Gemini Integration Engine](#73-ai--gemini-integration-engine)
   - 7.4 [Semantic Vector Search (ChromaDB)](#74-semantic-vector-search-chromadb)
   - 7.5 [Book Ingestion & Digitization Pipeline](#75-book-ingestion--digitization-pipeline)
   - 7.6 [OCR Processing Subsystem](#76-ocr-processing-subsystem)
   - 7.7 [Quiz System](#77-quiz-system)
   - 7.8 [Katha (Stories) Module](#78-katha-stories-module)
   - 7.9 [Articles & Research Module](#79-articles--research-module)
   - 7.10 [Interactive Sanskrit Games (Play)](#710-interactive-sanskrit-games-play)
   - 7.11 [Sanskrit Computational Linguistics & Apps Suite](#711-sanskrit-computational-linguistics--apps-suite)
   - 7.12 [Admin Hub & Operational Governance](#712-admin-hub--operational-governance)
   - 7.13 [Authentication & User Management](#713-authentication--user-management)
   - 7.14 [Developer API (v1)](#714-developer-api-v1)
8. [Third-Party Services & Integrations](#8-third-party-services--integrations)
9. [Security Features & Access Control](#9-security-features--access-control)
10. [End-to-End Execution Flows](#10-end-to-end-execution-flows)
11. [Appendix: File Sizes & Hardware Requirements](#11-appendix-file-sizes--hardware-requirements)

---

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INTERNET / CLIENT BROWSERS                         │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ HTTPS (Port 443)
                              ┌─────▼─────┐
                              │   Nginx    │  Reverse Proxy + SSL (Certbot)
                              │ (Port 80/  │  Max upload: 4 GB
                              │  443)      │  Timeout: 600s
                              └─────┬──────┘
                                    │ HTTP (Port 8000, localhost)
                         ┌──────────▼──────────┐
                         │ Gunicorn WSGI Server │  4 Workers × 4 Threads
                         │ (server:application) │  Timeout: 600s
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
     ┌────────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
     │   static_app    │  │   admin_app     │  │    sdl_app      │
     │  Flask (/)      │  │  Flask (/admin) │  │  Flask (/sdl)   │
     │                 │  │                 │  │                 │
     │ • Landing Page  │  │ • Admin Hub     │  │ • Library       │
     │ • Quiz UI       │  │ • User Mgmt    │  │ • Search        │
     │ • Katha UI      │  │ • Admin Mgmt   │  │ • Reader        │
     │ • Articles UI   │  │ • Broadcasts    │  │ • Book Upload   │
     │ • Play (Games)  │  │ • Audit Logs   │  │ • OCR           │
     │ • NLP Apps      │  │ • System Cfg   │  │ • Admin Panel   │
     └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
   ┌──────▼──────┐          ┌──────▼──────┐          ┌──────▼──────┐
   │  SQLite DBs │          │  ChromaDB   │          │ File System │
   │  (db/*.db)  │          │ (Vector DB) │          │ (uploads/)  │
   └─────────────┘          └─────────────┘          └─────────────┘
```

The system hosts three coordinated Flask sub-applications inside a unified WSGI application pipeline. A custom path rewriting middleware transparently routes incoming requests (`/admin`, `/api`, `/book`, `/search`) so external consumers interact with a clean URL hierarchy.

---

## 2. Technology Stack

### Backend
| Component | Technology | Role |
|---|---|---|
| **Language** | Python 3.10+ | Core runtime language |
| **Framework** | Flask | Modular sub-apps with Jinja2 templating |
| **WSGI Server** | Gunicorn | 4 workers × 4 threads, 600s timeout |
| **Reverse Proxy** | Nginx | SSL termination, reverse proxy, 4 GB upload threshold |
| **Process Supervision** | systemd | Auto-restart and service lifecycle management |

### Databases & Storage
| Database | Technology | Size (Runtime) | Purpose |
|---|---|---|---|
| `common.db` | SQLite (WAL mode) | ~160 KB | User profiles, role-based admin access, tokens, bookmarks |
| `quiz.db` | SQLite (WAL mode) | ~37 KB | Multilingual quiz questions, score tracking, user feedback |
| `katha.db` | SQLite (WAL mode) | ~37 KB | Stories, media collections, reader feedback |
| `articles.db` | SQLite (WAL mode) | ~37 KB | Scholarly articles and deduplicated feedback |
| `play.db` | SQLite (WAL mode) | ~37 KB | Synonym matching, word building, and word search games |
| `vyakarana_kosha.db` | SQLite | **~968 MB** | Compiled Vyākaraṇa & Kosha corpus (compiled from `data-master.zip` via `db/compile_vyakarana_kosha.py`) |
| `chroma_db/` | ChromaDB (Persistent) | Variable | Dense vector embeddings for semantic document search |

> *Note: Database files (`db/*.db`) are created dynamically at runtime or initialized via `python scripts/init_dev_db.py`. They are gitignored and not stored in repository version control.*

### Computational Linguistics & Sanskrit NLP
| Library | Capability | Packaging / Source |
|---|---|---|
| `vidyut.kosha` | High-performance 100M+ entry Paninian morphological lexicon | `vidyut` in `requirements.txt` |
| `vidyut.cheda` | Sentence segmentation and Sandhi viccheda | `vidyut` in `requirements.txt` |
| `vidyut.prakriya` | Step-by-step Ashtadhyayi rule derivation engine | `vidyut` in `requirements.txt` |
| `vidyut.lipi` | Bidirectional script transliteration (Devanagari, SLP1, IAST, etc.) | `vidyut` in `requirements.txt` |
| `chanda` | Sanskrit poetic meter (chandas) and prosody analysis | `chanda` in `requirements.txt` |
| `sandhi` | Phonetic combination and splitting algorithms | `sandhi` in `requirements.txt` |
| `sanskrit_parser` | Dependency parsing and semantic role (Karaka) mapping | Optional (`deploy.sh --no-deps`, dynamic fallback in `sanskrit_processor.py`) |
| `indic-transliteration` | Transliteration utilities across regional Indic scripts | `indic-transliteration` in `requirements.txt` |

---

## 3. Database Architecture & Schemas

All databases run SQLite in **Write-Ahead Logging (WAL)** mode for concurrent non-blocking reads and writes. Schema updates are automatically applied via dynamic schema migration utilities.

### `common.db` Tables
- `users`: User registration, hashed credentials, avatar preferences, optional personal AI keys.
- `favourites`: User book bookmarks.
- `booklists` & `booklist_items`: Custom collections and ordered reading lists.
- `user_tokens`: Token authentication records for API sessions.
- `user_otps`: One-time passwords for password recovery workflows.
- `admins`: Administrative accounts with granular permission sets.
- `sambhashana_modes`: AI chat companion personas and system instructions.
- `system_settings`: Platform-wide configurations and operational toggles.
- `user_ai_overrides`: Per-user access tiering for AI features.
- `user_ai_usage`: Telemetry on AI feature usage and errors.
- `vector_download_requests`: Bulk download queue for pre-calculated vector indexes.

### `quiz.db` Tables
- `quiz_questions`: Multilingual questions, options, and explanations.
- `quiz_results`: History of user and guest scores and completion durations.
- `quiz_feedback`: Question-specific user feedback.

### `katha.db` Tables
- `kathas`: Sanskrit stories with formatted HTML, categories, covers, and reading estimates.
- `katha_feedback`: Story ratings and reader feedback.

### `articles.db` Tables
- `articles`: Articles with formatted bodies, categories, authors, and publish state.
- `article_feedback`: Reader votes deduplicated via IP hashing.

### `play.db` Tables
- `synonym_sets` & `synonym_pairs`: Word matching games with time constraints.
- `word_builder_sets`: Syllable reassembly challenges.
- `word_search_sets`: Letter grid word-finding configurations.
- `play_results`: Game completion statistics.

---

## 4. File & Storage Layout

```
sdl_web/
├── uploads/                      — Uploaded book directories
│   └── {BookName}/
│       ├── {BookName}.txt        — Text with page markers (========== PAGE X ==========)
│       ├── metadata.txt          — Title, source URL, tags, publication info
│       ├── thumbnail.jpg         — Cached book cover image
│       └── feedback.json         — Upvotes and ratings
├── chroma_db/                    — ChromaDB persistent storage directory
├── pipeline_zips/                — Downloadable ZIP packages from bulk processing
├── ocr/                          — Active and completed OCR task workspaces
├── templates/
│   ├── admin/                    — Administrative dashboards
│   └── public/                   — Public-facing digital library templates
├── api_keys.json                 — Hashed API access keys
└── sdl_browse_cache.json         — Cached item indices from archive.org

static/
├── css/                          — Modular styling sheets
├── js/                           — Frontend interactive logic & transliteration
└── webfonts/                     — Font Awesome asset package

vidyut-data/                      — Optional local linguistics models (auto-routes to Cloud NLP API when absent)
├── chandas/                      — Prosody definitions
├── cheda/                        — Word-splitting models
├── kosha/                        — Lexicon tables
└── prakriya/                     — Grammatical rule models
```

---

## 5. Server Setup & Deployment

### Production Deployment
- **Recommended OS**: Linux (Ubuntu 22.04 / 24.04 LTS or Debian 12)
- **Deployment Scripts**:
  - [`setup.sh`](setup.sh): Installs system dependencies, configures Python virtual environment, registers systemd unit file, generates Nginx reverse proxy configuration, and configures Let's Encrypt SSL.
  - [`deploy.sh`](deploy.sh): Pulls dependencies, ensures `vyakarana_kosha.db` is compiled, and restarts Gunicorn.
- **Service Configuration**:
  - Gunicorn bound to `127.0.0.1:8000` with 4 workers and 4 threads per worker.
  - Nginx terminates HTTPS and forwards traffic with `client_max_body_size 4G` and `proxy_read_timeout 600s`.

---

## 6. WSGI Routing & URL Rewriting

Incoming HTTP requests traverse a three-tiered WSGI middleware pipeline:

```
ProxyFix ──> AdminPathRewriteMiddleware ──> DispatcherMiddleware
                                               ├── /      → static_app
                                               ├── /admin → admin_app
                                               └── /sdl   → sdl_app
```

### URL Rewriting Mapping
- `/` $\rightarrow$ `static_app` (Landing page)
- `/quiz/*`, `/katha/*`, `/articles/*`, `/play/*` $\rightarrow$ `static_app`
- `/apps/*` $\rightarrow$ `static_app` (NLP Blueprint at `/apps/api`)
- `/admin/hub`, `/admin/users` $\rightarrow$ `admin_app`
- `/admin/*` (general SDL admin) $\rightarrow$ rewritten to `/sdl/admin/*`
- `/api/*` $\rightarrow$ rewritten to `/sdl/api/*`
- `/book/*`, `/reader/*`, `/search/*`, `/library` $\rightarrow$ rewritten to `/sdl/*`

---

## 7. Modules & Component Architecture

### 7.1 Core Infrastructure & WSGI Chain
- Unified application entry point in `server.py`.
- Path rewriting preserves clean client-side URLs while isolating operational logic across specialized Flask instances.

### 7.2 Sanskrit Digital Library (SDL)
- **Primary Engine**: `sdl_web/sdl.py`
- Handles book uploads (ZIP/text), page-level indexing, Zstandard compression, and full-text search.
- Integrates linguistic normalization (`sdl_web/sanskrit_utils.py`) to match search terms regardless of Visarga transformations, Avagraha elision, or Sandhi compounding.
- Supports Server-Sent Events (SSE) streaming for real-time search result delivery.

### 7.3 AI & Gemini Integration Engine
- **Centralized Key Resolution**: Managed via `sdl_web/config.py` using a single platform key (`GEMINI_API_KEY` / `GOOGLE_API_KEY` in environment/.env) with fallback to the Superadmin key stored in `common.db`.
- **Role-Based Access Control (RBAC) & Quotas**: Global AI access rules tiered across user roles (Guest, Logged-in Member, Admin) configured in `system_settings`.
- **Per-User Overrides**: Granular overrides (`user_ai_overrides` table) enabling custom permissions and context memory limits per user.
- **Telemetry & Quota Monitoring**: Real-time logging of user invocation volume, feature usage, and error metrics (`user_ai_usage` table).

### 7.4 Semantic Vector Search (ChromaDB)
- **Vector Search Engine**: `sdl_web/ai_search.py`
- **Text Chunking Pipeline**: `sdl_web/admin_chunking.py`
- Converts paragraph-bounded text segments into dense vector representations via Gemini Embedding models.
- Stores vectors in ChromaDB with book, page, and chunk metadata for sub-second semantic retrieval.

### 7.5 Book Ingestion & Digitization Pipeline
- **Pipeline Orchestrator**: `sdl_web/admin_pipeline.py`
- Automates ingestion: archive.org fetching $\rightarrow$ PDF to image extraction via PyMuPDF $\rightarrow$ parallel OCR execution $\rightarrow$ page marker generation $\rightarrow$ archive packaging.

### 7.6 OCR Processing Subsystem
- **Engine**: `sdl_web/ocr.py`
- Leverages Google Drive API and document conversion pipelines with background queue processing and fallback OCR models.
- Supports PDF, image arrays, and ZIP containers, compiling extracted text into formatted text, DOCX, and PDF formats.

### 7.7 Quiz System
- Interactive assessment engine supporting multiple categories, subjects, and skill tiers.
- Features timer controls, answer review, score feedback, and IndexedDB caching for offline play.

### 7.8 Katha (Stories) Module
- Publishing platform for Sanskrit stories with rich media and category-based navigation.

### 7.9 Articles & Research Module
- Publishing platform for Sanskrit scholarly research, incorporating feedback deduplication via IP hashing.

### 7.10 Interactive Sanskrit Games (Play)
- Educational modules including **Synonym Matching (पर्यायमेलनम्)**, **Word Building (शब्दरचना)**, and **Word Search Grids (शब्दान्वेषणम्)**.

### 7.11 Sanskrit Computational Linguistics & Apps Suite
- **Ashtadhyayi Companion (`apps/ashtadhyayi_companion`)**: Reference suite for Panini’s 3,996 sutras, Shiva Sutras, Ganapatha, Dhatupatha, and classical texts (including Tarkasangraha).
- **Chandas (`apps/chandas`)**: Prosody identifier classifying Laghu/Guru metrics against classical meter definitions.
- **Dhatu & Shabda Explorers (`apps/dhatu_explorer`, `apps/shabda_explorer`)**: Full declension and conjugation derivation engines powered by `vyakarana_kosha.db` or cloud NLP API.
- **Sandhi Studio (`apps/sandhi_studio`)**: Interactive compound splitting and joining with rule explanations.
- **Rigveda Samhita (`apps/rigveda`)**: Complete Vedic text browser with Padapatha, Sayana Bhashya, and audio chanting (`rigveda.db.gz`).
- **Sanskrit STT (`apps/sanskrit_stt`)**: Sanskrit Speech-to-Text client integration and Telegram bot interfacing with the centralized Samshodhanam STT API.
- **OCR & Transliterator Bots (`apps/ocr_bot`, `apps/transliterator`)**: Automated bot workflows for manuscript OCR and multi-script transliteration.
- **Unified NLP Processor & Blueprint (`sanskrit_processor.py`, `apps/backend.py`)**: Centralized processing combining Chanda, Vidyut, Sandhi, and Karaka dependency mapping mounted at `/apps/api`.

### 7.12 Admin Hub & Operational Governance
- Centralized administrative console monitoring users, books, games, support threads, and system configurations.
- Secure, thread-safe audit logging recording state diffs across administrative actions.

### 7.13 Authentication & User Management
- Authentication using bcrypt password hashing, session cookies, and bearer tokens.
- Granular administrative permissions and role-based access.

### 7.14 Developer API (v1)
- Token-authenticated REST API (`sdl_web/api_v1.py`) supporting catalog queries, page retrieval, suggestions, and cross-instance data synchronization.


---

## 8. Third-Party Services & Integrations

| Service | Purpose | Integration Method |
|---|---|---|
| **Gemini Embedding API** | Dense vector semantic search representations | Platform API Key (`GEMINI_API_KEY` / Admin fallback) |
| **Google Drive / Vision** | High-accuracy Indic script OCR | OAuth2 credentials |
| **Archive.org API** | Public domain manuscript and book retrieval | Public HTTP REST endpoints |
| **SMTP Service** | Transactional emails (OTP, job alerts) | Standard TLS SMTP credentials |

---

## 9. Security Features & Access Control

- **Password Storage**: Passwords hashed with bcrypt.
- **Credential Storage**: Third-party API credentials stored with Fernet symmetric encryption.
- **Path Traversal Mitigation**: File access restricted via normalized path verification.
- **Origin Hardening**: Dynamic Cross-Origin Resource Sharing (CORS) validating approved host origins.


---

## 10. End-to-End Execution Flows

### Manuscript Digitization
```
Archive.org Source ──> Download PDF ──> PyMuPDF Image Split ──>
Google Drive OCR ──> Page-Marked Text File ──> Library Upload ──>
Paragraph Chunking ──> Gemini Embeddings ──> ChromaDB Storage
```

### AI Explanation Request
```
Client Reader View ──> User "Ask AI" ──> Context Assembly ──>
Gemini Key Resolution ──> Model Inference ──> Response Delivery
```

### Sanskrit Sentence Analysis Pipeline (`sanskrit_processor.py`)
```
Input Sanskrit Text ──> Transliterate to SLP1 ──> vidyut.cheda Segmentation ──>
vidyut.kosha Lexicon Lookup ──> Verb / Krdanta Detection ──>
sanskrit_parser Karaka Mapping ──> vidyut.prakriya Rule Derivation ──>
Render Dependency Graph
```

---

## 11. Appendix: File Sizes & Hardware Requirements

### Code & Asset Footprint
| Component | Footprint | Notes |
|---|---|---|
| `vyakarana_kosha.db` | ~968 MB | Compiled linguistic database (generated externally via `compile_vyakarana_kosha.py`) |
| `data-master.zip` | ~461 MB | Raw source linguistic archive (optional upload for compilation) |
| `sdl_web/sdl.py` | ~396 KB | Digital library routing engine |
| `apps/backend.py` | ~171 KB | NLP apps backend blueprint |
| `sdl_web/api_v1.py` | ~114 KB | Developer REST API endpoints |
| Total Core Codebase | ~3.5 MB+ | Python, HTML, CSS, JavaScript |

### Recommended System Specifications
- **Operating System**: Linux (Ubuntu 22.04+ or Debian 12+)
- **CPU**: 4+ cores (recommended for multi-threaded Gunicorn and NLP operations)
- **Memory**: Minimum 4 GB RAM (8 GB+ recommended if running all in-memory NLP engines with multiple workers)
- **Storage**: Minimum 10 GB SSD space (scales based on book volume and vector storage)
