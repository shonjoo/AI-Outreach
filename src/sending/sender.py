"""Email dispatcher with rate limits, jitter delay, duplicate protection, and logging."""

import logging
import random
import time
from typing import Dict, Optional, Tuple

from src.config import AppConfig
from src.db.database import Database
from src.db.models import Contact, ContactStatus, Draft, DraftStatus, SendLog
from src.sending.gmail_client import GmailClient
from src.sending.suppression import SuppressionManager

logger = logging.getLogger(__name__)


class OutreachSender:
    def __init__(
        self,
        config: AppConfig,
        db: Database,
        gmail_client: Optional[GmailClient] = None,
        suppression_manager: Optional[SuppressionManager] = None,
    ):
        self.config = config
        self.db = db
        self.gmail = gmail_client or GmailClient(config)
        self.suppression = suppression_manager or SuppressionManager(db)

    def send_approved_email(
        self,
        contact: Contact,
        draft: Draft,
        force_dry_run: Optional[bool] = None,
        respect_delay: bool = True,
    ) -> Tuple[bool, str]:
        """
        Sends an approved draft email to the contact with all safety checks.
        Returns (success: bool, status_message: str).
        """
        email = contact.email.strip().lower()
        is_dry_run = self.config.dry_run if force_dry_run is None else force_dry_run

        # 0. Check if draft is flagged
        if draft.status == DraftStatus.FLAGGED:
            msg = f"Cannot send: Draft for {contact.company} is FLAGGED. Manual edit and approval required."
            logger.warning(msg)
            return False, msg

        # 1. Check suppression list
        if self.suppression.is_suppressed(email):
            msg = f"Cannot send to {email}: Address is on the suppression/opt-out list."
            logger.warning(msg)
            return False, msg

        # 2. Check duplicate protection
        if self.db.has_already_sent_email(email):
            msg = f"Duplicate protection: An email has already been sent to {email}."
            logger.warning(msg)
            return False, msg

        # 3. Check daily rate limit
        sent_today = self.db.get_today_sent_count()
        limit = self.config.limits.emails_per_day
        if sent_today >= limit:
            msg = f"Daily limit reached: {sent_today}/{limit} emails sent today. Try again tomorrow."
            logger.warning(msg)
            return False, msg

        # 4. Prepare email body with compliant opt-out footer
        final_body = self.suppression.append_opt_out_footer(
            body=draft.email_body,
            sender_name=self.config.sender.name,
            sender_email=self.config.sender.email,
        )

        subject = draft.email_subject or f"Connecting with {contact.company}"

        # 5. Dispatch email via Gmail API / Dry-Run simulator
        success, msg_id, thread_id, err = self.gmail.send_email(
            to_email=email,
            subject=subject,
            body_text=final_body,
            dry_run=is_dry_run,
        )

        # 6. Log the send event in SQLite
        log_status = "SIMULATED" if is_dry_run else ("SENT" if success else "FAILED")
        self.db.log_send(
            SendLog(
                contact_id=contact.id or 0,
                draft_id=draft.id,
                channel="email",
                recipient=email,
                gmail_message_id=msg_id,
                gmail_thread_id=thread_id,
                is_dry_run=is_dry_run,
                status=log_status,
                error_message=err,
            )
        )

        if not success:
            return False, f"Send failed: {err}"

        # 7. Update contact status
        self.db.update_contact_status(contact.id, ContactStatus.EMAIL_SENT)

        # 8. Organic delay between sends (if not in immediate dry-run mode or if requested)
        if respect_delay and not is_dry_run:
            delay_sec = random.randint(self.config.limits.min_delay, self.config.limits.max_delay)
            logger.info(f"Organic rate-limit pause: waiting {delay_sec} seconds before next send...")
            time.sleep(delay_sec)

        status_prefix = "[DRY-RUN SIMULATED]" if is_dry_run else "[LIVE SENT]"
        return True, f"{status_prefix} Email queued and sent to {email} (Message ID: {msg_id})"
