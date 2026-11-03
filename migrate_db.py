import os
import shutil
import sqlite3
import json
from datetime import datetime
from time_utils import get_ist_now

def migrate():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_dir = os.path.join(project_root, 'db')
    sdl_web_dir = os.path.join(project_root, 'sdl_web')

    old_users_db = os.path.join(sdl_web_dir, 'sdl_users.db')
    old_katha_db = os.path.join(sdl_web_dir, 'sdl_katha.db')
    old_admins_json = os.path.join(sdl_web_dir, 'admins.json')

    new_common_db = os.path.join(db_dir, 'common.db')
    new_quiz_db = os.path.join(db_dir, 'quiz.db')
    new_katha_db = os.path.join(db_dir, 'katha.db')
    new_articles_db = os.path.join(db_dir, 'articles.db')

    # Step 6a: Create db/ directory if not exists
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print("Created db/ directory.")

    # Import the db modules to initialize database schemas
    import sys
    sys.path.insert(0, project_root)
    from db import common_db, quiz_db, katha_db, articles_db

    print("Initializing schemas in the new databases...")
    common_db.init_db()
    quiz_db.init_db()
    katha_db.init_db()
    articles_db.init_db()

    # Step 6b & 6c: Open sdl_web/sdl_users.db and copy tables to common.db and quiz.db
    if os.path.exists(old_users_db):
        print(f"Migrating data from {old_users_db}...")
        conn = sqlite3.connect(old_users_db)
        
        # Verify source counts
        cursor = conn.cursor()
        
        # Helper to check if a table exists
        def table_exists(table_name):
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            return cursor.fetchone() is not None

        tables_to_common = ['users', 'favourites', 'booklists', 'booklist_items', 'user_tokens', 'user_otps']
        tables_to_quiz = ['quiz_questions', 'quiz_results']

        # Copy common tables
        print("Copying user tables to common.db...")
        conn.execute("ATTACH DATABASE ? AS common", (new_common_db,))
        for t in tables_to_common:
            if table_exists(t):
                row_count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  Table '{t}': copying {row_count} rows...")
                conn.execute(f"INSERT OR REPLACE INTO common.{t} SELECT * FROM main.{t}")
            else:
                print(f"  Warning: Table '{t}' not found in old database.")
        conn.commit()
        conn.execute("DETACH DATABASE common")

        # Copy quiz tables
        print("Copying quiz tables to quiz.db...")
        conn.execute("ATTACH DATABASE ? AS quiz", (new_quiz_db,))
        for t in tables_to_quiz:
            if table_exists(t):
                row_count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  Table '{t}': copying {row_count} rows...")
                conn.execute(f"INSERT OR REPLACE INTO quiz.{t} SELECT * FROM main.{t}")
            else:
                print(f"  Warning: Table '{t}' not found in old database.")
        conn.commit()
        conn.execute("DETACH DATABASE quiz")
        
        conn.close()
        print("Users and quiz data migration complete.")
    else:
        print(f"Old user database not found at {old_users_db}. Skipping user/quiz tables copy.")

    # Step 6d: Copy file sdl_web/sdl_katha.db -> db/katha.db if new katha.db is empty
    if os.path.exists(old_katha_db):
        print(f"Copying katha database from {old_katha_db}...")
        # To preserve existing content and feedback safely, we copy the file directly
        # but only if the file size/contents in old_katha_db are non-empty
        # and we overwrite the initialized new_katha_db
        try:
            shutil.copy2(old_katha_db, new_katha_db)
            print(f"Successfully copied katha database to {new_katha_db}")
        except Exception as e:
            print(f"Error copying katha database: {e}")
    else:
        print(f"Old katha database not found at {old_katha_db}. Skipping katha database copy.")

    # Step 6f: Migrate admins.json to common.db admins table
    if os.path.exists(old_admins_json):
        print(f"Migrating admins from {old_admins_json} to common.db...")
        try:
            with open(old_admins_json, 'r', encoding='utf-8') as f:
                admins_data = json.load(f)
                users = admins_data.get('users', {})
                
            conn = sqlite3.connect(new_common_db)
            cursor = conn.cursor()
            for username, data in users.items():
                password_hash = data.get('password_hash')
                permissions = data.get('permissions', [])
                created_at = data.get('created_at')
                last_login = data.get('last_login')
                
                perms_json = json.dumps(permissions)
                # Check duplicate
                cursor.execute("SELECT username FROM admins WHERE UPPER(username) = ?", (username.upper(),))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO admins (username, password_hash, permissions_json, created_at, last_login) VALUES (?, ?, ?, ?, ?)",
                        (username.upper(), password_hash, perms_json, created_at, last_login)
                    )
                    print(f"  Admin '{username}' migrated.")
                else:
                    print(f"  Admin '{username}' already exists in SQLite table.")
            conn.commit()
            conn.close()
            print("Admin migration complete.")
        except Exception as e:
            print(f"Error migrating admins from JSON: {e}")
    else:
        print(f"Old admins JSON not found at {old_admins_json}. Skipping admins migration.")

    # Step 6i: Migrate HTML articles to db/articles.db
    print("Migrating HTML articles to articles.db...")
    articles_dir = os.path.join(project_root, 'articles')
    if os.path.exists(articles_dir):
        import re
        import html
        
        html_files = [f for f in os.listdir(articles_dir) if f.endswith('.html') and f not in ('admin-dashboard.html', 'admin-login.html', 'reader.html')]
        
        for fname in html_files:
            fpath = os.path.join(articles_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Title
                title_match = re.search(r'<h1>(.*?)</h1>', html_content)
                title = title_match.group(1).strip() if title_match else fname.replace('.html', '').replace('-', ' ').title()
                title = html.unescape(title)
                
                # Category
                cat_match = re.search(r'<(?:span|div) class="category-badge">(.*?)</(?:span|div)>', html_content)
                category = cat_match.group(1).strip() if cat_match else "सामान्य"
                category = html.unescape(category)
                
                # Defaults
                author = "Samshodhana Mandiram"
                reading_time = 5
                published_at = get_ist_now().isoformat()
                
                # Parse meta-info if present
                meta_info_match = re.search(r'<div class="meta-info">(.*?)</div>', html_content, re.DOTALL)
                if meta_info_match:
                    meta_html = meta_info_match.group(1)
                    spans = re.findall(r'<span>(.*?)</span>', meta_html)
                    for s in spans:
                        cleaned_s = s.strip()
                        if ',' in cleaned_s and any(month in cleaned_s for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                            try:
                                dt = datetime.strptime(cleaned_s, "%B %d, %Y")
                                published_at = dt.isoformat()
                            except Exception:
                                published_at = cleaned_s
                                
                    for s in spans:
                        cleaned_s = s.strip()
                        if 'Read' in cleaned_s:
                            digits = re.findall(r'\d+', cleaned_s)
                            if digits:
                                reading_time = int(digits[0])
                                
                    for s in spans:
                        cleaned_s = s.strip()
                        if not ',' in cleaned_s and 'Read' not in cleaned_s and len(cleaned_s) > 3:
                            author = cleaned_s

                # Content
                content_match = re.search(r'<div class="content">(.*?)(?:</div>\s*<div class="article-footer">|</div>\s*</article>)', html_content, re.DOTALL)
                content_html = content_match.group(1).strip() if content_match else ""
                
                # Summary
                summary = ""
                first_p = re.search(r'<p>(.*?)</p>', content_html, re.DOTALL)
                if first_p:
                    summary = re.sub(r'<.*?>', '', first_p.group(1)).strip()
                    summary = html.unescape(summary)
                
                # Check duplicate by title
                conn_art = articles_db.get_db()
                existing_article = conn_art.execute("SELECT id FROM articles WHERE title = ?", (title,)).fetchone()
                conn_art.close()
                if existing_article:
                    print(f"  Article '{title}' already exists in DB. Skipping duplicate insertion.")
                    continue

                res_id = articles_db.create_article(
                    title=title,
                    summary=summary,
                    content_html=content_html,
                    category=category,
                    cover_image_url="",
                    author=author,
                    reading_time=reading_time,
                    status='published',
                    published_at=published_at
                )
                if res_id:
                    print(f"  Article '{title}' migrated with ID {res_id}.")
                else:
                    print(f"  Article '{title}' failed to migrate.")
            except Exception as e:
                print(f"  Error migrating article {fname}: {e}")
    else:
        print(f"Articles HTML directory not found at {articles_dir}.")

    # Step 6g: Print migration summary and verification
    print("\n--- MIGRATION VERIFICATION ---")
    
    # Check common.db row counts
    if os.path.exists(new_common_db):
        conn = sqlite3.connect(new_common_db)
        print("common.db counts:")
        for t in ['users', 'favourites', 'booklists', 'booklist_items', 'user_tokens', 'user_otps', 'admins']:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {count} rows")
        conn.close()

    # Check quiz.db row counts
    if os.path.exists(new_quiz_db):
        conn = sqlite3.connect(new_quiz_db)
        print("quiz.db counts:")
        for t in ['quiz_questions', 'quiz_results']:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {count} rows")
        conn.close()

    # Check katha.db row counts
    if os.path.exists(new_katha_db):
        conn = sqlite3.connect(new_katha_db)
        print("katha.db counts:")
        for t in ['kathas', 'katha_feedback']:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {count} rows")
        conn.close()

    # Check articles.db row counts
    if os.path.exists(new_articles_db):
        conn = sqlite3.connect(new_articles_db)
        print("articles.db counts:")
        for t in ['articles', 'article_feedback']:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {count} rows")
        conn.close()

    # Step 6h: Delete old files
    # We will do this under an explicit flag or direct execution to ensure safe transitions.
    # Let's perform cleanup now.
    print("\nCleaning up old database files and legacy Python modules...")
    
    files_to_delete = [
        old_users_db,
        old_katha_db,
        old_admins_json,
        os.path.join(sdl_web_dir, 'user_db.py'),
        os.path.join(sdl_web_dir, 'katha_db.py'),
        os.path.join(sdl_web_dir, 'admin_users.py')
    ]
    
    for f in files_to_delete:
        if os.path.exists(f):
            try:
                if os.path.isdir(f):
                    shutil.rmtree(f)
                else:
                    os.remove(f)
                print(f"  Deleted: {f}")
            except Exception as e:
                print(f"  Error deleting {f}: {e}")
        else:
            print(f"  Not found (already cleaned): {f}")

    print("\nMigration completed successfully!")

if __name__ == '__main__':
    migrate()
