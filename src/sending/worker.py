"""Background dispatch queue worker for autonomous, paced outreach delivery."""

import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from src.config import AppConfig
from src.db.database import Database
from src.db.models import ContactStatus, Draft, DraftStatus, SendLog
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager

logger = logging.getLogger(__name__)


class DispatchWorker:
    """
    Background worker that polls the database for drafts marked APPROVED,
    evaluates daily limits and suppression lists, applies randomized delays,
    dispatches messages via OutreachSender, and updates draft/contact statuses.
    """

    def __init__(
        self,
        config: AppConfig,
        db: Database,
        sender: Optional[OutreachSender] = None,
        suppression_manager: Optional[SuppressionManager] = None,
        poll_interval: float = 5.0,
        min_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        force_dry_run: Optional[bool] = None,
    ):
        self.config = config
        self.db = db
        self.sender = sender or OutreachSender(config, db)
        self.suppression = suppression_manager or SuppressionManager(db)
        self.poll_interval = poll_interval

        # Delay configuration (in seconds)
        # Allows overriding default 90-240s with custom intervals (e.g. 0s during tests)
        self.min_delay = min_delay if min_delay is not None else float(config.limits.min_delay)
        self.max_delay = max_delay if max_delay is not None else float(config.limits.max_delay)
        self.force_dry_run = force_dry_run

        self.stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def is_running(self) -> bool:
        """True if the worker background thread is alive and running."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Starts the worker in a background daemon thread."""
        if self.is_running():
            logger.warning("DispatchWorker is already running.")
            return

        self.stop_event.clear()
        self._thread = threading.Thread(target=self.run, daemon=True, name="DispatchWorkerThread")
        self._thread.start()
        logger.info("DispatchWorker started in background thread.")

    def stop(self, timeout: Optional[float] = 10.0) -> None:
        """Signals graceful shutdown and waits for in-flight send to finish."""
        logger.info("Stopping DispatchWorker...")
        self.stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("DispatchWorker stopped.")

    def run(self, max_dispatches: Optional[int] = None, exit_when_empty: bool = False) -> int:
        """
        Runs the dispatch polling loop until stopped, max_dispatches reached,
        or queue empty (if exit_when_empty is True).
        Returns the total number of successfully dispatched drafts.
        """
        dispatched_count = 0
        logger.info("DispatchWorker loop active. Polling for approved drafts...")

        while not self.stop_event.is_set():
            if max_dispatches is not None and dispatched_count >= max_dispatches:
                logger.info(f"Reached max dispatches limit ({max_dispatches}). Stopping worker run.")
                break

            # 1. Check daily send counter against limits
            today_count = self.db.get_today_sent_count()
            limit = self.config.limits.emails_per_day
            if today_count >= limit:
                logger.warning(
                    f"Daily send cap reached ({today_count}/{limit}). Halting dispatch cycle for today."
                )
                break

            # 2. Fetch approved drafts (FIFO order by draft id)
            approved_drafts = self.db.list_drafts(DraftStatus.APPROVED)
            if not approved_drafts:
                if exit_when_empty:
                    logger.info("Queue is empty and exit_when_empty is True. Stopping worker run.")
                    break
                # No approved drafts in queue, wait for next poll interval
                if self.stop_event.wait(timeout=self.poll_interval):
                    break
                continue

            # 3. Process the next draft in FIFO order
            draft = approved_drafts[0]
            success, error_reason = self.process_draft(draft)
            if success:
                dispatched_count += 1

            # 4. Randomized jitter delay between successive sends
            if not self.stop_event.is_set():
                delay_sec = (
                    0.0
                    if self.max_delay <= 0
                    else random.uniform(self.min_delay, max_delay=max(self.min_delay, self.max_delay))
                )
                if delay_sec > 0:
                    logger.info(f"Pacing delay: waiting {delay_sec:.1f}s before next dispatch...")
                    if self.stop_event.wait(timeout=delay_sec):
                        logger.info("Worker stop signaled during pacing delay.")
                        break

        logger.info(f"DispatchWorker run completed. Total dispatched: {dispatched_count}.")
        return dispatched_count

    def process_draft(self, draft: Draft) -> Tuple[bool, Optional[str]]:
        """
        Processes a single approved draft with pre-flight checks,
        dispatches via OutreachSender, updates status and logs details.
        Returns (success: bool, error_reason: Optional[str]).
        """
        contact = self.db.get_contact(draft.contact_id)
        if not contact:
            err = f"Contact ID {draft.contact_id} not found for draft {draft.id}."
            logger.error(err)
            self._mark_draft_failed(draft, err)
            return False, err

        email = (contact.email or "").strip().lower()

        # Pre-flight Check: Suppression list
        if self.suppression.is_suppressed(email):
            reason = f"Recipient {email} is on suppression/opt-out list."
            logger.warning(f"Draft {draft.id} skipped: {reason}")
            self._mark_draft_failed(draft, reason, contact=contact, log_channel="email")
            return False, reason

        # Pre-flight Check: Daily send limit
        today_count = self.db.get_today_sent_count()
        limit = self.config.limits.emails_per_day
        if today_count >= limit:
            reason = f"Daily send cap reached ({today_count}/{limit})."
            logger.warning(f"Draft {draft.id} skipped: {reason}")
            # Leave draft in APPROVED status so it can be sent tomorrow
            return False, reason

        # Pre-flight Check: Duplicate address check
        if self.db.has_already_sent_email(email):
            reason = f"Duplicate protection: Email already sent to {email}."
            logger.warning(f"Draft {draft.id} skipped: {reason}")
            self._mark_draft_failed(draft, reason, contact=contact, log_channel="email")
            return False, reason

        # Dispatch via OutreachSender
        # Sender handles dry-run, Gmail API call, and base send log
        dry_run = self.config.dry_run if self.force_dry_run is None else self.force_dry_run
        success, msg = self.sender.send_approved_email(
            contact=contact,
            draft=draft,
            force_dry_run=dry_run,
            respect_delay=False,  # Worker controls jitter delay between sends
        )

        if success:
            logger.info(f"Draft {draft.id} dispatched successfully: {msg}")
            self.db.update_draft_status(draft.id, DraftStatus.SENT)
            self.db.update_contact_status(contact.id, ContactStatus.EMAIL_SENT)
            return True, None
        else:
            logger.warning(f"Draft {draft.id} failed to dispatch: {msg}")
            self.db.update_draft_status(draft.id, DraftStatus.FAILED)
            return False, msg

    def _mark_draft_failed(
        self,
        draft: Draft,
        reason: str,
        contact: Optional[any] = None,
        log_channel: str = "email",
    ) -> None:
        """Marks draft as FAILED and logs failure in send_logs."""
        self.db.update_draft_status(draft.id, DraftStatus.FAILED)
        recipient = contact.email if contact else ""
        contact_id = contact.id if contact else draft.contact_id

        self.db.log_send(
            SendLog(
                contact_id=contact_id or 0,
                draft_id=draft.id,
                channel=log_channel,
                recipient=recipient,
                gmail_message_id=None,
                gmail_thread_id=None,
                is_dry_run=self.config.dry_run if self.force_dry_run is None else self.force_dry_run,
                status="FAILED",
                error_message=reason,
            )
        )
