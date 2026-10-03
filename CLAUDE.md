# AI Outreach Intelligence Platform: Claude / Developer Handbook

> **Project:** Autonomous Cold Outreach & Lead Intelligence Platform  
> **Repository:** [`github.com/shonjoo/AI-Outreach`](https://github.com/shonjoo/AI-Outreach) (`main`)  
> **Status:** 100% Cloud-Native (Supabase + Streamlit Cloud + GitHub Actions)

---

## 1. System Overview & Core Philosophy
This platform automates personalized B2B cold outreach while eliminating "AI Slop". It conducts autonomous prospect research, compiles structured dossiers, generates personalized emails adhering to strict negative constraints (100–150 words, no buzzwords, no clichés, no emojis), requires human review, and dispatches via Gmail with rate-limiting and deliverability safeguards.

---

## 2. Architecture & Modules
- **`src/research/`**:
  - `crawler.py`: Async web scraper extracting company metadata, offerings, and pain points.
  - `web_search.py`: Fallback search for missing or sparse websites.
  - `dossier.py`: Synthesizes raw findings into structured `ResearchDossier` models.
- **`src/generation/`**:
  - `generator.py` & `llm_client.py`: Multi-provider LLM orchestration (Gemini, Claude, GPT).
  - `prompts.py`: Battle-tested cold outreach prompts enforcing observational hooks and low-friction CTAs.
  - `validator.py`: Negative constraints validator (`SlopDetector`). Enforces word bounds and catches forbidden phrases.
  - `uniqueness.py`: Semantic uniqueness checker to prevent repetitive messaging across prospects.
- **`src/db/`**:
  - `database.py`: Unified adapter with automatic backend switching and SQLite fallback.
  - `supabase_db.py`: Direct PostgREST client for live Supabase PostgreSQL cloud database.
  - `csv_importer.py`: Fast parser for `.csv` and `.xlsx` contact lists.
  - `models.py`: Dataclass models (`Contact`, `ResearchDossier`, `Draft`, `SendLog`, `SuppressionEntry`).
- **`src/sending/`**:
  - `gmail_client.py`: Official Gmail API client. Supports local `token.json` or cloud `GMAIL_TOKEN_JSON` env var.
  - `sender.py`: Dispatcher with daily quotas (max 20), randomized delays (90–240s), duplicate prevention, and dry-run toggle.
  - `suppression.py`: Opt-out suppression list management.
  - `reply_tracker.py`: Gmail thread polling for detecting prospect replies.
- **`src/dashboard/app.py`**:
  - Web UI built on Streamlit styled with the **ShadCN UI Zinc Dark** design system.
  - Features KPI metric cards, segmented pill tabs, custom status badges, and physics-based interactive transitions (`cubic-bezier(0.16, 1, 0.3, 1)`) on all clickable elements.

---

## 3. Database State (Supabase Cloud)
- **Host:** `https://sfwjkwzpdlkougwasyxr.supabase.co`
- **Active Backend:** `SupabaseDatabase`
- **Tables:** `contacts`, `research_dossiers`, `drafts`, `send_logs`, `suppression_list`, `daily_send_counter`.
- **Seeded Records:** 12 active prospect profiles, research dossiers, and generated drafts live in the cloud.

---

## 4. Key Commands & Execution
```bash
# 1. Run Unit & Integration Tests (19 tests)
python -m unittest discover tests

# 2. Run Dashboard Locally
streamlit run streamlit_app.py --server.port 8501

# 3. CLI Pipeline Execution
python -m src.cli pipeline --csv path/to/contacts.csv
python -m src.cli research
python -m src.cli generate
python -m src.cli stats
# Note: Sending strictly requires manual approval in the dashboard.


# 4. Migrate Data to Supabase
python scripts/migrate_to_supabase.py
```

---

## 5. Development Principles (`AGENTS.md`)
Follow the **Ponytail (Lazy Senior Dev)** ladder:
1. Does this need to be built at all? (YAGNI)
2. Reuse existing helpers in `src/db/` and `src/generation/`.
3. Standard library first.
4. Minimal code, shortest diffs, no unnecessary abstractions.
5. All non-trivial logic changes must have a runnable test in `tests/`.
