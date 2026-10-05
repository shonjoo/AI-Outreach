---
name: b2b-outreach-pipeline
description: >-
  Autonomous B2B outreach lifecycle orchestrator: Universal Excel/CSV lead import, SSRF-safe technical website signal crawling, fact-grounded Gemini draft generation with automatic failover, negative constraint SlopDetector auditing, dual SQLite/Supabase synchronization, deliverability-safe dispatch (dry-run & live Gmail API), and intent-classified reply tracking with webhook alerts.
---

# B2B Outreach Intelligence Pipeline

## Overview
This skill operates the complete, compliant cold outreach lifecycle for agency **"almost normal"**. It bridges prospect discovery, verifiable dossier research, slop-free copy generation, human review, safe dispatch, and incoming reply intelligence.

## Dependencies
- `supabase`: Schema management, migrations, and PostgREST client synchronization.
- `ponytail`: Senior developer principles: minimal diffs, standard-library first, zero boilerplate.
- `graphify`: Knowledge graph auditing of pipeline dependencies and data models.

## Quick Start
Run an end-to-end simulated cycle:
```bash
# 1. Ingest leads from an Excel or CSV file
python .agents/skills/b2b-outreach-pipeline/scripts/run_pipeline.py import --file leads.xlsx --output results/import.json

# 2. Build verified dossiers for pending contacts
python .agents/skills/b2b-outreach-pipeline/scripts/run_pipeline.py research --limit 5 --output results/research.json

# 3. Generate personalized multi-channel copy (Email, WhatsApp, LinkedIn)
python .agents/skills/b2b-outreach-pipeline/scripts/run_pipeline.py generate --limit 5 --output results/generation.json

# 4. Audit drafts against negative anti-slop constraints
python .agents/skills/b2b-outreach-pipeline/scripts/run_pipeline.py audit --output results/audit.json

# 5. Dispatch approved emails in safe Dry-Run mode
python .agents/skills/b2b-outreach-pipeline/scripts/run_pipeline.py dispatch --dry-run --output results/dispatch.json

# 6. Poll inbox threads and classify incoming replies
python .agents/skills/b2b-outreach-pipeline/scripts/run_pipeline.py track-replies --limit 10 --output results/replies.json
```

## Utility Scripts & Subcommands
The CLI script located at `scripts/run_pipeline.py` provides deterministic execution with mandatory file output (`--output <path>`):

### 1. `import`
Ingests contacts from `.xlsx` or `.csv` files into the active database.
- Arguments:
  - `--file <path>`: Required. Absolute or relative path to lead file.
  - `--sheet <name>`: Optional. Specific sheet name in an Excel workbook.
  - `--output <path>`: Required. Path to write JSON summary.

### 2. `research`
Crawls company websites, extracting technical opportunities (missing online booking, broken PDF menus, slow mobile speed) and verifiable facts.
- Arguments:
  - `--limit <int>`: Max contacts to research. Default `10`. Pass `0` for all.
  - `--output <path>`: Required. Output file path.

### 3. `generate`
Synthesizes drafts across Email (< 120 words), WhatsApp (< 50 words), and LinkedIn using Gemini multi-model failover (`gemini-flash-lite-latest` -> `gemini-3.5-flash-lite` -> `gemini-3.5-flash`).
- Arguments:
  - `--limit <int>`: Max drafts to generate. Default `10`.
  - `--output <path>`: Required. Output file path.

### 4. `audit`
Scans all generated drafts using `SlopDetector` for forbidden phrases ("I hope this finds you well", "synergy", em-dashes, exclamation marks) and computes cross-batch Jaccard uniqueness.
- Arguments:
  - `--output <path>`: Required. Output file path.

### 5. `dispatch`
Dispatches approved messages via OAuth2 Gmail API or simulates them safely.
- Arguments:
  - `--dry-run`: Flag to simulate sends without calling Gmail API.
  - `--output <path>`: Required. Output file path.

### 6. `track-replies`
Polls active email threads, classifies replies into `HOT_LEAD`, `PRICE_QUESTION`, `NOT_NOW`, or `UNSUBSCRIBE`, updates contact statuses, and dispatches real-time webhooks.
- Arguments:
  - `--limit <int>`: Max threads to check. Default `20`.
  - `--output <path>`: Required. Output file path.

## Operational Workflow

```
[Universal Lead File]
       │
       ▼
 [run_pipeline.py import] ──> Contacts Table (SQLite / Supabase)
       │
       ▼
[run_pipeline.py research] ──> Dossiers Table (verifiable_facts, opportunities)
       │
       ▼
[run_pipeline.py generate] ──> Multi-model Gemini failover (< 120 words email)
       │
       ▼
  [run_pipeline.py audit] ──> SlopDetector & Jaccard Uniqueness Validation
       │
       ▼
  [Review Studio Dashboard] ──> Human-in-the-Loop Approval & Manual Editing
       │
       ▼
[run_pipeline.py dispatch] ──> Compliant Send (Daily caps, jitter delay, opt-out check)
       │
       ▼
[run_pipeline.py track-replies] ──> Intent Classification & Webhook Alerts
```

## Safeguards & Compliance Rules
1. **Never Send Automatically:** Every cold message requires manual approval in the review studio before being marked `APPROVED`.
2. **Warm-up Deliverability:** Daily sends default to a 5-email warm-up cap. Delays are randomized between 90 and 240 seconds.
3. **Reserved Domain Block:** Disallow sending to `.example.com`, `.example.org`, `.test`, and `.invalid`.
4. **Opt-Out Permanence:** Unsubscribes are instantly recorded in the suppression list table and permanently blocked from future campaigns.
5. **SSRF Guard:** Web scrapers reject private IP ranges, loopback (`127.0.0.1`), and cloud metadata IP endpoints (`169.254.169.254`).

## Common Pitfalls
- **Running `dispatch` without `--dry-run` in dev:** Always run with `--dry-run` to test pipeline changes without consuming daily email quota.
- **Ignoring Quota Exhaustion:** If Gemini hits a 429 quota error, the runner stops generation gracefully and leaves remaining contacts queued as `PENDING_RESEARCH`.
- **Modifying copy with forbidden punctuation:** Re-introducing em-dashes (`—`) or exclamation marks (`!`) will cause `validate_draft()` to flag the draft and lock the Send button.
