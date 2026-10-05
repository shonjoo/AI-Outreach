"""Unit tests for reply tracking, Gemini/fallback intent classification, and alerts."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.config import load_config
from src.db.database import Database
from src.db.models import Contact, ContactStatus, Draft, DraftStatus, SendLog
from src.sending.reply_tracker import (
    INTENT_INTERESTED,
    INTENT_NOT_NOW,
    INTENT_PRICE_QUESTION,
    INTENT_UNSUBSCRIBE,
    ReplyTracker,
)
from src.sending.suppression import SuppressionManager


class TestReplyTracker(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_replies.db")
        self.config = load_config()
        self.config.db_path = self.db_path
        self.config.dry_run = True
        self.db = Database(self.db_path, force_sqlite=True)
        self.suppression = SuppressionManager(self.db)
        self.tracker = ReplyTracker(
            config=self.config,
            db=self.db,
            suppression_manager=self.suppression,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_deterministic_intent_classification(self):
        """Verify regex/keyword classification across all 4 intents."""
        # 1. INTERESTED
        r1 = self.tracker.classify_intent_deterministic(
            "Yes, I would love to see a 2-minute preview of the booking tool. Let's talk tomorrow."
        )
        self.assertEqual(r1["intent"], INTENT_INTERESTED)

        # 2. PRICE_QUESTION
        r2 = self.tracker.classify_intent_deterministic(
            "How much does your monthly package cost? Could you send over pricing options?"
        )
        self.assertEqual(r2["intent"], INTENT_PRICE_QUESTION)

        # 3. NOT_NOW
        r3 = self.tracker.classify_intent_deterministic(
            "We are too busy with renovations right now. Please follow up in two months."
        )
        self.assertEqual(r3["intent"], INTENT_NOT_NOW)

        # 4. UNSUBSCRIBE
        r4 = self.tracker.classify_intent_deterministic(
            "Please remove me from your list and unsubscribe. Do not contact again."
        )
        self.assertEqual(r4["intent"], INTENT_UNSUBSCRIBE)

    def test_handle_unsubscribe_triggers_suppression_and_opt_out_status(self):
        """UNSUBSCRIBE reply must suppress email immediately and update contact status to OPTED_OUT."""
        contact = Contact(
            first_name="David",
            last_name="Miller",
            company="Miller Auto",
            email="david@millerauto.com",
            status=ContactStatus.EMAIL_SENT,
        )
        cid = self.db.insert_contact(contact)
        contact.id = cid

        classification = {
            "intent": INTENT_UNSUBSCRIBE,
            "confidence": 0.98,
            "summary": "Opt out requested.",
        }

        new_status = self.tracker.handle_classified_reply(
            contact=contact,
            reply_text="Stop emailing me, unsubscribe please.",
            classification=classification,
        )

        self.assertEqual(new_status, ContactStatus.OPTED_OUT)
        # Verify contact updated in database
        updated_contact = self.db.get_contact(cid)
        self.assertEqual(updated_contact.status, ContactStatus.OPTED_OUT)

        # Verify added to suppression list
        self.assertTrue(self.suppression.is_suppressed("david@millerauto.com"))

    def test_handle_not_now_updates_status(self):
        """NOT_NOW reply must update contact status to FOLLOW_UP_LATER."""
        contact = Contact(
            first_name="Sarah",
            company="Sarah Salon",
            email="sarah@sarahsalon.com",
            status=ContactStatus.EMAIL_SENT,
        )
        cid = self.db.insert_contact(contact)
        contact.id = cid

        classification = {
            "intent": INTENT_NOT_NOW,
            "confidence": 0.90,
            "summary": "Check back in Q3.",
        }

        new_status = self.tracker.handle_classified_reply(
            contact=contact,
            reply_text="Not now, we are fully booked. Check back next quarter.",
            classification=classification,
        )

        self.assertEqual(new_status, ContactStatus.FOLLOW_UP_LATER)
        updated_contact = self.db.get_contact(cid)
        self.assertEqual(updated_contact.status, ContactStatus.FOLLOW_UP_LATER)

    def test_handle_interested_triggers_webhook_and_hot_lead(self):
        """INTERESTED reply updates status to HOT_LEAD and fires webhook POST."""
        contact = Contact(
            first_name="Jessica",
            company="Smile Studio",
            email="jessica@smilestudio.com",
            status=ContactStatus.EMAIL_SENT,
        )
        cid = self.db.insert_contact(contact)
        contact.id = cid

        classification = {
            "intent": INTENT_INTERESTED,
            "confidence": 0.95,
            "summary": "Curious to see demo.",
        }

        # Mock urllib.request.urlopen to verify POST payload
        self.tracker.webhook_url = "https://hooks.example.com/lead-alert"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            new_status = self.tracker.handle_classified_reply(
                contact=contact,
                reply_text="Sounds great, would love to see a 30-sec preview!",
                classification=classification,
            )

            self.assertEqual(new_status, ContactStatus.HOT_LEAD)
            self.assertEqual(self.db.get_contact(cid).status, ContactStatus.HOT_LEAD)

            # Webhook should have been called
            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args[0]
            req = call_args[0]
            self.assertEqual(req.full_url, "https://hooks.example.com/lead-alert")
            sent_payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(sent_payload["email"], "jessica@smilestudio.com")
            self.assertEqual(sent_payload["intent"], INTENT_INTERESTED)

    def test_poll_replies_thread_processing(self):
        """poll_replies queries Gmail threads and applies classification."""
        contact = Contact(
            first_name="Alex",
            company="Alex Diner",
            email="alex@alexdiner.com",
            status=ContactStatus.EMAIL_SENT,
        )
        cid = self.db.insert_contact(contact)
        contact.id = cid

        # Log an outbound send with thread ID
        self.db.log_send(
            SendLog(
                contact_id=cid,
                channel="email",
                recipient="alex@alexdiner.com",
                gmail_message_id="msg-101",
                gmail_thread_id="thd-505",
                is_dry_run=False,
                status="SENT",
            )
        )

        mock_gmail = MagicMock()
        mock_gmail.get_thread_messages.return_value = (
            True,
            [
                {"snippet": "Original outbound message", "payload": {"headers": [{"name": "From", "value": "sender@domain.com"}]}},
                {"snippet": "How much would a mobile website and online booking tool cost?", "payload": {"headers": [{"name": "From", "value": "alex@alexdiner.com"}]}},
            ],
            None,
        )

        tracker = ReplyTracker(
            config=self.config,
            db=self.db,
            gmail_client=mock_gmail,
            suppression_manager=self.suppression,
        )

        results = tracker.poll_replies(force_dry_run=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "alex@alexdiner.com")
        self.assertEqual(results[0]["intent"], INTENT_PRICE_QUESTION)
        self.assertEqual(self.db.get_contact(cid).status, ContactStatus.REPLIED)


if __name__ == "__main__":
    unittest.main()
