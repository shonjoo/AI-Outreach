"""Official Gmail API OAuth 2.0 integration and email dispatcher."""

import base64
import email
from email.mime.text import MIMEText
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import AppConfig

logger = logging.getLogger(__name__)

# Scopes needed for sending and reading threads for reply tracking
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.service = None
        self._init_service()

    def _init_service(self):
        """Authenticates with Gmail API using OAuth 2.0 flow."""
        creds = None
        token_path = Path(self.config.google_token_file)
        secret_path = Path(self.config.google_client_secret_file)

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
            except Exception as e:
                logger.warning(f"Error loading existing token: {e}")
        elif os.getenv("GMAIL_TOKEN_JSON"):
            try:
                import json
                creds = Credentials.from_authorized_user_info(json.loads(os.getenv("GMAIL_TOKEN_JSON")), GMAIL_SCOPES)
            except Exception as e:
                logger.warning(f"Error loading token from GMAIL_TOKEN_JSON env var: {e}")

        # If credentials don't exist or are invalid, attempt refresh if possible
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                logger.warning(f"Could not refresh token: {e}")
                creds = None

        if creds and creds.valid:
            try:
                self.service = build("gmail", "v1", credentials=creds)
                logger.info("Successfully authenticated with Gmail API.")
            except Exception as e:
                logger.error(f"Failed to build Gmail service: {e}")

    def authenticate_interactive(self) -> bool:
        """Launches browser OAuth flow to generate a new token.json."""
        secret_path = Path(self.config.google_client_secret_file)
        token_path = Path(self.config.google_token_file)

        if not secret_path.exists():
            logger.error(f"Client secrets file '{secret_path}' not found. Please download from Google Cloud Console.")
            return False

        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            self.service = build("gmail", "v1", credentials=creds)
            return True
        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            return False

    def create_message(self, to_email: str, subject: str, body_text: str) -> Dict[str, str]:
        """Creates standard base64url encoded MIME message."""
        message = MIMEText(body_text, "plain", "utf-8")
        message["to"] = to_email
        message["from"] = f"{self.config.sender.name} <{self.config.sender.email}>"
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return {"raw": raw}

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        dry_run: bool = True,
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Dispatches email.
        Returns: (success: bool, message_id: str, thread_id: str, error_msg: str)
        """
        # If dry-run mode is enabled:
        if dry_run or self.config.dry_run:
            mock_msg_id = f"dryrun-msg-{abs(hash(to_email + subject)) % 1000000}"
            mock_thread_id = f"dryrun-thd-{abs(hash(to_email)) % 1000000}"
            logger.info(
                f"[DRY-RUN] Simulated send to {to_email} | Subject: '{subject}' | Message ID: {mock_msg_id}"
            )
            return True, mock_msg_id, mock_thread_id, None

        if not self.service:
            err = "Gmail API service is not authenticated. Please run OAuth setup or enable dry-run mode."
            logger.error(err)
            return False, None, None, err

        try:
            msg_payload = self.create_message(to_email, subject, body_text)
            sent = self.service.users().messages().send(userId="me", body=msg_payload).execute()
            msg_id = sent.get("id")
            thread_id = sent.get("threadId")
            logger.info(f"Email sent successfully to {to_email}! Message ID: {msg_id}")
            return True, msg_id, thread_id, None
        except Exception as e:
            err = f"Failed to send email via Gmail API: {e}"
            logger.error(err)
            return False, None, None, err

    def get_thread_messages(
        self,
        thread_id: str,
        dry_run: bool = True,
    ) -> Tuple[bool, list, Optional[str]]:
        """
        Retrieves messages in a thread from Gmail API.
        Returns: (success: bool, messages: list, error_msg: Optional[str])
        """
        if dry_run or self.config.dry_run:
            logger.info(f"[DRY-RUN] Simulated fetching thread {thread_id}")
            return True, [], None

        if not self.service:
            err = "Gmail API service is not authenticated. Please run OAuth setup or enable dry-run mode."
            logger.error(err)
            return False, [], err

        try:
            thread = self.service.users().threads().get(userId="me", id=thread_id).execute()
            messages = thread.get("messages", [])
            return True, messages, None
        except Exception as e:
            err = f"Failed to fetch thread {thread_id} via Gmail API: {e}"
            logger.error(err)
            return False, [], err
