"""Abstract Base Database Interface defining the storage contract."""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.db.models import (
    Contact,
    ContactStatus,
    Draft,
    DraftStatus,
    ResearchDossier,
    SendLog,
    SuppressionEntry,
)


class BaseDatabase(ABC):
    """Abstract interface for outreach persistence backends."""

    # ------------------ Contacts ------------------

    @abstractmethod
    def insert_contact(self, contact: Contact) -> int:
        """Insert or upsert a contact by email and return contact ID."""
        pass

    @abstractmethod
    def get_contact(self, contact_id: int) -> Optional[Contact]:
        """Fetch a single contact by primary ID."""
        pass

    @abstractmethod
    def list_contacts(self, status: Optional[ContactStatus] = None) -> List[Contact]:
        """List contacts, optionally filtered by status."""
        pass

    @abstractmethod
    def update_contact_status(self, contact_id: int, status: ContactStatus):
        """Update a contact's lifecycle status."""
        pass

    @abstractmethod
    def update_contact_notes(self, contact_id: int, notes: str):
        """Update a contact's research notes."""
        pass

    # ------------------ Dossiers ------------------

    @abstractmethod
    def save_dossier(self, dossier: ResearchDossier) -> int:
        """Insert or update a research dossier for a contact."""
        pass

    @abstractmethod
    def get_dossier(self, contact_id: int) -> Optional[ResearchDossier]:
        """Fetch the research dossier for a contact."""
        pass

    # ------------------ Drafts ------------------

    @abstractmethod
    def save_draft(self, draft: Draft) -> int:
        """Insert or update an outreach message draft."""
        pass

    @abstractmethod
    def get_draft(self, contact_id: int) -> Optional[Draft]:
        """Fetch the generated draft for a contact."""
        pass

    @abstractmethod
    def update_draft_status(self, draft_id: int, status: DraftStatus):
        """Update draft status (e.g. APPROVED, REJECTED, FLAGGED)."""
        pass

    @abstractmethod
    def update_draft_content(
        self,
        draft_id: int,
        hook: str,
        email_subject: str,
        email_body: str,
        linkedin_note: str,
        linkedin_message: str,
        status: DraftStatus = DraftStatus.EDITED,
    ):
        """Update edited draft content."""
        pass

    # ------------------ Suppression List ------------------

    @abstractmethod
    def add_to_suppression(self, email: str, reason: str = "Opt-out requested"):
        """Add an email address to the opt-out / suppression list."""
        pass

    @abstractmethod
    def is_suppressed(self, email: str) -> bool:
        """Check if an email address is suppressed."""
        pass

    @abstractmethod
    def list_suppressed(self) -> List[SuppressionEntry]:
        """List all suppressed email addresses."""
        pass

    # ------------------ Send Logs & Rate Limits ------------------

    @abstractmethod
    def has_already_sent_email(self, email: str) -> bool:
        """Check if an email has already been sent to this address."""
        pass

    @abstractmethod
    def log_send(self, log: SendLog) -> int:
        """Record an outreach dispatch in the send log and update daily count."""
        pass

    @abstractmethod
    def get_today_sent_count(self) -> int:
        """Get the number of messages sent today (UTC)."""
        pass

    @abstractmethod
    def list_send_logs(self, limit: int = 50) -> List[SendLog]:
        """List recent dispatch activity."""
        pass
