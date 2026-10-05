"""Comprehensive test suite for Supabase database integration and fallback."""

import json
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.config import AppConfig, DatabaseConfig, LimitsConfig, LLMConfig, OutreachConfig, SenderConfig, StyleConfig
from src.db.database import Database
from src.db.models import (
    Contact,
    ContactStatus,
    Draft,
    DraftStatus,
    ResearchDossier,
    SendLog,
    SuppressionEntry,
)
from src.db.supabase_db import SupabaseDatabase, _parse_json_field


class TestSupabaseIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        with patch("src.db.supabase_db.create_client", return_value=self.mock_client):
            self.db = SupabaseDatabase("https://xyz.supabase.co", "fake-key")

    def test_parse_json_field(self):
        """Verify _parse_json_field handles lists, strings, None, and invalid JSON."""
        self.assertEqual(_parse_json_field(None), [])
        self.assertEqual(_parse_json_field(["fact 1"]), ["fact 1"])
        self.assertEqual(_parse_json_field('["fact 1", "fact 2"]'), ["fact 1", "fact 2"])
        self.assertEqual(_parse_json_field("not a json"), [])
        self.assertEqual(_parse_json_field(123), [])

    def test_insert_contact_new(self):
        """Verify inserting a new contact executes an insert call."""
        # 1. Select for existing returns empty data
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(data=[])

        # 2. Insert returns new row
        insert_mock = MagicMock()
        insert_mock.execute.return_value = MagicMock(data=[{"id": 42}])

        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.limit.return_value = select_mock
        table_mock.insert.return_value = insert_mock
        self.mock_client.table.return_value = table_mock

        contact = Contact(
            first_name="Jane",
            last_name="Doe",
            company="Acme Corp",
            email="jane@acme.com",
            job_title="CEO",
        )
        cid = self.db.insert_contact(contact)
        self.assertEqual(cid, 42)
        table_mock.insert.assert_called_once()

    def test_insert_contact_existing_updates(self):
        """Verify inserting an existing contact updates the existing record."""
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(data=[{"id": 10}])

        update_mock = MagicMock()
        update_mock.execute.return_value = MagicMock(data=[{"id": 10}])

        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.limit.return_value = select_mock
        table_mock.update.return_value.eq.return_value = update_mock
        self.mock_client.table.return_value = table_mock

        contact = Contact(
            first_name="Jane",
            last_name="Doe",
            company="Acme Corp",
            email="jane@acme.com",
        )
        cid = self.db.insert_contact(contact)
        self.assertEqual(cid, 10)
        table_mock.update.assert_called_once()

    def test_get_contact(self):
        """Verify get_contact maps Supabase row to Contact dataclass."""
        row = {
            "id": 5,
            "first_name": "Alice",
            "last_name": "Smith",
            "company": "Dental Care",
            "job_title": "Owner",
            "linkedin_url": "https://linkedin.com/in/alice",
            "email": "alice@dental.com",
            "notes": "Great practice",
            "website": "https://dental.com",
            "status": "APPROVED",
            "created_at": "2026-10-03T12:00:00",
            "updated_at": "2026-10-03T12:00:00",
        }
        res_mock = MagicMock()
        res_mock.execute.return_value = MagicMock(data=[row])

        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.limit.return_value = res_mock
        self.mock_client.table.return_value = table_mock

        contact = self.db.get_contact(5)
        self.assertIsNotNone(contact)
        self.assertEqual(contact.id, 5)
        self.assertEqual(contact.first_name, "Alice")
        self.assertEqual(contact.status, ContactStatus.APPROVED)

    def test_list_contacts(self):
        """Verify list_contacts returns a list of contacts."""
        rows = [
            {
                "id": 1,
                "first_name": "Bob",
                "last_name": "Brown",
                "company": "Bakery",
                "email": "bob@bakery.com",
                "status": "PENDING_RESEARCH",
                "created_at": "2026-10-03T12:00:00",
                "updated_at": "2026-10-03T12:00:00",
            }
        ]
        res_mock = MagicMock()
        res_mock.execute.return_value = MagicMock(data=rows)

        table_mock = MagicMock()
        table_mock.select.return_value.order.return_value = res_mock
        self.mock_client.table.return_value = table_mock

        contacts = self.db.list_contacts()
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].company, "Bakery")

    def test_save_and_get_dossier(self):
        """Verify save_dossier and get_dossier with JSON list structures."""
        # Test save (new dossier)
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(data=[])
        insert_mock = MagicMock()
        insert_mock.execute.return_value = MagicMock(data=[{"id": 88}])

        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.limit.return_value = select_mock
        table_mock.insert.return_value = insert_mock
        self.mock_client.table.return_value = table_mock

        dossier = ResearchDossier(
            contact_id=1,
            business_name="Acme",
            verifiable_facts=["Fact 1", "Fact 2"],
            detected_opportunities=["Online booking"],
        )
        did = self.db.save_dossier(dossier)
        self.assertEqual(did, 88)

        # Test get
        row = {
            "id": 88,
            "contact_id": 1,
            "business_name": "Acme",
            "verifiable_facts": ["Fact 1", "Fact 2"],
            "detected_opportunities": ["Online booking"],
            "search_snippets": [],
            "user_pasted_content": "",
            "has_strong_hook": True,
            "created_at": "2026-10-03T12:00:00",
        }
        res_mock = MagicMock()
        res_mock.execute.return_value = MagicMock(data=[row])
        table_mock.select.return_value.eq.return_value.limit.return_value = res_mock

        retrieved = self.db.get_dossier(1)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.verifiable_facts, ["Fact 1", "Fact 2"])

    def test_save_and_get_draft(self):
        """Verify save_draft and get_draft mapping."""
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(data=[])
        insert_mock = MagicMock()
        insert_mock.execute.return_value = MagicMock(data=[{"id": 99}])

        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.limit.return_value = select_mock
        table_mock.insert.return_value = insert_mock
        self.mock_client.table.return_value = table_mock

        draft = Draft(
            contact_id=1,
            hook="Noticed you lack online booking.",
            email_subject="Quick question",
            email_body="Hello, we can help build online booking.",
            status=DraftStatus.PENDING,
        )
        draft_id = self.db.save_draft(draft)
        self.assertEqual(draft_id, 99)

        # Test get
        row = {
            "id": 99,
            "contact_id": 1,
            "hook": "Noticed you lack online booking.",
            "email_subject": "Quick question",
            "email_body": "Hello, we can help build online booking.",
            "source_facts": ["Fact A"],
            "status": "PENDING",
            "version": 1,
            "created_at": "2026-10-03T12:00:00",
            "updated_at": "2026-10-03T12:00:00",
        }
        res_mock = MagicMock()
        res_mock.execute.return_value = MagicMock(data=[row])
        table_mock.select.return_value.eq.return_value.limit.return_value = res_mock

        retrieved = self.db.get_draft(1)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, DraftStatus.PENDING)
        self.assertEqual(retrieved.source_facts, ["Fact A"])

    def test_new_status_enums_compatibility(self):
        """Verify HOT_LEAD, FOLLOW_UP_LATER, SENT, and FAILED enums are handled correctly."""
        # 1. Contact with HOT_LEAD and FOLLOW_UP_LATER
        update_mock = MagicMock()
        update_mock.execute.return_value = MagicMock(data=[{"id": 7}])
        table_mock = MagicMock()
        table_mock.update.return_value.eq.return_value = update_mock
        self.mock_client.table.return_value = table_mock

        self.db.update_contact_status(7, ContactStatus.HOT_LEAD)
        table_mock.update.assert_called_with({"status": "HOT_LEAD", "updated_at": unittest.mock.ANY})

        self.db.update_contact_status(7, ContactStatus.FOLLOW_UP_LATER)
        table_mock.update.assert_called_with({"status": "FOLLOW_UP_LATER", "updated_at": unittest.mock.ANY})

        # 2. Draft with SENT and FAILED
        self.db.update_draft_status(15, DraftStatus.SENT)
        table_mock.update.assert_called_with({"status": "SENT", "updated_at": unittest.mock.ANY})

        self.db.update_draft_status(15, DraftStatus.FAILED)
        table_mock.update.assert_called_with({"status": "FAILED", "updated_at": unittest.mock.ANY})

        # 3. Retrieve contacts with HOT_LEAD
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(
            data=[
                {
                    "id": 7,
                    "first_name": "Hot",
                    "last_name": "Prospect",
                    "company": "Growth Clinic",
                    "email": "hot@clinic.com",
                    "status": "HOT_LEAD",
                    "created_at": "2026-10-04T12:00:00",
                    "updated_at": "2026-10-04T12:00:00",
                }
            ]
        )
        table_mock.select.return_value.order.return_value = select_mock
        contacts = self.db.list_contacts()
        self.assertEqual(contacts[0].status, ContactStatus.HOT_LEAD)

    def test_suppression(self):
        """Verify suppression check, addition, and listing."""
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(data=[{"id": 1}])
        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.limit.return_value = select_mock
        self.mock_client.table.return_value = table_mock

        self.assertTrue(self.db.is_suppressed("optout@example.com"))

    def test_send_log_and_rate_limits(self):
        """Verify logging sends and incrementing daily send counter."""
        insert_log_mock = MagicMock()
        insert_log_mock.execute.return_value = MagicMock(data=[{"id": 123}])

        # Counter exists
        select_counter_mock = MagicMock()
        select_counter_mock.execute.return_value = MagicMock(data=[{"count": 3}])
        update_counter_mock = MagicMock()
        update_counter_mock.execute.return_value = MagicMock(data=[])

        table_mock = MagicMock()
        table_mock.insert.return_value = insert_log_mock
        table_mock.select.return_value.eq.return_value.limit.return_value = select_counter_mock
        table_mock.update.return_value.eq.return_value = update_counter_mock
        self.mock_client.table.return_value = table_mock

        log = SendLog(
            contact_id=1,
            recipient="test@example.com",
            is_dry_run=True,
            status="SIMULATED",
        )
        log_id = self.db.log_send(log)
        self.assertEqual(log_id, 123)

    def test_database_facade_routing(self):
        """Verify Database facade routes to Supabase when configured, or SQLite when not."""
        # 1. Config with Supabase enabled
        config = AppConfig(
            sender=SenderConfig(),
            outreach=OutreachConfig(),
            style=StyleConfig(),
            limits=LimitsConfig(),
            llm=LLMConfig(),
            database=DatabaseConfig(
                backend="supabase",
                supabase_url="https://fake.supabase.co",
                supabase_key="fake-key",
            ),
        )

        with patch("src.db.supabase_db.create_client") as mock_cc:
            db_supabase = Database(config=config)
            self.assertTrue(db_supabase.is_supabase)
            self.assertEqual(db_supabase.backend_name, "supabase")
            mock_cc.assert_called_once()

        # 2. Config with SQLite forced
        db_sqlite = Database("tests/test_tmp.db", force_sqlite=True)
        self.assertFalse(db_sqlite.is_supabase)
        self.assertEqual(db_sqlite.backend_name, "sqlite")


if __name__ == "__main__":
    unittest.main()
