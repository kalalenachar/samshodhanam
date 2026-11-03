# Contributing to Samshodhanam (संशोधनम्)

Thank you for your interest in contributing to **Samshodhanam**! We welcome contributions from Sanskrit scholars, linguists, developers, and educators.

## Ways to Contribute

1. **Grammar & Lexicon:** Report inaccuracies in sutra derivations, chandas prosody classification, or dhatu/shabda conjugations.
2. **OCR & AI Pipelines:** Improve model accuracy for ancient scripts (Grantha, Sharada, Devanagari) or optimize WebSocket STT streaming.
3. **Manuscript Preservation:** Help curate and verify digitized manuscripts via the Sanskrit Digital Library (SDL) split-screen proofreader.
4. **Pedagogical Games:** Design new interactive educational games and quizzes for learners.
5. **Documentation & Translations:** Improve setup guides, translate UI elements into regional Indic languages, or write tutorials.

---

## Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/samshodhanam.git
   cd samshodhanam
   ```

2. **Set up a Python virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

4. **Run the local unified server:**
   ```bash
   python server.py
   ```
   Open `http://localhost:5001` in your browser.

5. **Run test suite:**
   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   ```

---

## Submitting Pull Requests

1. Create a new topic branch (`git checkout -b feat/your-feature-name`).
2. Keep changes focused and atomic.
3. Verify that tests pass before pushing.
4. Open a Pull Request against the `main` branch with a clear description of changes.

---

## Code of Conduct

Please be respectful and constructive in all community interactions. We are committed to providing a welcoming, collaborative environment for everyone.
