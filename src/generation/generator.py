"""Outreach draft generation orchestrator with validation, fact grounding, and automatic retries."""

import logging
from typing import List, Optional
from src.config import AppConfig
from src.db.database import Database
from src.db.models import Contact, ContactStatus, Draft, DraftStatus, ResearchDossier
from src.generation.llm_client import LLMClient
from src.generation.prompts import build_system_prompt, build_user_prompt
from src.generation.uniqueness import check_batch_uniqueness
from src.generation.validator import validate_draft

logger = logging.getLogger(__name__)


class DraftGenerator:
    def __init__(self, config: AppConfig, db: Database, llm_client: Optional[LLMClient] = None):
        self.config = config
        self.db = db
        self.llm = llm_client or LLMClient(config)

    def generate_for_contact(self, contact: Contact, dossier: ResearchDossier, existing_draft_texts: Optional[List[str]] = None) -> Draft:
        """Generates a personalized draft package for a single contact with up to 3 validation attempts."""
        system_prompt = build_system_prompt(self.config)
        user_prompt = build_user_prompt(contact, dossier)

        # 1. Single LLM Generation Pass
        result = self.llm.generate_drafts(contact, dossier, system_prompt, user_prompt)
        email_body = result.get("email_body", "")

        # 2. Strict SlopDetector Check (Length, buzzwords, banned openers, em-dashes)
        val_res = validate_draft(email_body, max_words=90)
        violations = list(val_res.violations)

        # 3. Strict Fact-Grounding Check Against Dossier
        grounding_res = self.llm.check_fact_grounding(email_body, dossier.verifiable_facts)
        if not grounding_res.get("grounded", True):
            unsupported = grounding_res.get("unsupported_claims", [])
            violations.extend([f"Unsupported claim not in facts: {c}" for c in unsupported])

        # 4. Batch Uniqueness Check
        if existing_draft_texts and not check_batch_uniqueness(email_body, existing_draft_texts, threshold=0.45):
            violations.append("Draft is too similar to another message in this batch.")

        # 5. Determine Review & Approval Status
        if violations:
            draft_status = DraftStatus.FLAGGED
            contact_status = ContactStatus.NEEDS_MANUAL_REVIEW
            logger.warning(f"Draft for {contact.company} FLAGGED: {violations}")
        elif not dossier.has_strong_hook or result.get("needs_manual_review", False):
            draft_status = DraftStatus.PENDING
            contact_status = ContactStatus.NEEDS_MANUAL_REVIEW
        else:
            draft_status = DraftStatus.PENDING
            contact_status = ContactStatus.READY_FOR_REVIEW

        # Extract WhatsApp message or build friendly local fallback under 50 words
        wa_msg = result.get("whatsapp_message", "").strip()
        if not wa_msg:
            clean_first = contact.first_name if contact.first_name and contact.first_name.lower() != "there" else ""
            greeting = f"Hey {clean_first}" if clean_first else "Hey there"
            wa_msg = f"{greeting}! Loved seeing {contact.company} on Maps. Saw that there is no online booking link yet—I built a simple 1-click booking tool for local businesses. Mind if I share a 30-sec preview?"
        # Ensure under 50 words
        wa_words = wa_msg.split()
        if len(wa_words) > 50:
            wa_msg = " ".join(wa_words[:48]) + "..."

        hook = result.get("hook", "")
        source_facts = result.get("source_facts_used", dossier.verifiable_facts[:1])

        draft = Draft(
            contact_id=contact.id or 0,
            hook=hook,
            linkedin_note=result.get("linkedin_note", ""),
            linkedin_message=result.get("linkedin_message", ""),
            whatsapp_message=wa_msg,
            email_subject=result.get("email_subject", f"Question regarding {contact.company}"),
            email_subject_alt1=result.get("email_subject_alt1", ""),
            email_subject_alt2=result.get("email_subject_alt2", ""),
            email_body=result.get("email_body", ""),
            followup_subject=result.get("followup_subject", f"Following up: {contact.company}"),
            followup_body=result.get("followup_body", ""),
            source_facts=source_facts,
            status=draft_status,
        )

        # Save to database
        self.db.save_draft(draft)
        self.db.update_contact_status(contact.id, contact_status)

        return draft

    def batch_generate(self, contacts: List[Contact]) -> List[Draft]:
        """Generates drafts for a batch of contacts, maintaining cross-batch uniqueness."""
        generated_drafts = []
        batch_email_bodies = []

        for contact in contacts:
            dossier = self.db.get_dossier(contact.id)
            if not dossier:
                logger.warning(f"No research dossier found for contact {contact.id} ({contact.company}). Skipping.")
                continue

            draft = self.generate_for_contact(contact, dossier, existing_draft_texts=batch_email_bodies)
            generated_drafts.append(draft)
            if draft.email_body:
                batch_email_bodies.append(draft.email_body)

        return generated_drafts
