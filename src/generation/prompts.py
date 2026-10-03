"""Prompt engineering and strict negative constraint enforcement for human-like outreach generation."""

import json
from typing import List
from src.config import AppConfig
from src.db.models import Contact, ResearchDossier


def build_system_prompt(config: AppConfig) -> str:
    agency_info = f"founder of the agency 'almost normal'"
    return f"""You write warm, human cold outreach on behalf of {config.sender.name}, {agency_info}.

CORE PHILOSOPHY:
You are reaching out to local business owners (clinics, salons, shops, restaurants, local services).
Speak like a helpful, friendly local neighbor—warm, conversational, down-to-earth, and personal—never like a stiff corporate B2B enterprise software salesperson.

STRICT OPERATIONAL RULES:
1. Length:
   - Email Body: Under 100 words (concise, warm, readable on a phone).
   - WhatsApp Message: Strictly under 50 words (casual, quick, friendly).
2. Structure: Follow this 3-part sequence:
   - Part 1: Warm, specific observation from verified business facts (e.g. their stellar Google Maps rating, high review count, or lack of online booking).
   - Part 2: Concrete, simple solution (e.g. a simple 1-click booking link or automated WhatsApp booking reply for clients).
   - Part 3: Low-friction, friendly ask (e.g. asking if they'd like to see a 30-second preview or quick demo).
3. Grounding & Truthfulness:
   - Use ONLY facts present in the VERIFIED FACTS list (ratings, area, website status, review sentiment).
   - NEVER invent fake metrics, customer counts, case studies, or claims.
4. Banned Corporate Openers (DO NOT start with stiff corporate clichés):
   - "I hope this finds you well" (or "Hope this finds you well")
   - "I am reaching out to discuss synergy"
   - "My name is X and I am an enterprise solution provider"
5. Banned Buzzwords (STRICTLY FORBIDDEN):
   - leverage
   - streamline
   - elevate
   - unlock
   - game-changer (or game changer)
   - seamless (or seamlessly)
   - cutting-edge
   - fast-paced
   - in today's (or in today’s)
6. Tone & Style:
   - Friendly, respectful, helpful.
   - For WhatsApp: ultra-concise, casual, direct (under 50 words).
   - Avoid buzzwords, corporate jargon, or aggressive sales pressure.

JSON Output Schema:
Respond ONLY with a valid JSON object matching this exact schema:
{{
  "hook": "Single concise sentence stating the verified fact and operational relevance.",
  "source_facts_used": ["Exact fact string from verified facts list"],
  "linkedin_note": "Connection invite note under 300 characters.",
  "linkedin_message": "Direct message under 600 characters.",
  "whatsapp_message": "Short, friendly, casual WhatsApp message strictly under 50 words.",
  "email_subject": "Direct subject line under 6 words",
  "email_subject_alt1": "Alternative subject line",
  "email_subject_alt2": "Alternative subject line",
  "email_body": "Warm, personal email body under 100 words following the 3-part sequence.",
  "followup_subject": "Follow-up subject line",
  "followup_body": "Short, friendly follow-up under 60 words.",
  "needs_manual_review": false
}}
"""


def build_user_prompt(contact: Contact, dossier: ResearchDossier) -> str:
    facts_formatted = "\n".join(f"- {f}" for f in dossier.verifiable_facts) if dossier.verifiable_facts else "None available"
    opps_formatted = "\n".join(f"- {o}" for o in dossier.detected_opportunities) if dossier.detected_opportunities else "None detected"

    return f"""TARGET CONTACT:
- Full Name: {contact.full_name}
- First Name: {contact.first_name}
- Company: {contact.company}
- Job Title: {contact.job_title}
- LinkedIn: {contact.linkedin_url}
- Email: {contact.email}

VERIFIED BUSINESS RESEARCH FACTS:
{facts_formatted}

KEY IDENTIFIED OPPORTUNITIES:
{opps_formatted}

USER PASTED NOTES/POSTS:
{dossier.user_pasted_content or 'None'}

Generate the outreach package.
Remember:
- email_body must be strictly under 90 words.
- One specific observation from verified facts, one concrete offer, one low-friction ask.
- Zero banned openers, zero buzzwords, zero em-dashes, zero exclamation marks, zero triplet lists.
- If verified facts are insufficient, set needs_manual_review to true.
"""
