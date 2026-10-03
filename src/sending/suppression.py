"""Suppression list and compliance management (CAN-SPAM / GDPR)."""

from src.db.database import Database


class SuppressionManager:
    def __init__(self, db: Database):
        self.db = db

    def is_suppressed(self, email: str) -> bool:
        """Checks if recipient is on the suppression list."""
        return self.db.is_suppressed(email)

    def suppress_contact(self, email: str, reason: str = "User requested opt-out"):
        """Adds an email to the permanent suppression list."""
        self.db.add_to_suppression(email, reason=reason)

    def append_opt_out_footer(self, body: str, sender_name: str, sender_email: str) -> str:
        """Appends a clear, compliant opt-out footer."""
        footer = (
            f"\n\n---\n"
            f"Best regards,\n"
            f"{sender_name}\n"
            f"{sender_email}\n\n"
            f"If you'd prefer not to hear from me again, simply reply with 'unsubscribe' "
            f"or let me know, and I will remove you from my list immediately."
        )
        return body.rstrip() + footer
