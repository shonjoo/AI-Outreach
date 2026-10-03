# 📬 AI Outreach Intelligence Platform

A human-in-the-loop cold outreach system designed for local business outreach (salons, clinics, shops).

Instead of mass scraping or automated mail-merges, this system:
1. **Researches businesses individually** — analyzes websites, reviews, or Google Maps signals for technical opportunities (e.g. missing online booking).
2. **Generates grounded copy** — produces personalized Email, WhatsApp, and LinkedIn drafts verified against researched facts with strict negative constraints (no clichés, no buzzwords).
3. **Enforces human review** — all messages require approval via an interactive Streamlit dashboard before dispatch.
4. **Safeguards sender reputation** — Gmail API integration with warmup rate limits (5/day default), random jitter delays, duplicate prevention, and opt-out suppression.

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```ini
GEMINI_API_KEY="your-gemini-key"
DRY_RUN="True"
DASHBOARD_PASSWORD="your-secure-password"

# Optional Cloud DB (defaults to local SQLite if omitted)
DB_BACKEND="sqlite"
```

### 3. Launch Dashboard
```bash
streamlit run streamlit_app.py
```
Open **[http://localhost:8501](http://localhost:8501)** to review prospects, edit drafts, and manage dispatch.

---

## 🛠️ Tech Stack & Architecture

- **UI:** Streamlit (Zinc Dark design system)
- **AI / LLM:** Google Gemini API (`gemini-3.8-flash`) with fact-grounding auditor
- **Database:** Supabase (PostgreSQL) in production / SQLite locally
- **Dispatch:** Gmail API (OAuth 2.0) + direct `wa.me` links for WhatsApp

---

## 🧪 Testing

Run the automated test suite:
```bash
python -m unittest discover tests
```

---

## ⚖️ Compliance & Ethics

- Mandatory opt-out footer and automated suppression list.
- Warmup daily send quotas to prevent spam and rate-limit triggers.
- No automated LinkedIn bots or scraping — manual review and 1-click links only.

