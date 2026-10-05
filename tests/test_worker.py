"""Unit tests for the background dispatch queue worker."""

import os
import shutil
import tempfile
import threading
import time
from typing import Tuple
import unittest

from src.config import load_config
from src.db.database import Database
from src.db.models import Contact, ContactStatus, Draft, DraftStatus
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager
from src.sending.worker import DispatchWorker


class TestDispatchWorker(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_worker.db")
        self.config = load_config()
        self.config.db_path = self.db_path
        self.config.dry_run = True
        self.config.limits.emails_per_day = 5
        self.db = Database(self.db_path, force_sqlite=True)
        self.suppression = SuppressionManager(self.db)
        self.sender = OutreachSender(self.config, self.db, suppression_manager=self.suppression)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_contact_and_approved_draft(self, name: str, email: str, company: str) -> Tuple[Contact, Draft]:
        contact = Contact(
            first_name=name,
            last_name="Test",
            company=company,
            email=email,
        )
        cid = self.db.insert_contact(contact)
        contact.id = cid

        draft = Draft(
            contact_id=cid,
            hook=f"Saw {company}'s website",
            email_subject=f"Question for {company}",
            email_body=(
                f"Hi {name},\n\n"
                f"Saw that booking at {company} requires phone calls during open hours.\n\n"
                f"I build simple online booking tools for local businesses.\n\n"
                f"Open to seeing a 2-minute preview?"
            ),
            status=DraftStatus.APPROVED,
        )
        did = self.db.save_draft(draft)
        draft.id = did
        return contact, draft

    def test_worker_pulls_approved_drafts_in_fifo_order(self):
        """Worker should process approved drafts in FIFO order (by id)."""
        c1, d1 = self._create_contact_and_approved_draft("Alpha", "alpha@localclinic.com", "Clinic Alpha")
        c2, d2 = self._create_contact_and_approved_draft("Beta", "beta@localsalon.com", "Salon Beta")

        worker = DispatchWorker(
            config=self.config,
            db=self.db,
            sender=self.sender,
            suppression_manager=self.suppression,
            min_delay=0.0,
            max_delay=0.0,
            poll_interval=0.1,
            force_dry_run=True,
        )

        dispatched = worker.run(max_dispatches=2)
        self.assertEqual(dispatched, 2)

        # Verify drafts updated to SENT
        d1_updated = self.db.get_draft(c1.id)
        d2_updated = self.db.get_draft(c2.id)
        self.assertEqual(d1_updated.status, DraftStatus.SENT)
        self.assertEqual(d2_updated.status, DraftStatus.SENT)

        # Verify send logs order
        logs = self.db.list_send_logs()
        self.assertEqual(len(logs), 2)
        # FIFO: First sent was d1 (alpha), then d2 (beta)
        self.assertEqual(logs[0].recipient, "beta@localsalon.com")  # logs listed desc
        self.assertEqual(logs[1].recipient, "alpha@localclinic.com")

    def test_worker_respects_daily_send_limit_and_halts(self):
        """Worker should halt dispatching when daily send limit is reached."""
        self.config.limits.emails_per_day = 2

        # Create 4 approved drafts
        for i in range(4):
            self._create_contact_and_approved_draft(f"Lead{i}", f"lead{i}@bizdomain.com", f"Biz {i}")

        worker = DispatchWorker(
            config=self.config,
            db=self.db,
            sender=self.sender,
            suppression_manager=self.suppression,
            min_delay=0.0,
            max_delay=0.0,
            poll_interval=0.1,
            force_dry_run=True,
        )

        dispatched = worker.run()
        self.assertEqual(dispatched, 2)
        self.assertEqual(self.db.get_today_sent_count(), 2)

        # 2 should be SENT, remaining 2 should remain APPROVED for next day
        approved = self.db.list_drafts(DraftStatus.APPROVED)
        sent = self.db.list_drafts(DraftStatus.SENT)
        self.assertEqual(len(sent), 2)
        self.assertEqual(len(approved), 2)

    def test_worker_skips_post_approval_suppression(self):
        """Drafts whose recipients were added to suppression list post-approval must be skipped/failed."""
        c1, d1 = self._create_contact_and_approved_draft("OptOut", "optout@localshop.com", "Shop OptOut")
        c2, d2 = self._create_contact_and_approved_draft("Valid", "valid@localshop.com", "Shop Valid")

        # Suppress optout contact after draft was approved
        self.suppression.suppress_contact("optout@localshop.com")

        worker = DispatchWorker(
            config=self.config,
            db=self.db,
            sender=self.sender,
            suppression_manager=self.suppression,
            min_delay=0.0,
            max_delay=0.0,
            poll_interval=0.1,
            force_dry_run=True,
        )

        dispatched = worker.run(max_dispatches=2, exit_when_empty=True)
        self.assertEqual(dispatched, 1)

        d1_updated = self.db.get_draft(c1.id)
        d2_updated = self.db.get_draft(c2.id)
        self.assertEqual(d1_updated.status, DraftStatus.FAILED)
        self.assertEqual(d2_updated.status, DraftStatus.SENT)

    def test_dry_run_simulation_mode(self):
        """Dry-run mode executes cleanly without real SMTP sends, logging SIMULATED."""
        c, d = self._create_contact_and_approved_draft("Dry", "dry@previewdomain.com", "Preview Co")

        worker = DispatchWorker(
            config=self.config,
            db=self.db,
            sender=self.sender,
            suppression_manager=self.suppression,
            min_delay=0.0,
            max_delay=0.0,
            poll_interval=0.1,
            force_dry_run=True,
        )

        dispatched = worker.run(max_dispatches=1)
        self.assertEqual(dispatched, 1)

        logs = self.db.list_send_logs()
        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0].is_dry_run)
        self.assertEqual(logs[0].status, "SIMULATED")

    def test_graceful_shutdown(self):
        """Worker thread should exit cleanly when stop() is called."""
        worker = DispatchWorker(
            config=self.config,
            db=self.db,
            sender=self.sender,
            suppression_manager=self.suppression,
            min_delay=0.0,
            max_delay=0.0,
            poll_interval=0.05,
            force_dry_run=True,
        )

        worker.start()
        self.assertTrue(worker.is_running())
        time.sleep(0.1)
        worker.stop(timeout=2.0)
        self.assertFalse(worker.is_running())


if __name__ == "__main__":
    unittest.main()
