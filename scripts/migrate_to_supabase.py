#!/usr/bin/env python3
"""
Migration tool to transfer data from SQLite (outreach.db) to Supabase cloud.

Usage:
    python scripts/migrate_to_supabase.py [--sqlite-path outreach.db]
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.db.database import Database
from src.db.supabase_db import SupabaseDatabase


def migrate(sqlite_path: str = "outreach.db"):
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) must be set in .env")
        sys.exit(1)

    print(f"Connecting to SQLite: {sqlite_path}")
    sqlite_db = Database(db_path=sqlite_path, force_sqlite=True)

    print(f"Connecting to Supabase: {supabase_url}")
    supabase_db = SupabaseDatabase(supabase_url=supabase_url, supabase_key=supabase_key)

    # 1. Contacts
    contacts = sqlite_db.list_contacts()
    print(f"\n[1/5] Migrating {len(contacts)} contacts...")
    old_to_new_contact_ids = {}
    for c in contacts:
        old_id = c.id
        new_id = supabase_db.insert_contact(c)
        if old_id:
            old_to_new_contact_ids[old_id] = new_id
    print(f"      Migrated {len(old_to_new_contact_ids)} contacts successfully.")

    # 2. Dossiers
    print("\n[2/5] Migrating research dossiers...")
    dossier_count = 0
    for old_id, new_id in old_to_new_contact_ids.items():
        dossier = sqlite_db.get_dossier(old_id)
        if dossier:
            dossier.contact_id = new_id
            supabase_db.save_dossier(dossier)
            dossier_count += 1
    print(f"      Migrated {dossier_count} dossiers successfully.")

    # 3. Drafts
    print("\n[3/5] Migrating drafts...")
    draft_count = 0
    for old_id, new_id in old_to_new_contact_ids.items():
        draft = sqlite_db.get_draft(old_id)
        if draft:
            draft.contact_id = new_id
            supabase_db.save_draft(draft)
            draft_count += 1
    print(f"      Migrated {draft_count} drafts successfully.")

    # 4. Suppression List
    suppressed = sqlite_db.list_suppressed()
    print(f"\n[4/5] Migrating {len(suppressed)} suppression entries...")
    for s in suppressed:
        supabase_db.add_to_suppression(s.email, s.reason)
    print(f"      Migrated {len(suppressed)} suppression entries.")

    # 5. Send Logs
    logs = sqlite_db.list_send_logs(limit=1000)
    print(f"\n[5/5] Migrating {len(logs)} send logs...")
    migrated_logs = 0
    for l in logs:
        if l.contact_id in old_to_new_contact_ids:
            l.contact_id = old_to_new_contact_ids[l.contact_id]
            supabase_db.log_send(l)
            migrated_logs += 1
    print(f"      Migrated {migrated_logs} send logs.")

    print("\n========================================================")
    print("Migration to Supabase completed successfully!")
    print("========================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite outreach database to Supabase.")
    parser.add_argument("--sqlite-path", default="outreach.db", help="Path to SQLite database file")
    args = parser.parse_args()
    migrate(args.sqlite_path)
