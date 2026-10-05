"""Data models and typed structures for outreach automation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class ContactStatus(str, Enum):
    PENDING_RESEARCH = "PENDING_RESEARCH"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    APPROVED = "APPROVED"
    EMAIL_SENT = "EMAIL_SENT"
    LINKEDIN_SENT = "LINKEDIN_SENT"
    WHATSAPP_SENT = "WHATSAPP_SENT"
    OPTED_OUT = "OPTED_OUT"
    REPLIED = "REPLIED"
    HOT_LEAD = "HOT_LEAD"
    FOLLOW_UP_LATER = "FOLLOW_UP_LATER"
    SKIPPED = "SKIPPED"


class DraftStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
    FLAGGED = "FLAGGED"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass
class Contact:
    id: Optional[int] = None
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    job_title: str = ""
    linkedin_url: str = ""
    email: str = ""
    notes: str = ""
    website: str = ""
    status: ContactStatus = ContactStatus.PENDING_RESEARCH
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.first_name or "Contact"


@dataclass
class ResearchDossier:
    id: Optional[int] = None
    contact_id: int = 0
    business_name: str = ""
    website_url: str = ""
    website_title: str = ""
    website_summary: str = ""
    detected_opportunities: List[str] = field(default_factory=list)
    search_snippets: List[str] = field(default_factory=list)
    user_pasted_content: str = ""
    verifiable_facts: List[str] = field(default_factory=list)
    has_strong_hook: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Draft:
    id: Optional[int] = None
    contact_id: int = 0
    hook: str = ""
    linkedin_note: str = ""
    linkedin_message: str = ""
    whatsapp_message: str = ""
    email_subject: str = ""
    email_subject_alt1: str = ""
    email_subject_alt2: str = ""
    email_body: str = ""
    followup_subject: str = ""
    followup_body: str = ""
    source_facts: List[str] = field(default_factory=list)
    status: DraftStatus = DraftStatus.PENDING
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SendLog:
    id: Optional[int] = None
    contact_id: int = 0
    draft_id: Optional[int] = None
    channel: str = "email"
    recipient: str = ""
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    gmail_message_id: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    is_dry_run: bool = True
    status: str = "SIMULATED"
    error_message: Optional[str] = None


@dataclass
class SuppressionEntry:
    id: Optional[int] = None
    email: str = ""
    reason: str = "User requested opt-out"
    opted_out_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
