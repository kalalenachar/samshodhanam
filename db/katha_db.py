"""
Samshodhana Mandiram — Katha (Story) Database Module

Separate SQLite database for Sanskrit stories/kathas.
Stores stories with rich HTML content, categories, media, and feedback.
"""

import sqlite3
import os
import hashlib
from datetime import datetime
from time_utils import get_ist_now

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'katha.db')


def _create_tables(conn):
    """Create all katha tables and indexes."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS kathas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            content_html TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'सामान्य',
            cover_image_url TEXT NOT NULL,
            media_json TEXT DEFAULT '[]',
            author TEXT DEFAULT '',
            reading_time INTEGER DEFAULT 5,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'published')),
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS katha_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            katha_id INTEGER NOT NULL,
            vote TEXT NOT NULL CHECK(vote IN ('up', 'down')),
            voter_hash TEXT NOT NULL,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (katha_id) REFERENCES kathas(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_kathas_status ON kathas(status);
        CREATE INDEX IF NOT EXISTS idx_kathas_category ON kathas(category);
        CREATE INDEX IF NOT EXISTS idx_kathas_published_at ON kathas(published_at);
        CREATE INDEX IF NOT EXISTS idx_katha_feedback_katha ON katha_feedback(katha_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_katha_feedback_unique ON katha_feedback(katha_id, voter_hash);
    ''')
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(katha_feedback)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'comments' not in columns:
            conn.execute("ALTER TABLE katha_feedback ADD COLUMN comments TEXT")
            conn.commit()
    except Exception as e:
        print(f"Error migrating katha_feedback schema: {e}")
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
            print(f"Katha database auto-initialized at {DB_PATH}")
        except Exception as e:
            print(f"Error auto-initializing katha database: {e}")

    return conn


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_db()
    try:
        _create_tables(conn)
        print(f"Katha database initialized at {DB_PATH}")
    finally:
        conn.close()


# =============================================================================
# STORY CRUD
# =============================================================================

def create_katha(title, summary, content_html, category, cover_image_url,
                 media_json='[]', author='', reading_time=5, status='draft', published_at=None):
    """Create a new katha/story. Returns the new ID or None."""
    conn = get_db()
    try:
        if status == 'published' and not published_at:
            published_at = get_ist_now().isoformat()
        cursor = conn.execute(
            '''INSERT INTO kathas (title, summary, content_html, category, cover_image_url,
               media_json, author, reading_time, status, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (title, summary, content_html, category, cover_image_url,
             media_json, author, reading_time, status, published_at)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating katha: {e}")
        return None
    finally:
        conn.close()


def update_katha(katha_id, title, summary, content_html, category, cover_image_url,
                 media_json='[]', author='', reading_time=5, published_at=None, status=None):
    """Update an existing katha. Returns True on success."""
    conn = get_db()
    try:
        if status:
            conn.execute(
                '''UPDATE kathas SET title=?, summary=?, content_html=?, category=?,
                   cover_image_url=?, media_json=?, author=?, reading_time=?,
                   published_at=?, status=?, updated_at=? WHERE id=?''',
                (title, summary, content_html, category, cover_image_url,
                 media_json, author, reading_time, published_at, status, get_ist_now().isoformat(), katha_id)
            )
        else:
            conn.execute(
                '''UPDATE kathas SET title=?, summary=?, content_html=?, category=?,
                   cover_image_url=?, media_json=?, author=?, reading_time=?,
                   published_at=?, updated_at=? WHERE id=?''',
                (title, summary, content_html, category, cover_image_url,
                 media_json, author, reading_time, published_at, get_ist_now().isoformat(), katha_id)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating katha: {e}")
        return False
    finally:
        conn.close()


def delete_katha(katha_id):
    """Delete a katha and its feedback. Returns True on success."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM kathas WHERE id = ?', (katha_id,))
        # Check if table is empty and reset autoincrement ID sequence to start from 1 next time
        cnt = conn.execute('SELECT COUNT(*) FROM kathas').fetchone()[0]
        if cnt == 0:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'kathas'")
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting katha: {e}")
        return False
    finally:
        conn.close()


def get_all_kathas():
    """Get all kathas (including drafts) for admin panel. Returns list of dicts."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT k.*,
                      COALESCE((SELECT COUNT(*) FROM katha_feedback f WHERE f.katha_id = k.id AND f.vote = 'up'), 0) as upvotes,
                      COALESCE((SELECT COUNT(*) FROM katha_feedback f WHERE f.katha_id = k.id AND f.vote = 'down'), 0) as downvotes
               FROM kathas k ORDER BY k.title ASC'''
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting all kathas: {e}")
        return []
    finally:
        conn.close()


def get_katha_by_id(katha_id):
    """Get a single katha by ID. Returns dict or None."""
    conn = get_db()
    try:
        row = conn.execute(
            '''SELECT k.*,
                      COALESCE((SELECT COUNT(*) FROM katha_feedback f WHERE f.katha_id = k.id AND f.vote = 'up'), 0) as upvotes,
                      COALESCE((SELECT COUNT(*) FROM katha_feedback f WHERE f.katha_id = k.id AND f.vote = 'down'), 0) as downvotes
               FROM kathas k WHERE k.id = ?''',
            (katha_id,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error getting katha: {e}")
        return None
    finally:
        conn.close()


def get_published_kathas(category=None, sort_by='title'):
    """Get published kathas for public display with optional filters."""
    conn = get_db()
    try:
        query = '''SELECT k.*,
                          COALESCE((SELECT COUNT(*) FROM katha_feedback f WHERE f.katha_id = k.id AND f.vote = 'up'), 0) as upvotes,
                          COALESCE((SELECT COUNT(*) FROM katha_feedback f WHERE f.katha_id = k.id AND f.vote = 'down'), 0) as downvotes
                   FROM kathas k WHERE k.status = 'published' '''
        params = []

        if category:
            query += ' AND k.category = ?'
            params.append(category)

        # Sorting
        if sort_by == 'date_asc':
            query += ' ORDER BY k.published_at ASC'
        elif sort_by == 'date_desc':
            query += ' ORDER BY k.published_at DESC'
        elif sort_by == 'category':
            query += ' ORDER BY k.category ASC, k.title ASC'
        elif sort_by == 'popular':
            query += ' ORDER BY (upvotes - downvotes) DESC, k.title ASC'
        elif sort_by == 'title_desc':
            query += ' ORDER BY k.title DESC'
        else:  # title (default)
            query += ' ORDER BY k.title ASC'

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting published kathas: {e}")
        return []
    finally:
        conn.close()


def toggle_status(katha_id):
    """Toggle between draft and published. Returns new status or None."""
    conn = get_db()
    try:
        row = conn.execute('SELECT status, cover_image_url FROM kathas WHERE id = ?', (katha_id,)).fetchone()
        if not row:
            return None

        new_status = 'published' if row['status'] == 'draft' else 'draft'
        
        if new_status == 'published':
            cover_url = (row['cover_image_url'] or '').strip()
            if not cover_url:
                raise ValueError("Cover image URL is required to publish this story")

            # Only set published_at if it hasn't been published before
            existing = conn.execute('SELECT published_at FROM kathas WHERE id = ?', (katha_id,)).fetchone()
            published_at = get_ist_now().isoformat()
            if existing and existing['published_at']:
                published_at = existing['published_at']

            conn.execute(
                'UPDATE kathas SET status=?, published_at=?, updated_at=? WHERE id=?',
                (new_status, published_at, get_ist_now().isoformat(), katha_id)
            )
        else:
            conn.execute(
                'UPDATE kathas SET status=?, updated_at=? WHERE id=?',
                (new_status, get_ist_now().isoformat(), katha_id)
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
    """Get distinct categories from published kathas."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM kathas WHERE status = 'published' ORDER BY category"
        ).fetchall()
        return [r['category'] for r in rows]
    except Exception as e:
        print(f"Error getting categories: {e}")
        return []
    finally:
        conn.close()


def get_all_categories():
    """Get distinct categories from ALL kathas (for admin)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM kathas ORDER BY category"
        ).fetchall()
        return [r['category'] for r in rows]
    except Exception as e:
        print(f"Error getting all categories: {e}")
        return []
    finally:
        conn.close()


def get_katha_count():
    """Get total number of kathas."""
    conn = get_db()
    try:
        row = conn.execute('SELECT COUNT(*) as count FROM kathas').fetchone()
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
    return hashlib.sha256(f"katha_feedback_{ip}".encode()).hexdigest()[:32]


def submit_feedback(katha_id, vote, voter_ip, comments=None):
    """Submit or toggle a thumbs up/down vote with an optional comment.
    If same voter voted before, it updates. Returns {'vote': 'up'/'down'/None, 'upvotes': n, 'downvotes': n}."""
    voter_hash = _hash_ip(voter_ip)
    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT id, vote FROM katha_feedback WHERE katha_id = ? AND voter_hash = ?',
            (katha_id, voter_hash)
        ).fetchone()

        if existing:
            if existing['vote'] == vote and not comments:
                # Same vote again and no comment update — remove it (toggle off)
                conn.execute('DELETE FROM katha_feedback WHERE id = ?', (existing['id'],))
                conn.commit()
                current_vote = None
            else:
                # Different vote or we are updating / adding a comment — update
                conn.execute(
                    'UPDATE katha_feedback SET vote = ?, comments = ? WHERE id = ?',
                    (vote, comments, existing['id'])
                )
                conn.commit()
                current_vote = vote
        else:
            # New vote
            conn.execute(
                'INSERT INTO katha_feedback (katha_id, vote, voter_hash, comments) VALUES (?, ?, ?, ?)',
                (katha_id, vote, voter_hash, comments)
            )
            conn.commit()
            current_vote = vote

        # Get updated counts
        stats = get_feedback_stats(katha_id, conn=conn)
        stats['vote'] = current_vote
        return stats
    except Exception as e:
        print(f"Error submitting katha feedback: {e}")
        return {'vote': None, 'upvotes': 0, 'downvotes': 0}
    finally:
        conn.close()


def get_katha_feedback_comments(katha_id):
    """Get all feedback comments/entries for a specific katha, with the comments first."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT vote, comments, created_at FROM katha_feedback
               WHERE katha_id = ? AND (comments IS NOT NULL AND comments != '')
               ORDER BY created_at DESC''',
            (katha_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting feedback comments: {e}")
        return []
    finally:
        conn.close()


def get_feedback_stats(katha_id, conn=None):
    """Get upvote/downvote counts for a katha."""
    should_close = conn is None
    if conn is None:
        conn = get_db()
    try:
        up = conn.execute(
            "SELECT COUNT(*) as c FROM katha_feedback WHERE katha_id = ? AND vote = 'up'",
            (katha_id,)
        ).fetchone()
        down = conn.execute(
            "SELECT COUNT(*) as c FROM katha_feedback WHERE katha_id = ? AND vote = 'down'",
            (katha_id,)
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


def get_voter_vote(katha_id, voter_ip):
    """Check what vote a specific voter has cast on a katha. Returns 'up', 'down', or None."""
    voter_hash = _hash_ip(voter_ip)
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT vote FROM katha_feedback WHERE katha_id = ? AND voter_hash = ?',
            (katha_id, voter_hash)
        ).fetchone()
        return row['vote'] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def get_voter_feedback(katha_id, voter_ip):
    """Check vote and comment a voter has cast on a katha. Returns a dict."""
    voter_hash = _hash_ip(voter_ip)
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT vote, comments FROM katha_feedback WHERE katha_id = ? AND voter_hash = ?',
            (katha_id, voter_hash)
        ).fetchone()
        if row:
            return {'vote': row['vote'], 'comments': row['comments']}
        return {'vote': None, 'comments': None}
    except Exception:
        return {'vote': None, 'comments': None}
    finally:
        conn.close()


def import_kathas(stories_list):
    """Bulk import stories from a list of dicts.
    Returns (added_count, errors_list, skipped_list)."""
    added = 0
    errors = []
    skipped = []
    conn = get_db()
    try:
        for i, s in enumerate(stories_list):
            try:
                title = s.get('title', '').strip()
                content_html = s.get('content_html', '').strip()
                cover_image_url = s.get('cover_image_url', '').strip()
                
                status = s.get('status', 'draft')
                if isinstance(status, str):
                    status = status.strip().lower()
                if status not in ('draft', 'published'):
                    status = 'draft'

                if not title or not content_html:
                    errors.append(f"Story {i+1}: Missing required fields (title/content_html).")
                    continue

                if status == 'published' and not cover_image_url:
                    errors.append(f"Story {i+1}: Cover image URL is required when status is published.")
                    continue

                # Check if a story with the same title already exists
                existing = conn.execute(
                    'SELECT id FROM kathas WHERE title = ?',
                    (title,)
                ).fetchone()

                if existing:
                    skipped.append({
                        "title": title
                    })
                    continue

                summary = ""
                category = s.get('category', '').strip() or 'सामान्य'
                author = s.get('author', '').strip()
                reading_time = int(s.get('reading_time', 5))
                published_at = s.get('published_at', '').strip() or None

                conn.execute(
                    '''INSERT INTO kathas (title, summary, content_html, category, cover_image_url, media_json, author, reading_time, status, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (title, summary, content_html, category, cover_image_url, '[]', author, reading_time, status, published_at)
                )
                added += 1
            except Exception as e:
                errors.append(f"Story {i+1}: {str(e)}")
        conn.commit()
    except Exception as e:
        print(f"Error importing stories: {e}")
        errors.append(f"Database error: {str(e)}")
    finally:
        conn.close()
    return added, errors, skipped
