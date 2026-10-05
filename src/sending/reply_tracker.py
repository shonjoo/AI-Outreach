"""Reply thread poller, Gemini intent classifier, and lead alert dispatcher."""

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from src.config import AppConfig
from src.db.database import Database
from src.db.models import Contact, ContactStatus, SendLog
from src.generation.llm_client import GeminiQuotaError, _is_quota_error
from src.sending.gmail_client import GmailClient
from src.sending.suppression import SuppressionManager

logger = logging.getLogger(__name__)

# Canonical Reply Intents
INTENT_INTERESTED = "INTERESTED"
INTENT_PRICE_QUESTION = "PRICE_QUESTION"
INTENT_NOT_NOW = "NOT_NOW"
INTENT_UNSUBSCRIBE = "UNSUBSCRIBE"

VALID_INTENTS = {
    INTENT_INTERESTED,
    INTENT_PRICE_QUESTION,
    INTENT_NOT_NOW,
    INTENT_UNSUBSCRIBE,
}

SYSTEM_INSTRUCTION = (
    "You are an expert sales outreach assistant analyzing incoming prospect email replies.\n"
    "Categorize the prospect's reply into EXACTLY ONE of the following 4 intents:\n"
    "1. 'INTERESTED': The prospect expressed curiosity, asked for a preview/demo, proposed meeting times, or wants to learn more.\n"
    "2. 'PRICE_QUESTION': The prospect specifically asked about pricing, costs, rates, or packages.\n"
    "3. 'NOT_NOW': The prospect says they are busy, bad timing, or asks to reconnect in a few months/weeks.\n"
    "4. 'UNSUBSCRIBE': The prospect says no, stop emailing, remove me, unsubscribe, not interested, or hostile opt-out.\n\n"
    "Respond ONLY with a JSON object in this exact schema:\n"
    "{\"intent\": \"INTERESTED\" | \"PRICE_QUESTION\" | \"NOT_NOW\" | \"UNSUBSCRIBE\", \"confidence\": float between 0.0 and 1.0, \"summary\": \"1-sentence summary\"}"
)


class ReplyTracker:
    def __init__(
        self,
        config: AppConfig,
        db: Database,
        gmail_client: Optional[GmailClient] = None,
        suppression_manager: Optional[SuppressionManager] = None,
        webhook_url: Optional[str] = None,
    ):
        self.config = config
        self.db = db
        self.gmail = gmail_client or GmailClient(config)
        self.suppression = suppression_manager or SuppressionManager(db)
        self.webhook_url = webhook_url or config.lead_alert_webhook_url or os.getenv("LEAD_ALERT_WEBHOOK_URL")

        self.gemini_client = None
        self._init_gemini_client()

    def _init_gemini_client(self):
        api_key = self.config.llm.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI client in ReplyTracker: {e}")

    def _get_candidate_models(self) -> List[str]:
        configured = getattr(self.config.llm, "model", None) or "gemini-flash-lite-latest"
        candidates = [configured, "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
        seen = set()
        return [m for m in candidates if not (m in seen or seen.add(m))]

    def classify_intent_deterministic(self, reply_text: str) -> Dict[str, Any]:
        """
        Regex and keyword-based fallback intent classifier.
        Used when LLM quotas are exhausted or offline.
        """
        text = reply_text.strip().lower()

        # 1. Opt-out / Unsubscribe patterns
        unsub_patterns = [
            r"\bunsubscribe\b",
            r"\bremove\s+me\b",
            r"\bstop\s+emailing\b",
            r"\bnot\s+interested\b",
            r"\bdo\s+not\s+contact\b",
            r"\btake\s+me\s+off\b",
            r"\bspam\b",
            r"\bleave\s+me\s+alone\b",
            r"\bwrong\s+person\b",
            r"\bno\s+thanks?\b",
        ]
        if any(re.search(p, text) for p in unsub_patterns):
            return {
                "intent": INTENT_UNSUBSCRIBE,
                "confidence": 0.95,
                "summary": "Prospect requested to opt out or stated no interest.",
            }

        # 2. Price / Cost questions
        price_patterns = [
            r"\bprice\b",
            r"\bpricing\b",
            r"\bcost\b",
            r"\bhow\s+much\b",
            r"\brate\b",
            r"\bquote\b",
            r"\bfee\b",
            r"\bbudget\b",
            r"\bpackages?\b",
        ]
        if any(re.search(p, text) for p in price_patterns):
            return {
                "intent": INTENT_PRICE_QUESTION,
                "confidence": 0.90,
                "summary": "Prospect asked about pricing or service rates.",
            }

        # 3. Not Now / Bad timing
        not_now_patterns = [
            r"\bnot\s+now\b",
            r"\bnext\s+(?:quarter|month|year)\b",
            r"\btoo\s+busy\b",
            r"\bfollow\s+up\s+in\b",
            r"\breach\s+out\s+later\b",
            r"\blater\s+in\b",
            r"\bcheck\s+back\b",
        ]
        if any(re.search(p, text) for p in not_now_patterns):
            return {
                "intent": INTENT_NOT_NOW,
                "confidence": 0.85,
                "summary": "Prospect indicated bad timing and requested follow up later.",
            }

        # 4. Interested / Call / Preview patterns
        interested_patterns = [
            r"\byes\b",
            r"\bsure\b",
            r"\binterested\b",
            r"\bpreview\b",
            r"\bdemo\b",
            r"\bshow\s+me\b",
            r"\bsend\s+(?:it|more|over|details)\b",
            r"\bcall\b",
            r"\bmeeting\b",
            r"\bchat\b",
            r"\btime\b",
            r"\bschedule\b",
            r"\bsounds\s+good\b",
            r"\blet'?s\s+(?:talk|connect|see)\b",
        ]
        if any(re.search(p, text) for p in interested_patterns):
            return {
                "intent": INTENT_INTERESTED,
                "confidence": 0.85,
                "summary": "Prospect expressed interest in seeing a preview or connecting.",
            }

        # Default fallback if ambiguous
        return {
            "intent": INTENT_INTERESTED,
            "confidence": 0.50,
            "summary": "Prospect replied to email thread.",
        }

    def classify_intent(self, reply_text: str) -> Dict[str, Any]:
        """
        Classifies incoming reply using Gemini fallback sequence,
        defaulting gracefully to deterministic classifier.
        """
        if not reply_text or not reply_text.strip():
            return {
                "intent": INTENT_NOT_NOW,
                "confidence": 0.0,
                "summary": "Empty reply text.",
            }

        prompt = f"PROSPECT REPLY TEXT:\n\"\"\"{reply_text.strip()}\"\"\""

        if self.gemini_client:
            last_err = None
            for model_name in self._get_candidate_models():
                try:
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={
                            "system_instruction": SYSTEM_INSTRUCTION,
                            "response_mime_type": "application/json",
                            "temperature": 0.1,
                        },
                    )
                    text = response.text or ""
                    parsed = self._parse_json(text)
                    intent = str(parsed.get("intent", "")).upper()
                    if intent in VALID_INTENTS:
                        return {
                            "intent": intent,
                            "confidence": float(parsed.get("confidence", 0.9)),
                            "summary": str(parsed.get("summary", "Classified reply.")),
                        }
                except Exception as e:
                    last_err = e
                    if _is_quota_error(e):
                        logger.warning(
                            f"Quota hit on intent classifier with '{model_name}': {e}. Trying next model..."
                        )
                        continue
                    logger.warning(f"Error on intent classifier with '{model_name}': {e}. Trying next model...")

            if last_err and _is_quota_error(last_err):
                logger.warning("All Gemini quota exhausted for intent classifier. Falling back to deterministic classifier.")
            elif last_err:
                logger.warning(f"All Gemini models failed for intent classifier ({last_err}). Falling back to deterministic classifier.")

        return self.classify_intent_deterministic(reply_text)

    def _parse_json(self, raw_text: str) -> Dict[str, Any]:
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
            return {}

    def handle_classified_reply(
        self,
        contact: Contact,
        reply_text: str,
        classification: Dict[str, Any],
    ) -> ContactStatus:
        """
        Executes immediate actions based on classified intent:
        - UNSUBSCRIBE: adds to suppression list, marks OPTED_OUT
        - NOT_NOW: marks FOLLOW_UP_LATER
        - PRICE_QUESTION: marks REPLIED, sends alert
        - INTERESTED: marks HOT_LEAD / REPLIED, sends alert
        """
        intent = classification.get("intent", INTENT_INTERESTED)
        summary = classification.get("summary", "")

        logger.info(
            f"Handling reply from {contact.email} ({contact.company}): Intent={intent} | Summary='{summary}'"
        )

        if intent == INTENT_UNSUBSCRIBE:
            self.suppression.suppress_contact(contact.email, reason="prospect_reply_opt_out")
            new_status = ContactStatus.OPTED_OUT
            self.db.update_contact_status(contact.id, new_status)
            return new_status

        elif intent == INTENT_NOT_NOW:
            new_status = ContactStatus.FOLLOW_UP_LATER
            self.db.update_contact_status(contact.id, new_status)
            return new_status

        elif intent == INTENT_PRICE_QUESTION:
            new_status = ContactStatus.REPLIED
            self.db.update_contact_status(contact.id, new_status)
            self._send_lead_webhook(contact, classification, reply_text)
            return new_status

        else:  # INTENT_INTERESTED
            new_status = ContactStatus.HOT_LEAD
            self.db.update_contact_status(contact.id, new_status)
            self._send_lead_webhook(contact, classification, reply_text)
            return new_status

    def _send_lead_webhook(
        self,
        contact: Contact,
        classification: Dict[str, Any],
        reply_text: str,
    ) -> bool:
        """Dispatches JSON POST webhook alert if configured."""
        webhook_url = self.webhook_url
        if not webhook_url:
            logger.info("No LEAD_ALERT_WEBHOOK_URL configured. Webhook alert skipped.")
            return False

        payload = {
            "event": "lead_reply_detected",
            "contact_id": contact.id,
            "full_name": contact.full_name,
            "first_name": contact.first_name,
            "company": contact.company,
            "email": contact.email,
            "intent": classification.get("intent"),
            "confidence": classification.get("confidence"),
            "summary": classification.get("summary"),
            "reply_snippet": reply_text[:300],
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "AlmostNormalOutreach/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                logger.info(f"Webhook alert dispatched for {contact.email}. Status: {resp.status}")
                return True
        except Exception as e:
            logger.warning(f"Failed to deliver lead alert webhook to {webhook_url}: {e}")
            return False

    def poll_replies(self, force_dry_run: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Polls active threads from send_logs where status in ('SENT', 'SIMULATED'),
        inspects Gmail threads, classifies incoming prospect replies, and applies actions.
        Returns a list of processed reply summaries.
        """
        is_dry_run = self.config.dry_run if force_dry_run is None else force_dry_run
        results = []

        logs = self.db.list_send_logs(limit=100)
        # Filter logs for emails sent with a thread ID
        active_logs = [l for l in logs if l.status in ("SENT", "SIMULATED") and l.gmail_thread_id]

        seen_contacts = set()

        for log in active_logs:
            if log.contact_id in seen_contacts:
                continue
            seen_contacts.add(log.contact_id)

            contact = self.db.get_contact(log.contact_id)
            if not contact or contact.status in (ContactStatus.OPTED_OUT, ContactStatus.REPLIED, ContactStatus.HOT_LEAD):
                continue

            # Query thread from Gmail
            success, messages, err = self.gmail.get_thread_messages(log.gmail_thread_id, dry_run=is_dry_run)
            if not success or not messages:
                continue

            # Look for an incoming reply from recipient (not from sender)
            recipient_email = contact.email.strip().lower()
            incoming_reply = None

            for msg in messages:
                # Check headers or snippet for reply from prospect
                snippet = msg.get("snippet", "")
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])
                from_hdr = next((h["value"] for h in headers if h.get("name", "").lower() == "from"), "")

                if recipient_email in from_hdr.lower() or (snippet and not from_hdr and len(messages) > 1):
                    incoming_reply = snippet
                    break

            if incoming_reply:
                classification = self.classify_intent(incoming_reply)
                updated_status = self.handle_classified_reply(contact, incoming_reply, classification)
                results.append({
                    "contact_id": contact.id,
                    "email": contact.email,
                    "intent": classification.get("intent"),
                    "summary": classification.get("summary"),
                    "new_status": updated_status.value,
                })

        return results
