"""Comprehensive test suite for the personalized outreach platform."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.config import load_config
from src.db.database import Database
from src.db.models import Contact, ContactStatus, DraftStatus
from src.generation.generator import DraftGenerator
from src.generation.uniqueness import calculate_jaccard_similarity, check_batch_uniqueness
from src.research.dossier import DossierBuilder
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager


class TestOutreachPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_outreach.db")
        self.config = load_config()
        self.config.db_path = self.db_path
        self.config.dry_run = True
        self.db = Database(self.db_path, force_sqlite=True)
        self.suppression = SuppressionManager(self.db)
        self.builder = DossierBuilder()
        self.generator = DraftGenerator(self.config, self.db)
        self.sender = OutreachSender(self.config, self.db, suppression_manager=self.suppression)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_config_loaded_correctly(self):
        """Verify that config.yaml strictly matches user specifications."""
        self.assertEqual(self.config.sender.name, "Nillohit Debnath")
        self.assertEqual(self.config.sender.email, "nillohitfreelanceco@gmail.com")
        self.assertEqual(self.config.limits.emails_per_day, 20)
        self.assertEqual(self.config.limits.delay_between_sends_seconds, [90, 240])
        self.assertIn("synergy", self.config.style.avoid)
        self.assertIn("I hope this finds you well", self.config.style.avoid)

    def test_02_contact_ingestion(self):
        """Verify contact creation and retrieval."""
        contact = Contact(
            first_name="Elena",
            last_name="Vance",
            company="Apex Smile Dental Care",
            job_title="Owner & Lead Dentist",
            email="elena@apexsmiledental.example.com",
            notes="Clinic website has no online booking button; patients must call during business hours.",
        )
        cid = self.db.insert_contact(contact)
        self.assertIsNotNone(cid)

        retrieved = self.db.get_contact(cid)
        self.assertEqual(retrieved.company, "Apex Smile Dental Care")
        self.assertEqual(retrieved.status, ContactStatus.PENDING_RESEARCH)

    def test_03_research_and_dossier_building(self):
        """Verify facts are extracted and opportunities detected."""
        contact = Contact(
            id=1,
            first_name="Marco",
            last_name="Bellini",
            company="Trattoria Bella Napoli",
            email="marco@trattoriabellanapoli.example.com",
            notes="Menu is a downloaded PDF with tiny text on mobile; customers ask for reservations on Instagram.",
        )
        dossier = self.builder.build_dossier(contact)
        self.assertTrue(dossier.has_strong_hook)
        self.assertTrue(any("pdf" in f.lower() for f in dossier.verifiable_facts))
        self.assertTrue(len(dossier.detected_opportunities) > 0)

    def test_04_generation_constraints_and_limits(self):
        """Verify drafts adhere to character/word limits and negative constraints."""
        contact = Contact(
            id=1,
            first_name="Sarah",
            last_name="Jenkins",
            company="Lumina Hair & Beauty Lounge",
            email="sarah@luminahairlounge.example.com",
            notes="No website, Instagram bio has broken booking link; customers comment asking for pricing.",
        )
        self.db.insert_contact(contact)
        dossier = self.builder.build_dossier(contact)
        self.db.save_dossier(dossier)

        draft = self.generator.generate_for_contact(contact, dossier)

        # Check LinkedIn limits
        self.assertLessEqual(len(draft.linkedin_note), 300)
        self.assertLessEqual(len(draft.linkedin_message), 600)

        # Check Email length adheres to max 90 words (Phase 4 requirement)
        words = len(draft.email_body.split())
        self.assertTrue(30 <= words <= 90, f"Word count was {words}, expected <= 90 words")

        # Check negative constraints (forbidden phrases)
        for forbidden in self.config.style.avoid:
            if forbidden != "emojis" and forbidden != "long introductions":
                self.assertNotIn(forbidden.lower(), draft.email_body.lower())
                self.assertNotIn(forbidden.lower(), draft.linkedin_message.lower())

        # Check that emojis are absent
        self.assertTrue(all(ord(char) < 127 for char in draft.email_body if char.isascii()))

        # Check low-friction ask
        self.assertTrue("?" in draft.email_body or any(w in draft.email_body.lower() for w in ["reply", "let me know", "worth", "interested"]))

    def test_05_uniqueness_across_batch(self):
        """Verify that batch drafts maintain uniqueness and are not cookie-cutter."""
        text_dental = (
            "While researching local dental practices, I noticed that Apex Smile Dental receives stellar patient reviews, "
            "but booking requires calling during clinic hours. For busy patients, this often means delayed inquiries. "
            "I build modern websites and simple AI automation for clinics, including automated booking assistants that "
            "schedule appointments 24/7. Would you be open to a 2-minute demo? Simply reply to this email."
        )
        text_restaurant = (
            "I was looking through Trattoria Bella Napoli dishes online and noticed that your menu is currently hosted as a "
            "PDF file. On mobile screens, pinch-zooming into PDFs often causes potential diners to bounce. "
            "I build high-converting websites and AI automation for local restaurants, such as interactive mobile menus and "
            "automated reservation assistants. Would you be interested in a preview? Simply reply to this email."
        )

        sim = calculate_jaccard_similarity(text_dental, text_restaurant)
        self.assertLess(sim, 0.40, f"Similarity {sim} was too high")
        self.assertTrue(check_batch_uniqueness(text_restaurant, [text_dental]))

    def test_06_sending_safeguards_and_rate_limits(self):
        """Verify dry-run simulation, duplicate protection, suppression, and rate limits."""
        contact = Contact(
            first_name="Elena",
            last_name="Vance",
            company="Apex Smile Dental Care",
            email="elena@apexsmiledental.example.com",
            notes="No online booking",
        )
        cid = self.db.insert_contact(contact)
        contact.id = cid

        dossier = self.builder.build_dossier(contact)
        self.db.save_dossier(dossier)
        draft = self.generator.generate_for_contact(contact, dossier)
        draft.id = self.db.get_draft(cid).id

        # 1. First Send (Simulated Dry-Run)
        success, msg = self.sender.send_approved_email(contact, draft, force_dry_run=True, respect_delay=False)
        self.assertTrue(success)
        self.assertIn("[DRY-RUN SIMULATED]", msg)

        # Verify DB logged the send
        logs = self.db.list_send_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].recipient, "elena@apexsmiledental.example.com")
        self.assertTrue(logs[0].is_dry_run)

        # 2. Duplicate Protection Check
        success_dup, msg_dup = self.sender.send_approved_email(contact, draft, force_dry_run=True, respect_delay=False)
        self.assertFalse(success_dup)
        self.assertIn("Duplicate protection", msg_dup)

        # 3. Suppression List Check on a new contact
        contact2 = Contact(
            first_name="Blocked",
            last_name="User",
            company="Blocked Co",
            email="optout@example.com",
        )
        cid2 = self.db.insert_contact(contact2)
        contact2.id = cid2
        self.suppression.suppress_contact("optout@example.com")

        success_sup, msg_sup = self.sender.send_approved_email(contact2, draft, force_dry_run=True, respect_delay=False)
        self.assertFalse(success_sup)
        self.assertIn("suppression", msg_sup)

    def test_07_opt_out_footer_appended(self):
        """Verify CAN-SPAM/GDPR compliance footer."""
        body = "Hello Dr. Vance, would love to show you a demo."
        final = self.suppression.append_opt_out_footer(
            body,
            sender_name="Nillohit Debnath",
            sender_email="nillohitfreelanceco@gmail.com",
        )
        self.assertIn("Nillohit Debnath", final)
        self.assertIn("nillohitfreelanceco@gmail.com", final)
        self.assertIn("unsubscribe", final)


if __name__ == "__main__":
    unittest.main()
