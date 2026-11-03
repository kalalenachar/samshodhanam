#!/usr/bin/env python3
"""
Create or update an administrative user in Open-Samsho.

Usage:
    python scripts/create_admin.py --username admin --password secretpassword
"""

import argparse
import sys
import os
import json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from db import common_db
from time_utils import get_ist_now

ALL_PERMISSIONS = [
    "PERM_DOWNLOAD_BOOKS",
    "PERM_UPLOAD_EXCEL",
    "PERM_EDIT_BOOK_NAME",
    "PERM_EDIT_TAGS",
    "PERM_EDIT_SUB_BOOK",
    "PERM_EDIT_LINK",
    "PERM_ADD_BOOK",
    "PERM_DELETE_BOOK",
    "PERM_EDIT_OCR",
    "PERM_VIEW_FEEDBACK",
    "PERM_MANAGE_FEEDBACK",
    "PERM_MANAGE_USERS",
    "PERM_MANAGE_QUIZ",
    "PERM_MANAGE_PLAY",
    "PERM_MANAGE_KATHA",
    "PERM_MANAGE_ARTICLES",
    "PERM_MANAGE_AI"
]


def create_or_update_admin(username, password):
    common_db.init_db()
    conn = common_db.get_db()
    try:
        pw_hash = common_db.hash_password(password)
        perms_json = json.dumps(ALL_PERMISSIONS)
        now_str = get_ist_now().isoformat()
        username_clean = username.strip().upper()

        cursor = conn.cursor()
        cursor.execute("SELECT username FROM admins WHERE UPPER(username) = ?", (username_clean,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE admins SET password_hash = ?, permissions_json = ? WHERE UPPER(username) = ?",
                (pw_hash, perms_json, username_clean)
            )
            conn.commit()
            print(f"[OK] Updated existing admin '{username_clean}'.")
        else:
            cursor.execute(
                "INSERT INTO admins (username, password_hash, permissions_json, created_at, last_login) VALUES (?, ?, ?, ?, ?)",
                (username_clean, pw_hash, perms_json, now_str, None)
            )
            conn.commit()
            print(f"[OK] Created new admin '{username_clean}' with full permissions.")
        return True
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Create or update an Open-Samsho admin account.")
    parser.add_argument("--username", "-u", default="admin", help="Admin username (default: admin)")
    parser.add_argument("--password", "-p", required=True, help="Admin password")
    args = parser.parse_args()

    create_or_update_admin(args.username, args.password)


if __name__ == "__main__":
    main()
