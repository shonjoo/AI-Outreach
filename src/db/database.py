"""Database management and repository methods (SQLite and Supabase adapter)."""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from src.db.models import (
    Contact,
    ContactStatus,
    Draft,
    DraftStatus,
    ResearchDossier,
    SendLog,
    SuppressionEntry,
)

logger = logging.getLogger(__name__)


class Database:
    """
    Unified database repository.
    Acts as a facade: delegates to SupabaseDatabase when configured,
    or falls back seamlessly to local SQLite storage.
    """

    def __init__(
        self,
        db_path: str = "outreach.db",
        config: Optional[Any] = None,
        force_sqlite: bool = False,
    ):
        self.db_path = db_path
        self._backend = None

        # Check if Supabase should be activated
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = (
            os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
        )
        db_backend = os.getenv("DB_BACKEND", "auto").strip().lower()

        if config and hasattr(config, "database"):
            if config.database.supabase_url:
                supabase_url = config.database.supabase_url
            if config.database.supabase_key or config.database.supabase_service_role_key:
                supabase_key = config.database.supabase_key or config.database.supabase_service_role_key
            if config.database.backend:
                db_backend = config.database.backend.strip().lower()

        use_supabase = (
            not force_sqlite
            and db_backend != "sqlite"
            and bool(supabase_url and supabase_key)
        )

        self.supabase_schema_pending = False
        if use_supabase:
            try:
                from src.db.supabase_db import SupabaseDatabase

                sb = SupabaseDatabase(supabase_url, supabase_key)
                # Verify that tables exist in Supabase schema cache
                sb.client.table("contacts").select("id").limit(1).execute()
                self._backend = sb
                logger.info(f"Connected to Supabase database backend: {supabase_url}")
            except Exception as e:
                err_str = str(e)
                if "PGRST205" in err_str or "Could not find the table" in err_str:
                    logger.warning(
                        "Supabase connected successfully, but 'contacts' table is not yet created in Supabase schema cache. "
                        "Please run 'supabase_schema.sql' in your Supabase Dashboard SQL Editor. "
                        "Falling back to local SQLite in the meantime."
                    )
                    self.supabase_schema_pending = True
                else:
                    logger.warning(f"Failed to initialize Supabase ({e}). Falling back to SQLite.")
                self._backend = None

        if self._backend is None:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.init_db()


    @property
    def is_supabase(self) -> bool:
        """Returns True if currently connected to Supabase."""
        return self._backend is not None

    @property
    def backend_name(self) -> str:
        """Returns 'supabase' or 'sqlite'."""
        return "supabase" if self.is_supabase else "sqlite"

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    company TEXT NOT NULL,
                    job_title TEXT,
                    linkedin_url TEXT,
                    email TEXT UNIQUE NOT NULL,
                    notes TEXT,
                    website TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING_RESEARCH',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_dossiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL UNIQUE,
                    business_name TEXT,
                    website_url TEXT,
                    website_title TEXT,
                    website_summary TEXT,
                    detected_opportunities TEXT,
                    search_snippets TEXT,
                    user_pasted_content TEXT,
                    verifiable_facts TEXT,
                    has_strong_hook INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL UNIQUE,
                    hook TEXT NOT NULL,
                    linkedin_note TEXT,
                    linkedin_message TEXT,
                    whatsapp_message TEXT,
                    email_subject TEXT NOT NULL,
                    email_subject_alt1 TEXT,
                    email_subject_alt2 TEXT,
                    email_body TEXT NOT NULL,
                    followup_subject TEXT,
                    followup_body TEXT,
                    source_facts TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS send_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    draft_id INTEGER,
                    channel TEXT NOT NULL DEFAULT 'email',
                    recipient TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    gmail_message_id TEXT,
                    gmail_thread_id TEXT,
                    is_dry_run INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS suppression_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    reason TEXT,
                    opted_out_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS daily_send_counter (
                    send_date TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            # Safe migration for existing SQLite files
            try:
                conn.execute("ALTER TABLE drafts ADD COLUMN whatsapp_message TEXT;")
            except Exception:
                pass

    # ------------------ Contacts ------------------

    def insert_contact(self, contact: Contact) -> int:
        if self._backend:
            return self._backend.insert_contact(contact)

        now = datetime.utcnow().isoformat()
        clean_email = contact.email.strip().lower() if contact.email else ""
        if not clean_email or "@" not in clean_email:
            identifier = contact.linkedin_url.strip() if contact.linkedin_url else f"{contact.first_name}_{contact.company}"
            clean_email = f"li_{abs(hash(identifier)) % 100000000}@linkedin-lead.local"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO contacts 
                (first_name, last_name, company, job_title, linkedin_url, email, notes, website, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    company=excluded.company,
                    job_title=excluded.job_title,
                    linkedin_url=excluded.linkedin_url,
                    notes=excluded.notes,
                    website=excluded.website,
                    updated_at=excluded.updated_at
                RETURNING id;
                """,
                (
                    contact.first_name.strip(),
                    contact.last_name.strip(),
                    contact.company.strip(),
                    contact.job_title.strip() if contact.job_title else "",
                    contact.linkedin_url.strip() if contact.linkedin_url else "",
                    clean_email,
                    contact.notes.strip() if contact.notes else "",
                    contact.website.strip() if contact.website else "",
                    contact.status.value,
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            return row["id"] if row else cursor.lastrowid

    def get_contact(self, contact_id: int) -> Optional[Contact]:
        if self._backend:
            return self._backend.get_contact(contact_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
            row = cursor.fetchone()
            if row:
                return Contact(
                    id=row["id"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    company=row["company"],
                    job_title=row["job_title"],
                    linkedin_url=row["linkedin_url"],
                    email=row["email"],
                    notes=row["notes"],
                    website=row["website"],
                    status=ContactStatus(row["status"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        return None

    def list_contacts(self, status: Optional[ContactStatus] = None) -> List[Contact]:
        if self._backend:
            return self._backend.list_contacts(status)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM contacts WHERE status = ? ORDER BY id ASC", (status.value,))
            else:
                cursor.execute("SELECT * FROM contacts ORDER BY id ASC")
            rows = cursor.fetchall()
            return [
                Contact(
                    id=row["id"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    company=row["company"],
                    job_title=row["job_title"],
                    linkedin_url=row["linkedin_url"],
                    email=row["email"],
                    notes=row["notes"],
                    website=row["website"],
                    status=ContactStatus(row["status"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def update_contact_status(self, contact_id: int, status: ContactStatus):
        if self._backend:
            return self._backend.update_contact_status(contact_id, status)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE contacts SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now, contact_id),
            )

    def update_contact_notes(self, contact_id: int, notes: str):
        if self._backend:
            return self._backend.update_contact_notes(contact_id, notes)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE contacts SET notes = ?, updated_at = ? WHERE id = ?",
                (notes.strip(), now, contact_id),
            )

    # ------------------ Dossiers ------------------

    def save_dossier(self, dossier: ResearchDossier) -> int:
        if self._backend:
            return self._backend.save_dossier(dossier)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO research_dossiers
                (contact_id, business_name, website_url, website_title, website_summary,
                 detected_opportunities, search_snippets, user_pasted_content,
                 verifiable_facts, has_strong_hook, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contact_id) DO UPDATE SET
                    business_name=excluded.business_name,
                    website_url=excluded.website_url,
                    website_title=excluded.website_title,
                    website_summary=excluded.website_summary,
                    detected_opportunities=excluded.detected_opportunities,
                    search_snippets=excluded.search_snippets,
                    user_pasted_content=excluded.user_pasted_content,
                    verifiable_facts=excluded.verifiable_facts,
                    has_strong_hook=excluded.has_strong_hook
                RETURNING id;
                """,
                (
                    dossier.contact_id,
                    dossier.business_name,
                    dossier.website_url,
                    dossier.website_title,
                    dossier.website_summary,
                    json.dumps(dossier.detected_opportunities),
                    json.dumps(dossier.search_snippets),
                    dossier.user_pasted_content,
                    json.dumps(dossier.verifiable_facts),
                    1 if dossier.has_strong_hook else 0,
                    now,
                ),
            )
            row = cursor.fetchone()
            return row["id"] if row else cursor.lastrowid

    def get_dossier(self, contact_id: int) -> Optional[ResearchDossier]:
        if self._backend:
            return self._backend.get_dossier(contact_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_dossiers WHERE contact_id = ?", (contact_id,))
            row = cursor.fetchone()
            if row:
                return ResearchDossier(
                    id=row["id"],
                    contact_id=row["contact_id"],
                    business_name=row["business_name"],
                    website_url=row["website_url"],
                    website_title=row["website_title"],
                    website_summary=row["website_summary"],
                    detected_opportunities=json.loads(row["detected_opportunities"] or "[]"),
                    search_snippets=json.loads(row["search_snippets"] or "[]"),
                    user_pasted_content=row["user_pasted_content"] or "",
                    verifiable_facts=json.loads(row["verifiable_facts"] or "[]"),
                    has_strong_hook=bool(row["has_strong_hook"]),
                    created_at=row["created_at"],
                )
        return None

    # ------------------ Drafts ------------------

    def save_draft(self, draft: Draft) -> int:
        if self._backend:
            return self._backend.save_draft(draft)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO drafts
                (contact_id, hook, linkedin_note, linkedin_message, whatsapp_message, email_subject,
                 email_subject_alt1, email_subject_alt2, email_body, followup_subject,
                 followup_body, source_facts, status, version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contact_id) DO UPDATE SET
                    hook=excluded.hook,
                    linkedin_note=excluded.linkedin_note,
                    linkedin_message=excluded.linkedin_message,
                    whatsapp_message=excluded.whatsapp_message,
                    email_subject=excluded.email_subject,
                    email_subject_alt1=excluded.email_subject_alt1,
                    email_subject_alt2=excluded.email_subject_alt2,
                    email_body=excluded.email_body,
                    followup_subject=excluded.followup_subject,
                    followup_body=excluded.followup_body,
                    source_facts=excluded.source_facts,
                    status=excluded.status,
                    version=drafts.version + 1,
                    updated_at=excluded.updated_at
                RETURNING id;
                """,
                (
                    draft.contact_id,
                    draft.hook,
                    draft.linkedin_note,
                    draft.linkedin_message,
                    draft.whatsapp_message,
                    draft.email_subject,
                    draft.email_subject_alt1,
                    draft.email_subject_alt2,
                    draft.email_body,
                    draft.followup_subject,
                    draft.followup_body,
                    json.dumps(draft.source_facts),
                    draft.status.value,
                    draft.version,
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            return row["id"] if row else cursor.lastrowid

    def get_draft(self, contact_id: int) -> Optional[Draft]:
        if self._backend:
            return self._backend.get_draft(contact_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM drafts WHERE contact_id = ?", (contact_id,))
            row = cursor.fetchone()
            if row:
                wa_msg = row["whatsapp_message"] if "whatsapp_message" in row.keys() else ""
                return Draft(
                    id=row["id"],
                    contact_id=row["contact_id"],
                    hook=row["hook"],
                    linkedin_note=row["linkedin_note"] or "",
                    linkedin_message=row["linkedin_message"] or "",
                    whatsapp_message=wa_msg or "",
                    email_subject=row["email_subject"] or "",
                    email_subject_alt1=row["email_subject_alt1"] or "",
                    email_subject_alt2=row["email_subject_alt2"] or "",
                    email_body=row["email_body"] or "",
                    followup_subject=row["followup_subject"] or "",
                    followup_body=row["followup_body"] or "",
                    source_facts=json.loads(row["source_facts"] or "[]"),
                    status=DraftStatus(row["status"]),
                    version=row["version"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        return None

    def update_draft_status(self, draft_id: int, status: DraftStatus):
        if self._backend:
            return self._backend.update_draft_status(draft_id, status)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE drafts SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now, draft_id),
            )

    def update_draft_content(
        self,
        draft_id: int,
        hook: str,
        email_subject: str,
        email_body: str,
        linkedin_note: str,
        linkedin_message: str,
        status: DraftStatus = DraftStatus.EDITED,
        whatsapp_message: str = "",
    ):
        if self._backend:
            return self._backend.update_draft_content(
                draft_id, hook, email_subject, email_body, linkedin_note, linkedin_message, status, whatsapp_message
            )

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE drafts 
                SET hook = ?, email_subject = ?, email_body = ?, 
                    linkedin_note = ?, linkedin_message = ?, whatsapp_message = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    hook,
                    email_subject,
                    email_body,
                    linkedin_note,
                    linkedin_message,
                    whatsapp_message,
                    status.value,
                    now,
                    draft_id,
                ),
            )

    # ------------------ Suppression List ------------------

    def add_to_suppression(self, email: str, reason: str = "Opt-out requested"):
        if self._backend:
            return self._backend.add_to_suppression(email, reason)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO suppression_list (email, reason, opted_out_at)
                VALUES (?, ?, ?)
                """,
                (email.strip().lower(), reason, now),
            )
            conn.execute(
                "UPDATE contacts SET status = ? WHERE email = ?",
                (ContactStatus.OPTED_OUT.value, email.strip().lower()),
            )

    def is_suppressed(self, email: str) -> bool:
        if self._backend:
            return self._backend.is_suppressed(email)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM suppression_list WHERE email = ?",
                (email.strip().lower(),),
            )
            return cursor.fetchone() is not None

    def list_suppressed(self) -> List[SuppressionEntry]:
        if self._backend:
            return self._backend.list_suppressed()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM suppression_list ORDER BY opted_out_at DESC")
            return [
                SuppressionEntry(
                    id=row["id"],
                    email=row["email"],
                    reason=row["reason"],
                    opted_out_at=row["opted_out_at"],
                )
                for row in cursor.fetchall()
            ]

    # ------------------ Send Logs & Duplicate Protection ------------------

    def has_already_sent_email(self, email: str) -> bool:
        if self._backend:
            return self._backend.has_already_sent_email(email)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM send_logs 
                WHERE recipient = ? AND channel = 'email' AND status IN ('SENT', 'SIMULATED')
                """,
                (email.strip().lower(),),
            )
            return cursor.fetchone() is not None

    def log_send(self, log: SendLog) -> int:
        if self._backend:
            return self._backend.log_send(log)

        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO send_logs 
                (contact_id, draft_id, channel, recipient, sent_at, 
                 gmail_message_id, gmail_thread_id, is_dry_run, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.contact_id,
                    log.draft_id,
                    log.channel,
                    log.recipient.strip().lower(),
                    now,
                    log.gmail_message_id,
                    log.gmail_thread_id,
                    1 if log.is_dry_run else 0,
                    log.status,
                    log.error_message,
                ),
            )
            log_id = cursor.lastrowid
            # Also record daily count if SENT
            if log.status in ("SENT", "SIMULATED"):
                today_str = datetime.utcnow().strftime("%Y-%m-%d")
                conn.execute(
                    """
                    INSERT INTO daily_send_counter (send_date, count)
                    VALUES (?, 1)
                    ON CONFLICT(send_date) DO UPDATE SET count = count + 1
                    """,
                    (today_str,),
                )
            return log_id

    def get_today_sent_count(self) -> int:
        if self._backend:
            return self._backend.get_today_sent_count()

        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT count FROM daily_send_counter WHERE send_date = ?",
                (today_str,),
            )
            row = cursor.fetchone()
            return row["count"] if row else 0

    def list_send_logs(self, limit: int = 50) -> List[SendLog]:
        if self._backend:
            return self._backend.list_send_logs(limit)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM send_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [
                SendLog(
                    id=row["id"],
                    contact_id=row["contact_id"],
                    draft_id=row["draft_id"],
                    channel=row["channel"],
                    recipient=row["recipient"],
                    sent_at=row["sent_at"],
                    gmail_message_id=row["gmail_message_id"],
                    gmail_thread_id=row["gmail_thread_id"],
                    is_dry_run=bool(row["is_dry_run"]),
                    status=row["status"],
                    error_message=row["error_message"],
                )
                for row in cursor.fetchall()
            ]
