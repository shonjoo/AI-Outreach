"""Headless CLI interface for outreach automation pipeline."""

import argparse
import csv
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import AppConfig, load_config
from src.db.database import Database
from src.db.models import Contact, ContactStatus, DraftStatus
from src.generation.generator import DraftGenerator
from src.research.dossier import DossierBuilder
from src.sending.gmail_client import GmailClient
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")


def cmd_ingest(args, config: AppConfig, db: Database):
    csv_file = Path(args.csv)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_file}")
        return

    count = 0
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("email"):
                continue
            contact = Contact(
                first_name=row.get("first_name", "").strip(),
                last_name=row.get("last_name", "").strip(),
                company=row.get("company", "").strip(),
                job_title=row.get("job_title", "").strip(),
                linkedin_url=row.get("linkedin_url", "").strip(),
                email=row.get("email", "").strip(),
                notes=row.get("notes", "").strip(),
                website=row.get("website", "").strip(),
            )
            db.insert_contact(contact)
            count += 1
    logger.info(f"Ingested {count} contacts from {csv_file}")


def cmd_research(args, config: AppConfig, db: Database):
    builder = DossierBuilder()
    contacts = db.list_contacts(ContactStatus.PENDING_RESEARCH)
    logger.info(f"Researching {len(contacts)} pending contacts...")
    for c in contacts:
        logger.info(f"Gathering signals for: {c.company} ({c.full_name})")
        dossier = builder.build_dossier(c)
        db.save_dossier(dossier)
        logger.info(f"-> Found {len(dossier.verifiable_facts)} facts, {len(dossier.detected_opportunities)} opportunities")


def cmd_generate(args, config: AppConfig, db: Database):
    generator = DraftGenerator(config, db)
    contacts = db.list_contacts()
    unprocessed = [c for c in contacts if db.get_dossier(c.id) and not db.get_draft(c.id)]
    logger.info(f"Generating drafts for {len(unprocessed)} researched contacts...")
    drafts = generator.batch_generate(unprocessed)
    logger.info(f"Generated {len(drafts)} drafts successfully.")


def cmd_pipeline(args, config: AppConfig, db: Database):
    """Runs ingest -> research -> generate in one workflow."""
    if args.csv:
        cmd_ingest(args, config, db)
    cmd_research(args, config, db)
    cmd_generate(args, config, db)
    cmd_stats(args, config, db)


def cmd_send(args, config: AppConfig, db: Database):
    sender = OutreachSender(config, db)
    contacts = db.list_contacts(ContactStatus.APPROVED)
    logger.info(f"Found {len(contacts)} approved contacts ready for sending.")

    dry_run = args.dry_run or config.dry_run
    mode_label = "DRY-RUN (Simulated)" if dry_run else "LIVE SENDING"
    logger.info(f"Executing in mode: {mode_label}")

    for c in contacts:
        draft = db.get_draft(c.id)
        if not draft:
            continue
        success, msg = sender.send_approved_email(
            contact=c,
            draft=draft,
            force_dry_run=dry_run,
            respect_delay=not dry_run,
        )
        logger.info(msg)


def cmd_stats(args, config: AppConfig, db: Database):
    contacts = db.list_contacts()
    today_count = db.get_today_sent_count()
    limit = config.limits.emails_per_day
    suppressed = db.list_suppressed()

    print("\n" + "=" * 55)
    print(" 📊 OUTREACH PIPELINE OVERVIEW")
    print("=" * 55)
    print(f" Total Contacts:            {len(contacts)}")
    print(f" Daily Sending Progress:    {today_count} / {limit} emails")
    print(f" Suppressed Contacts:       {len(suppressed)}")
    print("-" * 55)

    status_counts = {}
    for c in contacts:
        status_counts[c.status.value] = status_counts.get(c.status.value, 0) + 1

    for status, count in sorted(status_counts.items()):
        print(f"  • {status:<24}: {count}")
    print("=" * 55 + "\n")


def cmd_auth(args, config: AppConfig, db: Database):
    """Initializes interactive OAuth flow for Gmail API."""
    gmail = GmailClient(config)
    success = gmail.authenticate_interactive()
    if success:
        logger.info("Gmail OAuth authentication successful! token.json saved.")
    else:
        logger.error("OAuth authentication failed. Ensure credentials.json is present in the workspace.")


def main():
    parser = argparse.ArgumentParser(description="Personalized Outreach Automation CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Pipeline
    p_pipe = subparsers.add_parser("pipeline", help="Run full pipeline: ingest -> research -> generate")
    p_pipe.add_argument("--csv", required=True, help="Path to contacts CSV")

    # Ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest contacts CSV into database")
    p_ingest.add_argument("--csv", required=True, help="Path to contacts CSV")

    # Research
    subparsers.add_parser("research", help="Run web research on pending contacts")

    # Generate
    subparsers.add_parser("generate", help="Generate drafts for researched contacts")

    # Send
    p_send = subparsers.add_parser("send", help="Send approved drafts")
    p_send.add_argument("--dry-run", action="store_true", default=False, help="Force dry-run mode")

    # Stats
    subparsers.add_parser("stats", help="Show pipeline statistics")

    # Auth
    subparsers.add_parser("auth", help="Authenticate with Gmail API OAuth")

    args = parser.parse_args()
    config = load_config()
    db = Database(config.db_path, config=config)

    if args.command == "ingest":
        cmd_ingest(args, config, db)
    elif args.command == "research":
        cmd_research(args, config, db)
    elif args.command == "generate":
        cmd_generate(args, config, db)
    elif args.command == "pipeline":
        cmd_pipeline(args, config, db)
    elif args.command == "send":
        cmd_send(args, config, db)
    elif args.command == "stats":
        cmd_stats(args, config, db)
    elif args.command == "auth":
        cmd_auth(args, config, db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
