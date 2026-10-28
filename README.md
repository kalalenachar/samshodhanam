# संशोधनम् (Samshodhanam)

> **Sanskrit Computational Linguistics, AI-Powered Digital Library, and Manuscript Preservation Suite**

[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Live Deployment](https://img.shields.io/badge/Live%20Platform-samshodhanamandiram.in-success.svg)](https://samshodhanamandiram.in)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

🌐 **Live Deployed Version:** [https://samshodhanamandiram.in](https://samshodhanamandiram.in)

---

## 📖 Introduction: What is Samshodhanam?

**संशोधनम् (Samshodhanam)** (*Sanskrit for "Critical inquiry, research, and refinement"*) is an all-in-one open-source ecosystem that brings classical Sanskrit literature into the digital age. It combines **centuries-old linguistic science** (Panini's computational grammar) with **modern artificial intelligence** (neural OCR, semantic search, and speech recognition).

Whether you are a **scholar, student, language enthusiast, or software developer**, Samshodhanam provides accessible, web-based tools to explore texts, analyze poetry, digitize ancient manuscripts, and practice Sanskrit.

```
                              ┌───────────────────────────────────────────────┐
                              │            संशोधनम् (Samshodhanam)            │
                              │           https://samshodhanamandiram.in      │
                              └──────────────────────┬────────────────────────┘
                                                     │
         ┌──────────────────────────┬────────────────┴──────────┬─────────────────────────┐
         ▼                          ▼                           ▼                         ▼
┌──────────────────┐      ┌──────────────────┐        ┌──────────────────┐      ┌──────────────────┐
│  Computational   │      │  Sanskrit Digital│        │  AI, OCR &       │      │  Interactive     │
│  Linguistics     │      │  Library (SDL)   │        │  Speech Labs     │      │  Learning & Apps │
├──────────────────┤      ├──────────────────┤        ├──────────────────┤      ├──────────────────┤
│• Ashtadhyayi 4K  │      │• Script-aware    │        │• Neural Sanskrit │      │• QuizMaster with │
│  Sutra Companion │      │  full-text search│        │  Speech-to-Text  │      │  certificates    │
│• Chandas Prosody │      │• AI Concept &    │        │• Automated       │      │• Word games and  │
│  Meter Analyzer  │      │  Semantic Search │        │  Grantha OCR     │      │  crosswords      │
│• Dhatu & Shabda  │      │• Crowdsourced    │        │• Telegram Bots   │      │• Peer-reviewed   │
│  Conjugations    │      │  Proofreading    │        │  (OCR + Scripts) │      │  Article Reader  │
│• Sandhi Studio   │      │• Manuscript      │        │• WebSocket Real- │      │• Classical Text  │
│• Rigveda Samhita │      │  Image Archive   │        │  Time Streaming  │      │  Audio Player    │
└──────────────────┘      └──────────────────┘        └──────────────────┘      └──────────────────┘
```

---

## 🏛️ The Four Pillars of Samshodhanam

### 1. 📐 Sanskrit Computational Grammar & Linguistics
Panini's *Ashtadhyayi* (~500 BCE) is widely regarded as the world's first formal, generative linguistic rule system. Samshodhanam turns these rules into interactive web utilities:

| Tool | What It Does (In Plain Language) | Why It Matters |
| :--- | :--- | :--- |
| **Ashtadhyayi Companion** (`apps/ashtadhyayi_companion`) | Explore all 3,996 sutras of Panini, Shiva Sutras, Dhatupatha (verb roots), Ganapatha, and Tarkasangraha. | Deeply understand how Sanskrit grammatical rules derive words. |
| **Chandas Prosody Analyzer** (`apps/chandas`) | Paste any Sanskrit shloka (verse) and it automatically scans syllables as light (*Laghu*) or heavy (*Guru*) to identify poetic meters (Anushtubh, Indravajra, Mandakranta, etc.). | Instantly decode the poetic rhythm of classical poetry. |
| **Dhatu & Shabda Explorers** (`apps/dhatu_explorer`, `apps/shabda_explorer`) | Full verb conjugations across all 10 *Lakaras* (tenses/moods) and noun declensions across all 7 cases (*Vibhaktis*) in singular, dual, and plural. | Eliminates manual table lookup for Sanskrit learners. |
| **Sandhi Studio** (`apps/sandhi_studio`) | Combines words or splits complex compound words (*Samasa* & *Sandhi*) with step-by-step grammatical justification. | Helps beginners and researchers break down dense classical sentences. |
| **Rigveda Samhita** (`apps/rigveda`) | Browse the oldest Vedic text by Mandala, Sukta, and Rik, complete with word-by-word Padapatha, Sayana's commentary (*Bhashya*), and audio recitations. | Preserves sacred recitation traditions alongside scholarly commentary. |

---

### 2. 📚 Sanskrit Digital Library (SDL)
A modern, open-access preservation system designed to save rare manuscripts and printed heritage books from degradation:

- **Multi-Script & Accent-Aware Search:** Search manuscripts seamlessly whether you type in Devanagari, English phonetic transliteration (IAST), or regional scripts.
- **AI-Powered Semantic Vector Search:** Search by *meaning* or *concept* rather than just exact keywords. Powered by vector embeddings (ChromaDB) and Google Gemini AI, allowing researchers to ask conceptual questions like *"Find references to solar eclipses in astronomical treaties"*.
- **Crowdsourced Manuscript Proofreading:** A collaborative split-screen interface where volunteers review digitized pages against original scan images, correct OCR errors, and build verified machine-readable texts.

---

### 3. 🤖 AI, OCR & Speech Processing
Samshodhanam includes state-of-the-art tools designed specifically for the unique phonetic and script requirements of Sanskrit:

- **Sanskrit Speech-to-Text (STT):** Real-time spoken Sanskrit transcription via WebSockets and pre-recorded audio file uploads.
- **Automated Manuscript OCR:** End-to-end background pipeline capable of batch-processing ancient Grantha and Devanagari book scans into searchable text.
- **Telegram Bots (`apps/ocr_bot`, `apps/transliterator`):**
  - Instant camera-to-text OCR directly inside Telegram.
  - Multi-script transliterator converting between Devanagari, IAST, Kannada, Telugu, Bengali, Malayalam, and Grantha scripts.

---

### 4. 🎮 Interactive Learning, Articles & Culture
- **QuizMaster (`quiz`):** Gamified quizzes on Sanskrit literature, grammar, and philosophy with live scorecards and downloadable certificates.
- **Sanskrit Games (`play`):** Interactive vocabulary builders, word-matching games, and synonym puzzles.
- **Research Articles Portal (`articles`):** Clean, distraction-free scholarly article reader with categorization and author publishing workflows.

---

## ⚡ Quick Start: Running Samshodhanam Locally

You can run the entire platform locally on your machine in 3 simple steps.

### Prerequisites
- **Python 3.10 or higher**
- `git`

### Step 1: Clone the Repository & Set Up Virtual Environment

```bash
git clone https://github.com/kalalenachar/samshodhanam.git
cd samshodhanam

# Create and activate a Python virtual environment:
python3 -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### Step 2: Install Required Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Start the Web Server

```bash
python server.py
```

Now open your web browser and navigate to:
- 🌐 **Main Web Portal:** `http://localhost:5001`
- 📚 **Standalone Digital Library (SDL):** `http://localhost:5000` (run with `python sdl_web/sdl.py`)
- 🛡️ **Admin Hub:** `http://localhost:5001/admin`

---

<details>
<summary>🛠️ <b>Advanced Developer Setup (Environment Variables, OCR, and Bots)</b></summary>

### 1. Environment Configuration (`.env`)
Create a local `.env` file from `.env.example`:
```bash
cp .env.example .env
```
Key configuration settings:
- `SECRET_KEY`: Random 32-byte string for session management and authentication.
- `GEMINI_API_KEY`: *(Optional)* Enables AI semantic vector search and explanation features.
- `GOOGLE_CLIENT_ID`: *(Optional)* Enables Google OAuth one-click user sign-in.
- `SMTP_USER` & `SMTP_PASS`: *(Optional)* Sends email notifications to volunteer proofreaders.

### 2. Initializing Development Databases
To initialize clean local SQLite databases and create an admin account:
```bash
python scripts/init_dev_db.py --admin-user admin --admin-pass admin123
```

### 3. Background Services & Telegram Bots
- **Telegram OCR Bot:** Configure `TELEGRAM_BOT_TOKEN` in `.env` and start via `python apps/ocr_bot/bot.py`.
- **Sanskrit STT Service:** Run the dedicated WebSocket engine via `python apps/sanskrit_stt/server.py`.
- **Systemd Auto-Start Scripts:** Production service templates are provided in `deploy.sh`.
</details>

---

## 🗺️ Project Architecture & Tech Stack

```
samshodhanam/
├── apps/                        # Grammatical & Linguistics Applications
│   ├── ashtadhyayi_companion/   # Paninian Sutra & Dhatupatha explorer
│   ├── chandas/                 # Metric prosody scanner & meter identification
│   ├── dhatu_explorer/          # Verbal conjugation engine
│   ├── shabda_explorer/         # Nominal declension engine
│   ├── sandhi_studio/           # Sandhi joining and compound splitting
│   ├── rigveda/                 # Vedic text, Padapatha & audio recitation
│   ├── sanskrit_stt/            # WebSocket Sanskrit speech recognition
│   ├── ocr_bot/                 # Telegram OCR processing bot
│   └── transliterator/          # Cross-script transliteration engine
├── sdl_web/                     # Sanskrit Digital Library core platform
├── articles/                    # Research articles and scholarly publishing portal
├── quiz/                        # Gamified quiz engine and certificates
├── play/                        # Pedagogical Sanskrit word games
├── db/                          # Database connection and search modules
├── scripts/                     # Maintenance, DB migration, and seeding utilities
└── server.py                    # Unified WSGI gateway & portal router
```

- **Backend:** Python 3.10+, Flask, WSGI multi-app routing, SQLite / PostgreSQL
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (responsive, lightweight, zero build-step overhead)
- **AI & NLP:** Google Gemini, ChromaDB vector store, Vidyut Sanskrit computational modules
- **Speech & OCR:** WebSocket audio streaming, OCR pipeline, Telegram Bot API

---

## 📑 In-Depth Documentation

For detailed architectural specifications and design guides, explore the repository documentation:
- [**System Architecture & Design**](ARCHITECTURE.md): Complete guide to WSGI routing, database schemas, and security.
- [**Manuscript Ingestion Pipeline**](INGESTION_PIPELINE.md): 7-step guide to PDF scanning, OCR, proofreading, and vectorization.
- [**Sanskrit Linguistic Normalization**](SANSKRIT_NORMALIZATION.md): Visarga, Avagraha, and Sandhi handling across search indexes.
- [**GitHub Proofreading Sync Spec**](GITHUB_BOOK_SYNC_SPEC.md): Technical specification for two-way manuscript synchronization.

---

## 🤝 Contributing

We warmly welcome contributions from everyone! Whether you are:
- A **Sanskrit scholar** who noticed an error in a grammatical derivation,
- A **developer** wanting to improve OCR accuracy or add new linguistics features,
- A **designer or educator** wanting to create new learning games.

Feel free to open an [Issue](https://github.com/kalalenachar/samshodhanam/issues) or submit a [Pull Request](https://github.com/kalalenachar/samshodhanam/pulls).
