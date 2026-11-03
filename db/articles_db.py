"""
Samshodhana Mandiram — Articles Database Module

Separate SQLite database for Sanskrit articles.
Stores articles with full HTML content, categories, and feedback.
"""

import sqlite3
import os
import hashlib
from datetime import datetime
from time_utils import get_ist_now

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'articles.db')


def _create_tables(conn):
    """Create all article tables and indexes."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            content_html TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'सामान्य',
            cover_image_url TEXT NOT NULL,
            author TEXT DEFAULT '',
            reading_time INTEGER DEFAULT 5,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'published')),
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS article_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            vote TEXT NOT NULL CHECK(vote IN ('up', 'down')),
            voter_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
        CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
        CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
        CREATE INDEX IF NOT EXISTS idx_article_feedback_article ON article_feedback(article_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_article_feedback_unique ON article_feedback(article_id, voter_hash);
    ''')
    conn.commit()


def get_db():
    """Get a database connection with row_factory for dict-like access."""
    db_exists = os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    if not db_exists:
        try:
            _create_tables(conn)
            print(f"Articles database auto-initialized at {DB_PATH}")
        except Exception as e:
            print(f"Error auto-initializing articles database: {e}")

    return conn


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_db()
    try:
        _create_tables(conn)
        print(f"Articles database initialized at {DB_PATH}")
    finally:
        conn.close()


# =============================================================================
# ARTICLE CRUD
# =============================================================================

def create_article(title, summary, content_html, category, cover_image_url,
                   author='', reading_time=5, status='draft', published_at=None):
    """Create a new article. Returns the new ID or None."""
    conn = get_db()
    try:
        if status == 'published' and not published_at:
            published_at = get_ist_now().isoformat()
        cursor = conn.execute(
            '''INSERT INTO articles (title, summary, content_html, category, cover_image_url,
               author, reading_time, status, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (title, summary, content_html, category, cover_image_url,
             author, reading_time, status, published_at)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating article: {e}")
        return None
    finally:
        conn.close()


def update_article(article_id, title, summary, content_html, category, cover_image_url,
                   author='', reading_time=5, published_at=None, status=None):
    """Update an existing article. Returns True on success."""
    conn = get_db()
    try:
        if status:
            conn.execute(
                '''UPDATE articles SET title=?, summary=?, content_html=?, category=?,
                   cover_image_url=?, author=?, reading_time=?,
                   published_at=?, status=?, updated_at=? WHERE id=?''',
                (title, summary, content_html, category, cover_image_url,
                 author, reading_time, published_at, status, get_ist_now().isoformat(), article_id)
            )
        else:
            conn.execute(
                '''UPDATE articles SET title=?, summary=?, content_html=?, category=?,
                   cover_image_url=?, author=?, reading_time=?,
                   published_at=?, updated_at=? WHERE id=?''',
                (title, summary, content_html, category, cover_image_url,
                 author, reading_time, published_at, get_ist_now().isoformat(), article_id)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating article: {e}")
        return False
    finally:
        conn.close()


def delete_article(article_id):
    """Delete an article and its feedback. Returns True on success."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM articles WHERE id = ?', (article_id,))
        # Check if table is empty and reset autoincrement ID sequence to start from 1 next time
        cnt = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        if cnt == 0:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'articles'")
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting article: {e}")
        return False
    finally:
        conn.close()


def get_all_articles():
    """Get all articles (including drafts) for admin panel. Returns list of dicts."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT a.*,
                      COALESCE((SELECT COUNT(*) FROM article_feedback f WHERE f.article_id = a.id AND f.vote = 'up'), 0) as upvotes,
                      COALESCE((SELECT COUNT(*) FROM article_feedback f WHERE f.article_id = a.id AND f.vote = 'down'), 0) as downvotes
               FROM articles a ORDER BY a.created_at DESC'''
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting all articles: {e}")
        return []
    finally:
        conn.close()


def get_article_by_id(article_id):
    """Get a single article by ID. Returns dict or None."""
    conn = get_db()
    try:
        row = conn.execute(
            '''SELECT a.*,
                      COALESCE((SELECT COUNT(*) FROM article_feedback f WHERE f.article_id = a.id AND f.vote = 'up'), 0) as upvotes,
                      COALESCE((SELECT COUNT(*) FROM article_feedback f WHERE f.article_id = a.id AND f.vote = 'down'), 0) as downvotes
               FROM articles a WHERE a.id = ?''',
            (article_id,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error getting article: {e}")
        return None
    finally:
        conn.close()


def get_published_articles(category=None, sort_by='date_desc'):
    """Get published articles for public display with optional filters."""
    conn = get_db()
    try:
        query = '''SELECT a.*,
                          COALESCE((SELECT COUNT(*) FROM article_feedback f WHERE f.article_id = a.id AND f.vote = 'up'), 0) as upvotes,
                          COALESCE((SELECT COUNT(*) FROM article_feedback f WHERE f.article_id = a.id AND f.vote = 'down'), 0) as downvotes
                   FROM articles a WHERE a.status = 'published' '''
        params = []

        if category:
            query += ' AND a.category = ?'
            params.append(category)

        # Sorting
        if sort_by == 'date_asc':
            query += ' ORDER BY a.published_at ASC'
        elif sort_by == 'category':
            query += ' ORDER BY a.category ASC, a.published_at DESC'
        elif sort_by == 'popular':
            query += ' ORDER BY (upvotes - downvotes) DESC, a.published_at DESC'
        else:  # date_desc (default)
            query += ' ORDER BY a.published_at DESC'

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting published articles: {e}")
        return []
    finally:
        conn.close()


def toggle_status(article_id):
    """Toggle between draft and published. Returns new status or None."""
    conn = get_db()
    try:
        row = conn.execute('SELECT status, cover_image_url FROM articles WHERE id = ?', (article_id,)).fetchone()
        if not row:
            return None

        new_status = 'published' if row['status'] == 'draft' else 'draft'
        
        if new_status == 'published':
            # Only set published_at if it hasn't been published before
            existing = conn.execute('SELECT published_at FROM articles WHERE id = ?', (article_id,)).fetchone()
            published_at = get_ist_now().isoformat()
            if existing and existing['published_at']:
                published_at = existing['published_at']

            conn.execute(
                'UPDATE articles SET status=?, published_at=?, updated_at=? WHERE id=?',
                (new_status, published_at, get_ist_now().isoformat(), article_id)
            )
        else:
            conn.execute(
                'UPDATE articles SET status=?, updated_at=? WHERE id=?',
                (new_status, get_ist_now().isoformat(), article_id)
            )

        conn.commit()
        return new_status
    except ValueError as e:
        raise e
    except Exception as e:
        print(f"Error toggling status: {e}")
        return None
    finally:
        conn.close()


def get_categories():
    """Get distinct categories from published articles."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM articles WHERE status = 'published' ORDER BY category"
        ).fetchall()
        return [r['category'] for r in rows]
    except Exception as e:
        print(f"Error getting categories: {e}")
        return []
    finally:
        conn.close()


def get_all_categories():
    """Get distinct categories from ALL articles (for admin)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM articles ORDER BY category"
        ).fetchall()
        return [r['category'] for r in rows]
    except Exception as e:
        print(f"Error getting all categories: {e}")
        return []
    finally:
        conn.close()


def get_article_count():
    """Get total number of articles."""
    conn = get_db()
    try:
        row = conn.execute('SELECT COUNT(*) as count FROM articles').fetchone()
        return row['count'] if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


# =============================================================================
# FEEDBACK
# =============================================================================

def _hash_ip(ip):
    """Hash an IP address for privacy-safe deduplication."""
    return hashlib.sha256(f"article_feedback_{ip}".encode()).hexdigest()[:32]


def submit_feedback(article_id, vote, voter_ip):
    """Submit or toggle a thumbs up/down vote.
    If same voter voted before, it updates. Returns {'vote': 'up'/'down'/None, 'upvotes': n, 'downvotes': n}."""
    voter_hash = _hash_ip(voter_ip)
    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT id, vote FROM article_feedback WHERE article_id = ? AND voter_hash = ?',
            (article_id, voter_hash)
        ).fetchone()

        if existing:
            if existing['vote'] == vote:
                # Same vote again — remove it (toggle off)
                conn.execute('DELETE FROM article_feedback WHERE id = ?', (existing['id'],))
                conn.commit()
                current_vote = None
            else:
                # Different vote — update
                conn.execute('UPDATE article_feedback SET vote = ? WHERE id = ?', (vote, existing['id']))
                conn.commit()
                current_vote = vote
        else:
            # New vote
            conn.execute(
                'INSERT INTO article_feedback (article_id, vote, voter_hash) VALUES (?, ?, ?)',
                (article_id, vote, voter_hash)
            )
            conn.commit()
            current_vote = vote

        # Get updated counts
        stats = get_feedback_stats(article_id, conn=conn)
        stats['vote'] = current_vote
        return stats
    except Exception as e:
        print(f"Error submitting article feedback: {e}")
        return {'vote': None, 'upvotes': 0, 'downvotes': 0}
    finally:
        conn.close()


def get_feedback_stats(article_id, conn=None):
    """Get upvote/downvote counts for an article."""
    should_close = conn is None
    if conn is None:
        conn = get_db()
    try:
        up = conn.execute(
            "SELECT COUNT(*) as c FROM article_feedback WHERE article_id = ? AND vote = 'up'",
            (article_id,)
        ).fetchone()
        down = conn.execute(
            "SELECT COUNT(*) as c FROM article_feedback WHERE article_id = ? AND vote = 'down'",
            (article_id,)
        ).fetchone()
        return {
            'upvotes': up['c'] if up else 0,
            'downvotes': down['c'] if down else 0
        }
    except Exception:
        return {'upvotes': 0, 'downvotes': 0}
    finally:
        if should_close:
            conn.close()


def get_voter_vote(article_id, voter_ip):
    """Check what vote a specific voter has cast on an article. Returns 'up', 'down', or None."""
    voter_hash = _hash_ip(voter_ip)
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT vote FROM article_feedback WHERE article_id = ? AND voter_hash = ?',
            (article_id, voter_hash)
        ).fetchone()
        return row['vote'] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def import_articles(articles_list):
    """Bulk import articles from a list of dicts.
    Returns (added_count, errors_list, skipped_list)."""
    added = 0
    errors = []
    skipped = []
    conn = get_db()
    try:
        for i, a in enumerate(articles_list):
            try:
                title = a.get('title', '').strip()
                content_html = a.get('content_html', '').strip()
                cover_image_url = a.get('cover_image_url', '').strip()

                status = a.get('status', 'draft')
                if isinstance(status, str):
                    status = status.strip().lower()
                if status not in ('draft', 'published'):
                    status = 'draft'

                if not title or not content_html:
                    errors.append(f"Article {i+1}: Missing required fields (title/content_html).")
                    continue

                if status == 'published' and not cover_image_url:
                    status = 'draft'

                # Check if an article with the same title already exists
                existing = conn.execute(
                    'SELECT id FROM articles WHERE title = ?',
                    (title,)
                ).fetchone()

                if existing:
                    skipped.append({
                        "title": title
                    })
                    continue

                summary = a.get('summary', '').strip()
                category = a.get('category', '').strip() or 'सामान्य'
                author = a.get('author', '').strip()
                reading_time = int(a.get('reading_time', 5))
                published_at = a.get('published_at', '').strip() or None

                conn.execute(
                    '''INSERT INTO articles (title, summary, content_html, category, cover_image_url, author, reading_time, status, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (title, summary, content_html, category, cover_image_url, author, reading_time, status, published_at)
                )
                added += 1
            except Exception as e:
                errors.append(f"Article {i+1}: {str(e)}")
        conn.commit()
    except Exception as e:
        print(f"Error importing articles: {e}")
        errors.append(f"Database error: {str(e)}")
    finally:
        conn.close()
    return added, errors, skipped
