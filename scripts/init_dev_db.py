#!/usr/bin/env python3
"""
Initialize clean development databases with default schema, settings, and optional dev admin.

Usage:
    python scripts/init_dev_db.py
    python scripts/init_dev_db.py --admin-user devadmin --admin-pass devpass123
"""

import argparse
import sys
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from db import common_db, quiz_db, katha_db, articles_db
from scripts.create_admin import create_or_update_admin


def init_all_databases(admin_user=None, admin_pass=None):
    print("==================================================")
    print("   Open-Samsho Database Initialization")
    print("==================================================")

    db_dir = os.path.join(base_dir, 'db')
    os.makedirs(db_dir, exist_ok=True)

    print("1. Initializing Common Database & Default System Settings...")
    common_db.init_db()

    print("2. Initializing Quiz Database...")
    quiz_db.init_db()

    print("3. Initializing Katha Database...")
    katha_db.init_db()

    print("4. Initializing Articles Database...")
    articles_db.init_db()

    if admin_user and admin_pass:
        print(f"5. Provisioning development admin account ('{admin_user}')...")
        create_or_update_admin(admin_user, admin_pass)

    print("==================================================")
    print("[OK] All databases initialized cleanly.")
    print("==================================================")


def main():
    parser = argparse.ArgumentParser(description="Initialize local databases for Open-Samsho.")
    parser.add_argument("--admin-user", default=None, help="Optional admin username to create")
    parser.add_argument("--admin-pass", default=None, help="Optional admin password")
    args = parser.parse_args()

    init_all_databases(args.admin_user, args.admin_pass)


if __name__ == "__main__":
    main()
