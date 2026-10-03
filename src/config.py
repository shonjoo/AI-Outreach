"""Configuration loader and validator for outreach automation."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import yaml
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass
class SenderConfig:
    name: str = "Nillohit Debnath"
    email: str = "nillohitfreelanceco@gmail.com"
    role: str = "Web and AI automation freelancer"
    bio: str = (
        "We build websites and AI automation for small businesses, helping them "
        "get more customers and save time on repetitive work."
    )


@dataclass
class OutreachConfig:
    purpose: str = "sales"
    offer: str = (
        "Professional websites and AI automation (such as automatic replies to "
        "customer questions and bookings) for small local businesses."
    )
    ideal_contact: str = "Owners and managers of small local businesses: shops, salons, clinics, restaurants."
    call_to_action: str = "Ask them to simply reply to the message."


@dataclass
class StyleConfig:
    tone: str = "polite, professional, concise"
    avoid: List[str] = field(
        default_factory=lambda: [
            "I hope this finds you well",
            "synergy",
            "emojis",
            "long introductions",
        ]
    )
    language: str = "English"


@dataclass
class LimitsConfig:
    linkedin_connection_note_chars: int = 300
    linkedin_message_chars: int = 600
    email_words: str = "100-150"
    emails_per_day: int = 20
    delay_between_sends_seconds: List[int] = field(default_factory=lambda: [90, 240])

    @property
    def min_delay(self) -> int:
        return self.delay_between_sends_seconds[0] if self.delay_between_sends_seconds else 90

    @property
    def max_delay(self) -> int:
        return self.delay_between_sends_seconds[1] if len(self.delay_between_sends_seconds) > 1 else 240


@dataclass
class LLMConfig:
    provider: str = "gemini"
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


@dataclass
class AppConfig:
    sender: SenderConfig
    outreach: OutreachConfig
    style: StyleConfig
    limits: LimitsConfig
    llm: LLMConfig
    dry_run: bool = True
    db_path: str = "outreach.db"
    google_client_secret_file: str = "credentials.json"
    google_token_file: str = "token.json"


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Loads configuration from YAML and environment variables."""
    cfg_file = Path(config_path)
    data = {}
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    sender_data = data.get("sender", {})
    sender = SenderConfig(
        name=sender_data.get("name", "Nillohit Debnath"),
        email=sender_data.get("email", "nillohitfreelanceco@gmail.com"),
        role=sender_data.get("role", "Web and AI automation freelancer"),
        bio=sender_data.get("bio", ""),
    )

    outreach_data = data.get("outreach", {})
    outreach = OutreachConfig(
        purpose=outreach_data.get("purpose", "sales"),
        offer=outreach_data.get("offer", ""),
        ideal_contact=outreach_data.get("ideal_contact", ""),
        call_to_action=outreach_data.get("call_to_action", "Ask them to simply reply to the message."),
    )

    style_data = data.get("style", {})
    style = StyleConfig(
        tone=style_data.get("tone", "polite, professional, concise"),
        avoid=style_data.get(
            "avoid",
            ["I hope this finds you well", "synergy", "emojis", "long introductions"],
        ),
        language=style_data.get("language", "English"),
    )

    limits_data = data.get("limits", {})
    limits = LimitsConfig(
        linkedin_connection_note_chars=limits_data.get("linkedin_connection_note_chars", 300),
        linkedin_message_chars=limits_data.get("linkedin_message_chars", 600),
        email_words=str(limits_data.get("email_words", "100-150")),
        emails_per_day=limits_data.get("emails_per_day", 20),
        delay_between_sends_seconds=limits_data.get("delay_between_sends_seconds", [90, 240]),
    )

    llm_data = data.get("llm", {})
    llm = LLMConfig(
        provider=llm_data.get("provider", "gemini"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

    dry_run_env = os.getenv("DRY_RUN", "True").strip().lower()
    dry_run = dry_run_env in ("true", "1", "yes", "t")

    return AppConfig(
        sender=sender,
        outreach=outreach,
        style=style,
        limits=limits,
        llm=llm,
        dry_run=dry_run,
        db_path=os.getenv("DB_PATH", "outreach.db"),
        google_client_secret_file=os.getenv("GOOGLE_CLIENT_SECRET_FILE", "credentials.json"),
        google_token_file=os.getenv("GOOGLE_TOKEN_FILE", "token.json"),
    )
