"""Reply detection engine that checks Gmail threads and cancels follow-ups."""

import logging
from typing import List

from src.db.database import Database
from src.db.models import ContactStatus
from src.sending.gmail_client import GmailClient

logger = logging.getLogger(__name__)


class ReplyTracker:
    def __init__(self, db: Database, gmail_client: GmailClient):
        self.db = db
        self.gmail = gmail_client

    def check_all_active_threads(self) -> List[str]:
        """
        Scans all recent sent logs and updates any contacts who have replied.
        Returns list of email addresses that replied.
        """
        replied_emails = []
        logs = self.db.list_send_logs(limit=100)

        for log in logs:
            if not log.gmail_thread_id or log.is_dry_run:
                continue

            has_reply = self.gmail.check_for_replies(log.gmail_thread_id, log.recipient)
            if has_reply:
                contact = self.db.get_contact(log.contact_id)
                if contact and contact.status != ContactStatus.REPLIED:
                    logger.info(f"Reply detected from {log.recipient}! Updating status to REPLIED.")
                    self.db.update_contact_status(contact.id, ContactStatus.REPLIED)
                    replied_emails.append(log.recipient)

        return replied_emails
