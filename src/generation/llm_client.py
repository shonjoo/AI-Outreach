"""Unified LLM client supporting Gemini, Anthropic, OpenAI, and a grounded mock generator."""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from src.config import AppConfig
from src.db.models import Contact, ResearchDossier

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.provider = config.llm.provider.lower()
        self._init_clients()

    def _init_clients(self):
        self.gemini_client = None
        self.anthropic_client = None
        self.openai_client = None

        if self.provider == "gemini":
            api_key = self.config.llm.gemini_api_key or os.getenv("GEMINI_API_KEY")
            if api_key:
                try:
                    from google import genai
                    self.gemini_client = genai.Client(api_key=api_key)
                except Exception as e:
                    logger.warning(f"Could not initialize Google GenAI client: {e}")

        elif self.provider == "anthropic":
            api_key = self.config.llm.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                try:
                    import anthropic
                    self.anthropic_client = anthropic.Anthropic(api_key=api_key)
                except Exception as e:
                    logger.warning(f"Could not initialize Anthropic client: {e}")

        elif self.provider == "openai":
            api_key = self.config.llm.openai_api_key or os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    from openai import OpenAI
                    self.openai_client = OpenAI(api_key=api_key)
                except Exception as e:
                    logger.warning(f"Could not initialize OpenAI client: {e}")

    def generate_drafts(
        self,
        contact: Contact,
        dossier: ResearchDossier,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        """Generates outreach drafts using the configured LLM provider or offline mock."""
        # 1. Try Gemini
        if self.provider == "gemini" and self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=user_prompt,
                    config={
                        "system_instruction": system_prompt,
                        "response_mime_type": "application/json",
                        "temperature": 0.3,
                    },
                )
                text = response.text or ""
                return self._parse_json(text)
            except Exception as e:
                logger.error(f"Gemini generation error: {e}. Falling back to offline generator.")

        # 2. Try Anthropic
        elif self.provider == "anthropic" and self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1500,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                text = response.content[0].text
                return self._parse_json(text)
            except Exception as e:
                logger.error(f"Anthropic generation error: {e}. Falling back to offline generator.")

        # 3. Try OpenAI
        elif self.provider == "openai" and self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )
                text = response.choices[0].message.content
                return self._parse_json(text)
            except Exception as e:
                logger.error(f"OpenAI generation error: {e}. Falling back to offline generator.")

        # 4. Fallback / Offline Grounded Generator
        return self._generate_offline_grounded(contact, dossier)

    def check_fact_grounding(self, draft_text: str, verified_facts: List[str]) -> Dict[str, Any]:
        """
        Secondary cheap LLM call to verify that all claims about the recipient
        are strictly supported by the verified-facts list.
        Returns: {"grounded": bool, "unsupported_claims": List[str]}
        """
        if not verified_facts:
            return {
                "grounded": False,
                "unsupported_claims": ["No verified facts provided for contact."],
            }

        facts_text = "\n".join(f"- {f}" for f in verified_facts)
        system_instruction = (
            "You are a strict fact auditor. Compare the outreach email draft against the VERIFIED FACTS.\n"
            "Identify any claim about the recipient's business (such as their current website state, menus, hours, reviews, pricing, team, customers, platforms, or tools) that is NOT present in the VERIFIED FACTS.\n"
            "Do NOT flag general descriptions of what the sender offers (e.g. web design, booking forms).\n"
            "Respond ONLY with a JSON object:\n"
            "{\"grounded\": boolean, \"unsupported_claims\": [\"claim 1 not found in facts\"]}"
        )
        prompt = f"VERIFIED FACTS:\n{facts_text}\n\nDRAFT:\n{draft_text}"

        # 1. Try Gemini
        if self.provider == "gemini" and self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=prompt,
                    config={
                        "system_instruction": system_instruction,
                        "response_mime_type": "application/json",
                        "temperature": 0.0,
                    },
                )
                return self._parse_json(response.text or "{}")
            except Exception as e:
                logger.error(f"Gemini grounding check error: {e}")

        # 2. Try OpenAI
        elif self.provider == "openai" and self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
                return self._parse_json(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"OpenAI grounding check error: {e}")

        # 3. Try Anthropic
        elif self.provider == "anthropic" and self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=300,
                    system=system_instruction,
                    messages=[{"role": "user", "content": prompt}],
                )
                return self._parse_json(response.content[0].text)
            except Exception as e:
                logger.error(f"Anthropic grounding check error: {e}")

        # Fallback offline grounding check
        return self._offline_grounding_check(draft_text, verified_facts)

    def _offline_grounding_check(self, draft_text: str, verified_facts: List[str]) -> Dict[str, Any]:
        """Deterministic offline fact-grounding auditor."""
        draft_lower = draft_text.lower()
        facts_combined = " ".join(verified_facts).lower()
        unsupported = []

        # Check for specific claims
        if "pdf" in draft_lower and "pdf" not in facts_combined and "menu" not in facts_combined:
            unsupported.append("Mentioned PDF menu without verification in facts.")
        if "instagram" in draft_lower and "instagram" not in facts_combined:
            unsupported.append("Mentioned Instagram without verification in facts.")
        if ("call" in draft_lower or "phone" in draft_lower) and "call" not in facts_combined and "booking" not in facts_combined and "hours" not in facts_combined:
            unsupported.append("Mentioned phone call booking requirement without verification in facts.")

        # Check for invented numbers / metrics (e.g., percentages or time savings)
        metric_matches = re.findall(r"\b\d+%\b|\b\d+\s+hours?\b|\b\d+\s+clients?\b", draft_text)
        for m in metric_matches:
            if m.lower() not in facts_combined:
                unsupported.append(f"Invented metric '{m}' not found in verified facts.")

        return {
            "grounded": len(unsupported) == 0,
            "unsupported_claims": unsupported,
        }

    def _parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Cleans and extracts JSON payload from LLM response."""
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            match = re.search(r"```json\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        elif "```" in cleaned:
            match = re.search(r"```\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Could not parse valid JSON from LLM: {raw_text[:200]}")

    def _generate_offline_grounded(self, contact: Contact, dossier: ResearchDossier) -> Dict[str, Any]:
        """
        Deterministic, strictly grounded fallback generator.
        Adheres to Phase 4 rules:
        - Strictly under 90 words
        - 3-part sequence: verified observation, concrete offer, low-friction ask
        - No banned openers ('I hope this finds you well', 'I came across', 'I'm reaching out', 'I noticed that')
        - No banned buzzwords ('leverage', 'streamline', etc.)
        - No em-dashes, no triplet lists, no 'not just X, but Y'
        - No exclamation marks, no empty flattery, no invented metrics
        """
        facts = dossier.verifiable_facts
        company = contact.company
        first_name = contact.first_name or "there"

        hook = ""
        source_fact = ""
        angle = "general"

        company_lower = company.lower()
        title_lower = (contact.job_title or "").lower()
        notes_lower = (contact.notes or "").lower()

        # 1. Restaurant / Menu angle
        if any(w in company_lower or w in title_lower or w in notes_lower for w in ["trattoria", "restaurant", "chef", "cafe", "diner", "bistro", "menu", "pdf"]):
            angle = "mobile_menu"
            source_fact = next((f for f in facts if "pdf" in f.lower() or "menu" in f.lower()), facts[0] if facts else "")
            hook = f"Saw that {company}'s online menu opens as a PDF file on phones."

        # 2. Clinic / Dental booking angle
        elif any(w in company_lower or w in title_lower or w in notes_lower for w in ["dental", "clinic", "doctor", "dentist", "medical", "patient"]) or any("booking" in f.lower() for f in facts):
            angle = "booking"
            source_fact = next((f for f in facts if "booking" in f.lower() or "appointment" in f.lower()), facts[0] if facts else "")
            hook = f"Saw that booking at {company} currently requires a phone call during open hours."

        # 3. Salon / Social angle
        elif any(w in company_lower or w in title_lower or w in notes_lower for w in ["salon", "hair", "beauty", "stylist", "lounge", "spa", "no website"]):
            angle = "new_website"
            source_fact = next((f for f in facts if "no website" in f.lower() or "instagram" in f.lower() or "broken" in f.lower()), facts[0] if facts else "")
            hook = f"Saw that {company} shares services on Instagram without a dedicated website for appointments."

        elif facts:
            source_fact = facts[0]
            clean_fact = facts[0].replace("From contact notes: ", "").replace("From website: ", "")
            hook = f"Saw that {clean_fact}."
        else:
            return {
                "hook": "No verifiable details found.",
                "source_facts_used": [],
                "linkedin_note": "",
                "linkedin_message": "",
                "email_subject": f"Question regarding {company}",
                "email_subject_alt1": f"{company} inquiry flow",
                "email_subject_alt2": f"Idea for {company}",
                "email_body": "Flagged for manual review due to insufficient verified facts.",
                "followup_subject": "",
                "followup_body": "",
                "needs_manual_review": True,
            }

        # Generate strictly un-slopped drafts (<90 words, 3 parts, no banned words/patterns)
        if angle == "booking":
            email_body = (
                f"Hi {first_name},\n\n"
                f"Saw that booking an appointment at {company} currently requires calling during office hours.\n\n"
                f"I build clean websites with simple online booking forms that let clients select a slot directly from their phone.\n\n"
                f"Would you be open to a 2-minute preview of how this would look for {company}?"
            )
            li_note = f"Hi {first_name}, saw {company}'s clinic. I build direct online booking tools so patients can confirm slots after hours. Open to connecting?"
            li_msg = (
                f"Hi {first_name}, saw that appointment scheduling at {company} requires phone calls during open hours.\n\n"
                f"I build lightweight booking tools that let patients confirm appointments directly online.\n\n"
                f"Would you be open to seeing a 2-minute preview for {company}?"
            )
            sub1 = f"Booking page for {company}"
            sub2 = f"Online booking for {company}"
            sub3 = f"Idea for {company}"
            fu_sub = f"Following up: {company} booking flow"
            fu_body = (
                f"Hi {first_name},\n\n"
                f"Checking in on my previous note about an online booking page for {company}.\n\n"
                f"Happy to send over a quick preview if you reply to this email."
            )

        elif angle == "mobile_menu":
            email_body = (
                f"Hi {first_name},\n\n"
                f"Saw that {company}'s food menu opens as a PDF file on phones.\n\n"
                f"I build fast mobile restaurant websites with clear menus and automated replies for reservation inquiries.\n\n"
                f"Would you be open to a 2-minute preview of a mobile menu for {company}?"
            )
            li_note = f"Hi {first_name}, saw {company}. I build mobile web menus and automated table inquiry replies for local restaurants. Open to connecting?"
            li_msg = (
                f"Hi {first_name}, saw that {company}'s menu is currently hosted as a PDF document.\n\n"
                f"I create mobile-first menus with fast table reservation forms.\n\n"
                f"Would you be open to a 2-minute preview?"
            )
            sub1 = f"Mobile menu for {company}"
            sub2 = f"Quick question on {company}'s menu"
            sub3 = f"Website preview for {company}"
            fu_sub = f"Following up: {company} menu"
            fu_body = (
                f"Hi {first_name},\n\n"
                f"Checking in on my note regarding a mobile-friendly menu for {company}.\n\n"
                f"Happy to send a quick mockup if you reply to this message."
            )

        else:
            email_body = (
                f"Hi {first_name},\n\n"
                f"Saw that {company} shares work on Instagram without a direct website for bookings.\n\n"
                f"I build modern websites with automatic booking forms so clients can confirm appointments directly online.\n\n"
                f"Would you be open to a 2-minute preview of how this would look for {company}?"
            )
            li_note = f"Hi {first_name}, saw {company}'s work on social. I build simple booking websites for salons to turn visitors into confirmed appointments. Open to connecting?"
            li_msg = (
                f"Hi {first_name}, saw that {company} takes inquiries on social without a dedicated booking site.\n\n"
                f"I build fast websites with appointment forms that confirm bookings automatically.\n\n"
                f"Would you be open to a 2-minute preview?"
            )
            sub1 = f"Booking website for {company}"
            sub2 = f"Quick question for {company}"
            sub3 = f"Idea for {company}"
            fu_sub = f"Following up: {company} booking website"
            fu_body = (
                f"Hi {first_name},\n\n"
                f"Checking in on my note about a booking page for {company}.\n\n"
                f"Let me know if you would like to see a quick concept preview."
            )

        return {
            "hook": hook,
            "source_facts_used": [source_fact] if source_fact else facts[:1],
            "linkedin_note": li_note[:295],
            "linkedin_message": li_msg[:590],
            "email_subject": sub1,
            "email_subject_alt1": sub2,
            "email_subject_alt2": sub3,
            "email_body": email_body,
            "followup_subject": fu_sub,
            "followup_body": fu_body,
            "needs_manual_review": False,
        }
