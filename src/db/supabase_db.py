"""Supabase (PostgreSQL) database backend and repository methods."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

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


def _parse_json_field(val: Any) -> list:
    """Helper to parse JSON fields whether returned as list or string."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []


def safe_contact_status(val: Any) -> ContactStatus:
    """Safely converts string or enum to ContactStatus with fallback."""
    if isinstance(val, ContactStatus):
        return val
    try:
        return ContactStatus(str(val))
    except (ValueError, KeyError, AttributeError):
        return ContactStatus.PENDING_RESEARCH


class SupabaseDatabase:
    """Supabase cloud database repository."""

    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.client: Client = create_client(supabase_url, supabase_key)

    # ------------------ Contacts ------------------

    def insert_contact(self, contact: Contact) -> int:
        now = datetime.utcnow().isoformat()
        clean_email = contact.email.strip().lower() if contact.email else ""
        if not clean_email or "@" not in clean_email:
            identifier = contact.linkedin_url.strip() if contact.linkedin_url else f"{contact.first_name}_{contact.company}"
            clean_email = f"li_{abs(hash(identifier)) % 100000000}@linkedin-lead.local"

        payload = {
            "first_name": contact.first_name.strip(),
            "last_name": contact.last_name.strip(),
            "company": contact.company.strip(),
            "job_title": contact.job_title.strip() if contact.job_title else "",
            "linkedin_url": contact.linkedin_url.strip() if contact.linkedin_url else "",
            "email": clean_email,
            "notes": contact.notes.strip() if contact.notes else "",
            "website": contact.website.strip() if contact.website else "",
            "status": contact.status.value,
            "updated_at": now,
        }

        # Check existing contact by email
        existing = (
            self.client.table("contacts")
            .select("id")
            .eq("email", clean_email)
            .limit(1)
            .execute()
        )
        if existing.data:
            contact_id = existing.data[0]["id"]
            self.client.table("contacts").update(payload).eq("id", contact_id).execute()
            return int(contact_id)

        payload["created_at"] = now
        res = self.client.table("contacts").insert(payload).execute()
        if res.data:
            return int(res.data[0]["id"])
        raise RuntimeError("Failed to insert contact into Supabase.")

    def insert_contacts_batch(self, contacts: List[Contact]) -> int:
        """Batch upserts multiple contacts into Supabase in chunks to avoid single HTTP roundtrips."""
        if not contacts:
            return 0
        now = datetime.utcnow().isoformat()
        payloads = []
        import hashlib

        for idx, contact in enumerate(contacts):
            clean_email = contact.email.strip().lower() if contact.email else ""
            if not clean_email or "@" not in clean_email:
                identifier = f"{contact.linkedin_url}_{contact.first_name}_{contact.company}_{idx}".strip()
                h = hashlib.sha256(identifier.encode()).hexdigest()[:12]
                clean_email = f"li_{h}@linkedin-lead.local"

            payloads.append({
                "first_name": contact.first_name.strip(),
                "last_name": contact.last_name.strip(),
                "company": contact.company.strip(),
                "job_title": contact.job_title.strip() if contact.job_title else "",
                "linkedin_url": contact.linkedin_url.strip() if contact.linkedin_url else "",
                "email": clean_email,
                "notes": contact.notes.strip() if contact.notes else "",
                "website": contact.website.strip() if contact.website else "",
                "status": contact.status.value,
                "created_at": now,
                "updated_at": now,
            })

        # Upsert in chunks of 100 to stay well within PostgREST payload limits
        chunk_size = 100
        total_inserted = 0
        for i in range(0, len(payloads), chunk_size):
            chunk = payloads[i:i + chunk_size]
            res = self.client.table("contacts").upsert(chunk, on_conflict="email").execute()
            if res.data:
                total_inserted += len(res.data)
            else:
                total_inserted += len(chunk)

        return total_inserted

    def get_contact(self, contact_id: int) -> Optional[Contact]:
        res = (
            self.client.table("contacts")
            .select("*")
            .eq("id", contact_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        return Contact(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            company=row["company"],
            job_title=row.get("job_title", ""),
            linkedin_url=row.get("linkedin_url", ""),
            email=row["email"],
            notes=row.get("notes", ""),
            website=row.get("website", ""),
            status=safe_contact_status(row.get("status")),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def get_contact_by_email(self, email: str) -> Optional[Contact]:
        if not email:
            return None
        res = (
            self.client.table("contacts")
            .select("*")
            .ilike("email", email.strip().lower())
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        return Contact(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            company=row["company"],
            job_title=row.get("job_title", ""),
            linkedin_url=row.get("linkedin_url", ""),
            email=row["email"],
            notes=row.get("notes", ""),
            website=row.get("website", ""),
            status=safe_contact_status(row.get("status")),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def list_contacts(self, status: Optional[ContactStatus] = None) -> List[Contact]:
        query = self.client.table("contacts").select("*")
        if status:
            query = query.eq("status", status.value)
        res = query.order("id", desc=False).execute()
        contacts = []
        for row in res.data or []:
            contacts.append(
                Contact(
                    id=row["id"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    company=row["company"],
                    job_title=row.get("job_title", ""),
                    linkedin_url=row.get("linkedin_url", ""),
                    email=row["email"],
                    notes=row.get("notes", ""),
                    website=row.get("website", ""),
                    status=safe_contact_status(row.get("status")),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
            )
        return contacts

    def update_contact_status(self, contact_id: int, status: ContactStatus):
        now = datetime.utcnow().isoformat()
        self.client.table("contacts").update(
            {"status": status.value, "updated_at": now}
        ).eq("id", contact_id).execute()

    def update_contact_notes(self, contact_id: int, notes: str):
        now = datetime.utcnow().isoformat()
        self.client.table("contacts").update(
            {"notes": notes.strip(), "updated_at": now}
        ).eq("id", contact_id).execute()

    # ------------------ Dossiers ------------------

    def save_dossier(self, dossier: ResearchDossier) -> int:
        now = datetime.utcnow().isoformat()
        payload = {
            "contact_id": dossier.contact_id,
            "business_name": dossier.business_name,
            "website_url": dossier.website_url,
            "website_title": dossier.website_title,
            "website_summary": dossier.website_summary,
            "detected_opportunities": dossier.detected_opportunities,
            "search_snippets": dossier.search_snippets,
            "user_pasted_content": dossier.user_pasted_content,
            "verifiable_facts": dossier.verifiable_facts,
            "has_strong_hook": dossier.has_strong_hook,
        }

        existing = (
            self.client.table("research_dossiers")
            .select("id")
            .eq("contact_id", dossier.contact_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            dossier_id = existing.data[0]["id"]
            self.client.table("research_dossiers").update(payload).eq("id", dossier_id).execute()
            return int(dossier_id)

        payload["created_at"] = now
        res = self.client.table("research_dossiers").insert(payload).execute()
        if res.data:
            return int(res.data[0]["id"])
        raise RuntimeError("Failed to insert research dossier into Supabase.")

    def get_dossier(self, contact_id: int) -> Optional[ResearchDossier]:
        res = (
            self.client.table("research_dossiers")
            .select("*")
            .eq("contact_id", contact_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        return ResearchDossier(
            id=row["id"],
            contact_id=row["contact_id"],
            business_name=row.get("business_name", ""),
            website_url=row.get("website_url", ""),
            website_title=row.get("website_title", ""),
            website_summary=row.get("website_summary", ""),
            detected_opportunities=_parse_json_field(row.get("detected_opportunities")),
            search_snippets=_parse_json_field(row.get("search_snippets")),
            user_pasted_content=row.get("user_pasted_content", ""),
            verifiable_facts=_parse_json_field(row.get("verifiable_facts")),
            has_strong_hook=bool(row.get("has_strong_hook", True)),
            created_at=str(row["created_at"]),
        )

    # ------------------ Drafts ------------------

    def save_draft(self, draft: Draft) -> int:
        now = datetime.utcnow().isoformat()
        payload = {
            "contact_id": draft.contact_id,
            "hook": draft.hook,
            "linkedin_note": draft.linkedin_note,
            "linkedin_message": draft.linkedin_message,
            "whatsapp_message": getattr(draft, "whatsapp_message", ""),
            "email_subject": draft.email_subject,
            "email_subject_alt1": draft.email_subject_alt1,
            "email_subject_alt2": draft.email_subject_alt2,
            "email_body": draft.email_body,
            "followup_subject": draft.followup_subject,
            "followup_body": draft.followup_body,
            "source_facts": draft.source_facts,
            "status": draft.status.value,
            "version": draft.version,
            "updated_at": now,
        }

        existing = (
            self.client.table("drafts")
            .select("id")
            .eq("contact_id", draft.contact_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            draft_id = existing.data[0]["id"]
            try:
                self.client.table("drafts").update(payload).eq("id", draft_id).execute()
            except Exception as e:
                if "whatsapp_message" in str(e).lower():
                    payload.pop("whatsapp_message", None)
                    self.client.table("drafts").update(payload).eq("id", draft_id).execute()
                else:
                    raise
            return int(draft_id)

        payload["created_at"] = now
        try:
            res = self.client.table("drafts").insert(payload).execute()
        except Exception as e:
            if "whatsapp_message" in str(e).lower():
                payload.pop("whatsapp_message", None)
                res = self.client.table("drafts").insert(payload).execute()
            else:
                raise

        if res.data:
            return int(res.data[0]["id"])
        raise RuntimeError("Failed to insert draft into Supabase.")

    def get_draft(self, contact_id: int) -> Optional[Draft]:
        res = (
            self.client.table("drafts")
            .select("*")
            .eq("contact_id", contact_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        return Draft(
            id=row["id"],
            contact_id=row["contact_id"],
            hook=row["hook"],
            linkedin_note=row.get("linkedin_note", ""),
            linkedin_message=row.get("linkedin_message", ""),
            whatsapp_message=row.get("whatsapp_message", "") or "",
            email_subject=row["email_subject"],
            email_subject_alt1=row.get("email_subject_alt1", ""),
            email_subject_alt2=row.get("email_subject_alt2", ""),
            email_body=row["email_body"],
            followup_subject=row.get("followup_subject", ""),
            followup_body=row.get("followup_body", ""),
            source_facts=_parse_json_field(row.get("source_facts")),
            status=DraftStatus(row["status"]),
            version=row.get("version", 1),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
    def list_all_drafts(self) -> Dict[int, Draft]:
        """Returns all drafts mapped by contact_id in a single PostgREST query."""
        res = self.client.table("drafts").select("*").execute()
        drafts = {}
        for row in (res.data or []):
            d = Draft(
                id=row["id"],
                contact_id=row["contact_id"],
                hook=row["hook"],
                linkedin_note=row.get("linkedin_note", ""),
                linkedin_message=row.get("linkedin_message", ""),
                whatsapp_message=row.get("whatsapp_message", "") or "",
                email_subject=row["email_subject"],
                email_subject_alt1=row.get("email_subject_alt1", ""),
                email_subject_alt2=row.get("email_subject_alt2", ""),
                email_body=row["email_body"],
                followup_subject=row.get("followup_subject", ""),
                followup_body=row.get("followup_body", ""),
                source_facts=_parse_json_field(row.get("source_facts")),
                status=DraftStatus(row["status"]),
                version=row.get("version", 1),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            drafts[d.contact_id] = d
        return drafts

    def list_drafts(self, status: Optional[DraftStatus] = None) -> List[Draft]:
        """Returns all drafts matching status, ordered by id ASC."""
        query = self.client.table("drafts").select("*")
        if status:
            query = query.eq("status", status.value)
        res = query.order("id").execute()
        drafts = []
        for row in (res.data or []):
            drafts.append(
                Draft(
                    id=row["id"],
                    contact_id=row["contact_id"],
                    hook=row["hook"],
                    linkedin_note=row.get("linkedin_note", ""),
                    linkedin_message=row.get("linkedin_message", ""),
                    whatsapp_message=row.get("whatsapp_message", "") or "",
                    email_subject=row["email_subject"],
                    email_subject_alt1=row.get("email_subject_alt1", ""),
                    email_subject_alt2=row.get("email_subject_alt2", ""),
                    email_body=row["email_body"],
                    followup_subject=row.get("followup_subject", ""),
                    followup_body=row.get("followup_body", ""),
                    source_facts=_parse_json_field(row.get("source_facts")),
                    status=DraftStatus(row["status"]),
                    version=row.get("version", 1),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
            )
        return drafts

    def list_all_dossiers(self) -> Dict[int, ResearchDossier]:
        """Returns all dossiers mapped by contact_id in a single PostgREST query."""
        res = self.client.table("research_dossiers").select("*").execute()
        dossiers = {}
        for row in (res.data or []):
            dos = ResearchDossier(
                id=row["id"],
                contact_id=row["contact_id"],
                business_name=row["business_name"],
                website_url=row.get("website_url", ""),
                website_title=row.get("website_title", ""),
                website_summary=row.get("website_summary", ""),
                detected_opportunities=_parse_json_field(row.get("detected_opportunities")),
                search_snippets=_parse_json_field(row.get("search_snippets")),
                user_pasted_content=row.get("user_pasted_content", ""),
                verifiable_facts=_parse_json_field(row.get("verifiable_facts")),
                has_strong_hook=row.get("has_strong_hook", True),
                created_at=str(row["created_at"]),
            )
            dossiers[dos.contact_id] = dos
        return dossiers

    def update_draft_status(self, draft_id: int, status: DraftStatus):
        now = datetime.utcnow().isoformat()
        self.client.table("drafts").update(
            {"status": status.value, "updated_at": now}
        ).eq("id", draft_id).execute()

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
        now = datetime.utcnow().isoformat()
        payload = {
            "hook": hook,
            "email_subject": email_subject,
            "email_body": email_body,
            "linkedin_note": linkedin_note,
            "linkedin_message": linkedin_message,
            "whatsapp_message": whatsapp_message,
            "status": status.value,
            "updated_at": now,
        }
        try:
            self.client.table("drafts").update(payload).eq("id", draft_id).execute()
        except Exception as e:
            if "whatsapp_message" in str(e).lower():
                payload.pop("whatsapp_message", None)
                self.client.table("drafts").update(payload).eq("id", draft_id).execute()
            else:
                raise

    # ------------------ Suppression List ------------------

    def add_to_suppression(self, email: str, reason: str = "Opt-out requested"):
        now = datetime.utcnow().isoformat()
        clean_email = email.strip().lower()

        existing = (
            self.client.table("suppression_list")
            .select("id")
            .eq("email", clean_email)
            .limit(1)
            .execute()
        )
        if not existing.data:
            self.client.table("suppression_list").insert(
                {"email": clean_email, "reason": reason, "opted_out_at": now}
            ).execute()

        # Update contact status to OPTED_OUT
        self.client.table("contacts").update(
            {"status": ContactStatus.OPTED_OUT.value, "updated_at": now}
        ).eq("email", clean_email).execute()

    def is_suppressed(self, email: str) -> bool:
        clean_email = email.strip().lower()
        res = (
            self.client.table("suppression_list")
            .select("id")
            .eq("email", clean_email)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def list_suppressed(self) -> List[SuppressionEntry]:
        res = (
            self.client.table("suppression_list")
            .select("*")
            .order("opted_out_at", desc=True)
            .execute()
        )
        return [
            SuppressionEntry(
                id=row["id"],
                email=row["email"],
                reason=row.get("reason", ""),
                opted_out_at=str(row["opted_out_at"]),
            )
            for row in res.data or []
        ]

    # ------------------ Send Logs & Rate Limits ------------------

    def has_already_sent_email(self, email: str) -> bool:
        clean_email = email.strip().lower()
        res = (
            self.client.table("send_logs")
            .select("id")
            .eq("recipient", clean_email)
            .eq("channel", "email")
            .in_("status", ["SENT", "SIMULATED"])
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def log_send(self, log: SendLog) -> int:
        now = datetime.utcnow().isoformat()
        payload = {
            "contact_id": log.contact_id,
            "draft_id": log.draft_id,
            "channel": log.channel,
            "recipient": log.recipient.strip().lower(),
            "sent_at": now,
            "gmail_message_id": log.gmail_message_id,
            "gmail_thread_id": log.gmail_thread_id,
            "is_dry_run": bool(log.is_dry_run),
            "status": log.status,
            "error_message": log.error_message,
        }
        res = self.client.table("send_logs").insert(payload).execute()
        log_id = int(res.data[0]["id"]) if res.data else 0

        # Increment daily send counter if live or simulated
        if log.status in ("SENT", "SIMULATED"):
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            counter_res = (
                self.client.table("daily_send_counter")
                .select("count")
                .eq("send_date", today_str)
                .limit(1)
                .execute()
            )
            if counter_res.data:
                curr_count = counter_res.data[0]["count"]
                self.client.table("daily_send_counter").update(
                    {"count": curr_count + 1}
                ).eq("send_date", today_str).execute()
            else:
                self.client.table("daily_send_counter").insert(
                    {"send_date": today_str, "count": 1}
                ).execute()

        return log_id

    def get_today_sent_count(self) -> int:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        res = (
            self.client.table("daily_send_counter")
            .select("count")
            .eq("send_date", today_str)
            .limit(1)
            .execute()
        )
        if res.data:
            return int(res.data[0]["count"])
        return 0

    def list_send_logs(self, limit: int = 50) -> List[SendLog]:
        res = (
            self.client.table("send_logs")
            .select("*")
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            SendLog(
                id=row["id"],
                contact_id=row["contact_id"],
                draft_id=row.get("draft_id"),
                channel=row["channel"],
                recipient=row["recipient"],
                sent_at=str(row["sent_at"]),
                gmail_message_id=row.get("gmail_message_id"),
                gmail_thread_id=row.get("gmail_thread_id"),
                is_dry_run=bool(row["is_dry_run"]),
                status=row["status"],
                error_message=row.get("error_message"),
            )
            for row in res.data or []
        ]
