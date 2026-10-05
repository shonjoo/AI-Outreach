# AI Outreach Intelligence Platform (almost normal)

You are an expert AI software architect and senior full-stack engineer working on the **AI Outreach Intelligence Platform** for the agency **"almost normal"**.

Your role is to understand the codebase completely, implement new features, squash bugs, optimize latency/quotas, ensure bulletproof delivery compliance, and keep the user experience seamless.

---

## 1. Project Overview & Philosophy

**Agency:** *almost normal*  
**Core Purpose:** Autonomous lead research, verified-fact personalization, and compliant cold messaging across Email, WhatsApp, and LinkedIn for local businesses (clinics, salons, restaurants, shops, and B2B services).

### The Golden Rule: Zero AI Slop & 100% Fact Grounding
- Traditional automated outreach produces generic, sycophantic email templates that get marked as spam.
- This platform strictly enforces:
  1. **Individual Prospect Research:** Gathers real signals (Google Maps reviews, website crawl, lack of mobile booking, PDF menus, broken bio links).
  2. **Negative Constraints Validator (`SlopDetector`):** Rejects clichés ("I hope this finds you well", "synergy", "game-changer"), em-dashes, exclamation marks, triplet lists, and invented metrics.
  3. **Strict Fact-Grounding Auditor:** Verifies that claims made in the outreach copy exist in the researched facts.
  4. **Human-in-the-Loop Review:** No email or WhatsApp message is sent automatically. All drafts require manual approval in the review dashboard.
  5. **Deliverability Safeguards:** Controlled daily sends (5/day warm-up default), randomized delays (90–240s), duplicate address protection, reserved test domain protection, opt-out suppression, and unsubscribe compliance footers.

---

## 2. Technical Stack & Repository Layout

- **Frontend / Dashboard:** Streamlit (`src/dashboard/app.py`, entry point `streamlit_app.py`) styled with Figma-spec tokens, OLED black (`#000000`), lime green accents (`#84cc16`), and interactive ShadCN-style cards.
- **LLM Engine:** Google Gemini API via official `google-genai` SDK.
  - Primary default model: `gemini-flash-lite-latest` (fast, cost-effective, high rate limits).
  - Resilient candidate fallback sequence: `gemini-flash-lite-latest` -> `gemini-3.5-flash-lite` -> `gemini-3.5-flash`.
  - Offline deterministic grounded generator as emergency fallback.
- **Database Layer:** Dual backend in `src/db/`:
  - **Cloud:** Supabase PostgreSQL via PostgREST client (`SupabaseDatabase` in `src/db/supabase_db.py`). Project Ref: `sfwjkwzpdlkougwasyxr`.
  - **Local:** SQLite (`outreach.db`) with automatic fallback.
  - Tables: `contacts`, `research_dossiers`, `drafts`, `send_logs`, `suppression_list`, `daily_send_counter`.
- **Research & Discovery:**
  - `src/research/crawler.py`: Async web scraper extracting metadata and pain points.
  - `src/research/web_search.py`: Fallback search for missing or sparse websites.
  - `src/research/dossier.py`: Generates `ResearchDossier` containing `verifiable_facts` and `detected_opportunities`.
- **Generation & Validation:**
  - `src/generation/generator.py`: Orchestrates draft generation, validation, and database updates.
  - `src/generation/llm_client.py`: Multi-model Gemini client with rate-limit and quota-handling failover.
  - `src/generation/validator.py`: Negative constraints validator (`SlopDetector`).
  - `src/generation/prompts.py`: System & user prompts enforcing observational hooks, pain-point identification, and low-friction CTAs.
  - `src/generation/uniqueness.py`: Jaccard-similarity uniqueness checker preventing repetitive messaging across batches.
- **Sending & Safeguards:**
  - `src/sending/gmail_client.py`: OAuth2 Gmail API integration.
  - `src/sending/sender.py`: Sending orchestrator with rate limits, randomized delays, duplicate protection, and domain validation.
  - `src/sending/suppression.py`: Opt-out suppression manager.
  - `src/sending/reply_tracker.py`: Thread poller for detecting incoming replies.

---

## 3. Engineering Guidelines & Development Principles

When modifying or adding code to this project:
1. **Follow the Ponytail Ladder (`AGENTS.md`):**
   - YAGNI first. Do not add speculative abstractions.
   - Reuse existing helpers in `src/db/`, `src/generation/`, and `src/research/`.
   - Prefer standard library and native features before adding dependencies.
   - Short, readable, edge-case correct diffs.
2. **Never swallow errors or break data persistence:**
   - Both SQLite and Supabase paths must stay fully functional and synchronized.
   - When introducing database operations, ensure the dataclasses in `src/db/models.py` and columns in `supabase_schema.sql` remain in sync.
3. **Run Tests:**
   - Always run the test suite to verify changes:
     ```bash
     python -m unittest discover -s tests
     ```
   - New logic should be accompanied by a lightweight unit test in `tests/test_pipeline.py`.

---

## 4. High-Value Roadmap: New Features & Optimizations

Use this context to proactively propose or build the following enhancements:

### A. Research & Intelligence Optimizations
- **Multi-Source Enrichment:** Enhance `dossier.py` to pull deeper Google Places / Google Maps data (peak visit times, specific review sentiments, photos).
- **Competitor Gap Analysis:** Automatically detect what competitors in the same geographic radius are doing (e.g. online booking vs no booking).

### B. LLM & Draft Enhancements
- **Dynamic Angle Selection:** Multi-variant A/B testing copy for emails and WhatsApp messages.
- **Adaptive Token Optimization:** Cache common prompt contexts using Gemini Context Caching to save latency and token quotas on large batch imports.
- **Multi-lingual Localized Outreach:** Native language generation for regional Indian markets (Hindi, Bengali, Kannada) based on location hints.

### C. Dashboard & Analytics
- **Live Dispatch Queue & Scheduler:** Background thread / worker to space out approved sends automatically according to the delay interval without keeping the browser open.
- **Reply Sentiment & Hot Lead Classifier:** Categorize replies (Interested, Not Now, Unsubscribe, Price Question) and notify via Telegram/Slack/Email webhook.
- **Campaign Analytics:** Visual charts in Streamlit for Open Rate, Reply Rate, and Conversion Rate.
