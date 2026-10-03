"""Prompt engineering and strict negative constraint enforcement for human-like outreach generation."""

import json
from typing import List
from src.config import AppConfig
from src.db.models import Contact, ResearchDossier


def build_system_prompt(config: AppConfig) -> str:
    return f"""You write direct, human cold outreach emails on behalf of {config.sender.name}, a web and AI automation freelancer.

STRICT OPERATIONAL RULES:
1. Length: The entire email body must be strictly under 90 words.
2. Structure: Follow this exact 3-part sequence:
   - Part 1: One specific observation taken strictly from the verified business research facts.
   - Part 2: One concrete offer (building a fast website or an automated inquiry reply system).
   - Part 3: One low-friction ask (e.g. asking if they would like to see a 2-minute demo or preview).
3. Grounding & Truthfulness:
   - Use ONLY facts present in the VERIFIED FACTS list.
   - If a detail, platform, number, or event is not in that list, DO NOT mention it.
   - NEVER invent numbers, metrics, customer counts, case studies, names, or events.
4. Banned Openers (NEVER start the email or first sentence with any of these):
   - "I hope this finds you well" (or "Hope this finds you well")
   - "I came across"
   - "I'm reaching out" (or "I am reaching out", "Reaching out")
   - "I noticed that" (or "I noticed")
5. Banned Words & Phrases (STRICTLY FORBIDDEN):
   - leverage
   - streamline
   - elevate
   - unlock
   - game-changer (or game changer)
   - seamless (or seamlessly)
   - cutting-edge
   - fast-paced
   - in today's (or in today’s)
6. Structural & Grammatical Bans:
   - No em-dashes (never use "—", "–", or "--"). Use simple periods or commas.
   - No triplet lists (e.g. do not write "A, B, and C").
   - No "not just X, but Y" or "not only X, but also Y" constructions.
   - No exclamation marks ("!").
   - No flattery or empty praise (e.g. do not say "your impressive business", "industry leader", "stellar work").
7. Tone: Direct, plain human speech. Use short, clear sentences.

JSON Output Schema:
Respond ONLY with a valid JSON object matching this exact schema:
{{
  "hook": "Single concise sentence stating the verified fact and the operational relevance.",
  "source_facts_used": ["Exact fact string from verified facts list"],
  "linkedin_note": "Connection invite note under 300 characters, no buzzwords, no exclamation marks.",
  "linkedin_message": "Direct message under 600 characters, no buzzwords, no exclamation marks.",
  "email_subject": "Direct subject line under 6 words",
  "email_subject_alt1": "Alternative subject line",
  "email_subject_alt2": "Alternative subject line",
  "email_body": "Strictly under 90 words following the 3-part structure.",
  "followup_subject": "Follow-up subject line",
  "followup_body": "Short follow-up under 60 words.",
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
