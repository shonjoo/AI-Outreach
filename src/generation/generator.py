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
        base_user_prompt = build_user_prompt(contact, dossier)

        max_attempts = 3
        attempt = 0
        violations = []
        result = {}
        passed_validation = False

        while attempt < max_attempts:
            attempt += 1

            if violations:
                prompt_to_send = (
                    base_user_prompt
                    + f"\n\nCRITICAL FIXES REQUIRED (Attempt {attempt}/{max_attempts}):\n"
                    + "Your previous draft was rejected for the following rule violations:\n"
                    + "\n".join(f"- {v}" for v in violations)
                    + "\n\nRewrite the message from scratch. Ensure the email body is strictly under 90 words with zero banned words or patterns."
                )
            else:
                prompt_to_send = base_user_prompt

            result = self.llm.generate_drafts(contact, dossier, system_prompt, prompt_to_send)
            email_body = result.get("email_body", "")

            # 1. Post-Generation Validator (Style & Negative Constraints)
            val_res = validate_draft(email_body, max_words=90)
            if not val_res.is_valid:
                violations = val_res.violations
                logger.warning(f"Draft validation failed for {contact.company} (attempt {attempt}/{max_attempts}): {violations}")
                continue

            # 2. Fact-Grounding Check (LLM Auditor)
            grounding_res = self.llm.check_fact_grounding(email_body, dossier.verifiable_facts)
            if not grounding_res.get("grounded", True):
                unsupported = grounding_res.get("unsupported_claims", [])
                violations = [f"Unsupported claim not found in verified facts: {claim}" for claim in unsupported]
                logger.warning(f"Fact-grounding failed for {contact.company} (attempt {attempt}/{max_attempts}): {violations}")
                continue

            # 3. Uniqueness Check
            if existing_draft_texts:
                is_unique = check_batch_uniqueness(email_body, existing_draft_texts, threshold=0.45)
                if not is_unique:
                    violations = ["Draft is too similar to another message in this batch. Use a different angle."]
                    logger.warning(f"Batch uniqueness failed for {contact.company} (attempt {attempt}/{max_attempts})")
                    continue

            # All checks passed!
            passed_validation = True
            violations = []
            break

        hook = result.get("hook", "")
        source_facts = result.get("source_facts_used", dossier.verifiable_facts[:1])
        needs_review = result.get("needs_manual_review", False) or not dossier.has_strong_hook

        # If 3 attempts failed, mark draft as FLAGGED
        if not passed_validation:
            draft_status = DraftStatus.FLAGGED
            contact_status = ContactStatus.NEEDS_MANUAL_REVIEW
            logger.error(f"Draft for {contact.company} FLAGGED after 3 failed attempts: {violations}")
        elif needs_review:
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
            wa_msg = f"{greeting}! Loved seeing {contact.company} on Maps. Noticed you don't have an online booking link yet—I built a simple 1-click booking tool for local businesses. Mind if I share a 30-sec preview?"
        # Ensure under 50 words
        wa_words = wa_msg.split()
        if len(wa_words) > 50:
            wa_msg = " ".join(wa_words[:48]) + "..."

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
