#!/usr/bin/env python3
"""
CLI helper for b2b-outreach-pipeline skill.
Provides discrete, file-backed subcommands for every stage of the B2B outreach lifecycle.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.db.csv_importer import import_contacts_to_db, parse_any_lead_file
from src.db.database import Database
from src.db.models import ContactStatus, DraftStatus
from src.generation.generator import DraftGenerator
from src.generation.llm_client import GeminiQuotaError
from src.generation.validator import validate_draft
from src.generation.uniqueness import check_batch_uniqueness
from src.research.dossier import DossierBuilder
from src.sending.reply_tracker import ReplyTracker
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("pipeline_runner")


def write_json_output(data: dict, output_path: str):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"Success! Output written to: {p}")


def cmd_import(args):
    config = load_config()
    db = Database(config.db_path, config=config)
    input_file = Path(args.file)
    if not input_file.exists():
        logger.error(f"File not found: {input_file}")
        sys.exit(1)

    file_bytes = input_file.read_bytes()
    contacts = parse_any_lead_file(file_bytes, input_file.name, target_sheet=args.sheet)
    imported = import_contacts_to_db(db, contacts)
    write_json_output({
        "status": "success",
        "command": "import",
        "file": str(input_file),
        "parsed_count": len(contacts),
        "imported_count": imported,
        "backend": db.backend_name,
    }, args.output)


def cmd_research(args):
    config = load_config()
    db = Database(config.db_path, config=config)
    builder = DossierBuilder()

    contacts = db.list_contacts(ContactStatus.PENDING_RESEARCH)
    limit = args.limit if args.limit > 0 else len(contacts)
    to_process = contacts[:limit]

    processed = []
    for c in to_process:
        dossier = builder.build_dossier(c)
        db.save_dossier(dossier)
        processed.append({
            "contact_id": c.id,
            "company": c.company,
            "facts_count": len(dossier.verifiable_facts),
            "opportunities_count": len(dossier.detected_opportunities),
            "has_hook": dossier.has_strong_hook,
        })

    write_json_output({
        "status": "success",
        "command": "research",
        "researched_count": len(processed),
        "items": processed,
    }, args.output)


def cmd_generate(args):
    config = load_config()
    db = Database(config.db_path, config=config)
    generator = DraftGenerator(config, db)

    contacts = db.list_contacts()
    unprocessed = [c for c in contacts if not db.get_draft(c.id)]
    limit = args.limit if args.limit > 0 else len(unprocessed)
    to_process = unprocessed[:limit]

    generated = []
    quota_hit = False
    for c in to_process:
        dossier = db.get_dossier(c.id)
        if not dossier:
            dossier = DossierBuilder().build_dossier(c)
            db.save_dossier(dossier)
        try:
            draft = generator.generate_for_contact(c, dossier)
            generated.append({
                "contact_id": c.id,
                "email": c.email,
                "status": draft.status.value,
                "email_subject": draft.email_subject,
            })
        except GeminiQuotaError:
            logger.warning("Gemini API rate/quota limit reached. Stopping batch safely.")
            quota_hit = True
            break
        except Exception as e:
            logger.error(f"Error generating draft for {c.email}: {e}")

    write_json_output({
        "status": "partial_success" if quota_hit else "success",
        "command": "generate",
        "generated_count": len(generated),
        "quota_hit": quota_hit,
        "items": generated,
    }, args.output)


def cmd_audit(args):
    config = load_config()
    db = Database(config.db_path, config=config)
    drafts = db.list_all_drafts()

    flagged = []
    clean = []
    for cid, draft in drafts.items():
        v_res = validate_draft(draft.email_body)
        if not v_res.is_valid:
            flagged.append({
                "draft_id": draft.id,
                "contact_id": cid,
                "errors": v_res.errors,
            })
        else:
            clean.append(draft.id)

    write_json_output({
        "status": "success",
        "command": "audit",
        "total_audited": len(drafts),
        "clean_count": len(clean),
        "flagged_count": len(flagged),
        "flagged_items": flagged,
    }, args.output)


def cmd_dispatch(args):
    config = load_config()
    db = Database(config.db_path, config=config)
    sender = OutreachSender(config, db)

    sent_count = 0
    skipped_count = 0
    results = []

    for contact in db.list_contacts(ContactStatus.APPROVED):
        draft = db.get_draft(contact.id)
        if not draft or draft.status != DraftStatus.APPROVED:
            continue

        success, msg = sender.send_approved_email(
            contact=contact,
            draft=draft,
            force_dry_run=args.dry_run,
        )
        if success:
            sent_count += 1
        else:
            skipped_count += 1

        results.append({
            "contact_id": contact.id,
            "recipient": contact.email,
            "success": success,
            "message": msg,
            "dry_run": args.dry_run,
        })

    write_json_output({
        "status": "success",
        "command": "dispatch",
        "mode": "dry-run" if args.dry_run else "live",
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "results": results,
    }, args.output)


def cmd_track_replies(args):
    config = load_config()
    db = Database(config.db_path, config=config)
    tracker = ReplyTracker(config, db)

    results = tracker.poll_and_process_replies(max_threads=args.limit)
    write_json_output({
        "status": "success",
        "command": "track-replies",
        "processed_count": len(results),
        "replies": results,
    }, args.output)


def main():
    parser = argparse.ArgumentParser(description="B2B Outreach Pipeline Helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # import
    p_import = subparsers.add_parser("import", help="Import contacts from Excel or CSV")
    p_import.add_argument("--file", required=True, help="Path to Excel (.xlsx) or CSV file")
    p_import.add_argument("--sheet", default=None, help="Target Excel sheet name")
    p_import.add_argument("--output", required=True, help="Path to write JSON summary output")
    p_import.set_defaults(func=cmd_import)

    # research
    p_research = subparsers.add_parser("research", help="Crawl websites and build fact dossiers")
    p_research.add_argument("--limit", type=int, default=10, help="Max contacts to research (0 for all)")
    p_research.add_argument("--output", required=True, help="Path to write JSON summary output")
    p_research.set_defaults(func=cmd_research)

    # generate
    p_generate = subparsers.add_parser("generate", help="Generate drafts with Gemini multi-model failover")
    p_generate.add_argument("--limit", type=int, default=10, help="Max drafts to generate (0 for all)")
    p_generate.add_argument("--output", required=True, help="Path to write JSON summary output")
    p_generate.set_defaults(func=cmd_generate)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit drafts against negative constraints and anti-slop rules")
    p_audit.add_argument("--output", required=True, help="Path to write JSON summary output")
    p_audit.set_defaults(func=cmd_audit)

    # dispatch
    p_dispatch = subparsers.add_parser("dispatch", help="Send approved emails with safeguards and limits")
    p_dispatch.add_argument("--dry-run", action="store_true", help="Simulate sends without hitting live Gmail API")
    p_dispatch.add_argument("--output", required=True, help="Path to write JSON summary output")
    p_dispatch.set_defaults(func=cmd_dispatch)

    # track-replies
    p_track = subparsers.add_parser("track-replies", help="Poll Gmail threads, classify intent, and fire alerts")
    p_track.add_argument("--limit", type=int, default=20, help="Max threads to poll")
    p_track.add_argument("--output", required=True, help="Path to write JSON summary output")
    p_track.set_defaults(func=cmd_track_replies)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
