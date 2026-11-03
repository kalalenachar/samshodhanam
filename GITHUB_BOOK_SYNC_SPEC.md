# GitHub Book Proofreading Sync — Architecture & Specification

> **Implementation Status**: *Proposed Architecture & Specification (Roadmap Feature)*  
> The GitHub REST synchronization endpoints and automated synchronization workflows described in this specification document are designed for future two-way repository synchronization. Configuration keys in `.env.example` (`GITHUB_BOOKS_REPO`, `GITHUB_BOOKS_TOKEN`, `GITHUB_BOOKS_BRANCH`) are reserved placeholders.

---

## 1. Overview

The **GitHub Book Sync Subsystem** specifies how crowdsourced and scholar-verified Sanskrit manuscript transcriptions can be version-controlled, auditable, and collaborative across remote repositories.

```
┌────────────────────────────┐         GitHub REST API v3/v4         ┌────────────────────────────┐
│      Open-Samsho SDL       │ ────────────────────────────────────> │  Target GitHub Repository  │
│  (Community Proofreading)  │ <──────────────────────────────────── │    (e.g., org/books-db)    │
└────────────────────────────┘         Pull / Webhook Updates        └────────────────────────────┘
```

---

## 2. Configuration & Authentication

The subsystem relies on standard GitHub personal access tokens (PAT) or GitHub App installation tokens, configured via environment variables in `.env` (reserved in `.env.example`):

```env
# Target repository in org/repo format
GITHUB_BOOKS_REPO=your-org/sanskrit-proofread-texts

# Fine-grained PAT with 'Contents: Read and Write' permissions
GITHUB_BOOKS_TOKEN=ghp_yourPersonalAccessTokenHere

# Target branch to synchronize with
GITHUB_BOOKS_BRANCH=main
```

---

## 3. Directory Layout in the Synchronized Repository

Each digitized text is maintained within the target GitHub repository under a standardized hierarchy:

```text
books/
├── nyaya_sudha/
│   ├── metadata.json           # Title, author, commentary, categories, source URL
│   ├── book.sdl                # Binary/compressed SDL representation
│   ├── pages/                  # Normalized transcription per page
│   │   ├── page_0001.txt
│   │   ├── page_0002.txt
│   │   └── ...
│   └── full_text.txt           # Aggregated page-marked text
└── ...
```

---

## 4. Synchronization Lifecycle

### 4.1 Export Workflow (SDL → GitHub)
1. **Verification**: A proofreader edits a page in the SDL Reader UI and submits changes.
2. **Review/Approval**: An administrator or trusted scholar reviews and approves the edit.
3. **Commit Creation**: The SDL backend invokes the GitHub REST API (`POST /repos/{owner}/{repo}/contents/{path}`) with:
   - Message: `proofread(book_id): page 14 verified by @scholar_handle`
   - Content: Base64-encoded UTF-8 normalized Sanskrit text.
   - Committer information reflecting the platform / author.

### 4.2 Ingestion Workflow (GitHub → SDL)
1. **Manual / Scheduled Fetch**: Triggered periodically or via GitHub Webhook (`push` event).
2. **Diff Application**: If a text is edited directly on GitHub (e.g. via web editor or pull request), SDL downloads the updated page files.
3. **Re-chunking & Re-embedding**: The SDL ingestion pipeline triggers automated re-chunking and vector re-indexing for modified pages.

---

## 5. Security & Rate Limiting

- **Token Protection**: `GITHUB_BOOKS_TOKEN` is strictly kept on the server side and never sent to client browsers.
- **Rate Limit Management**: All calls respect GitHub API headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`).
- **Audit Trails**: Every synchronization event is logged with the corresponding commit SHA.
