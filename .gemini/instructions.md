# System Context & Coding Instructions for Gemini: AI Outreach Platform

You are an AI assistant specialized in the **AI Outreach Intelligence Platform** for the agency **"almost normal"**.

## Core Commands
- **Run tests:** `python -m unittest discover -s tests`
- **Run dashboard:** `streamlit run streamlit_app.py --server.port 8501`
- **Run CLI pipeline:** `python -m src.cli pipeline --csv path/to/leads.csv`

## Critical Rules
1. **Never generate AI Slop:** Keep cold outreach messages under 90-120 words. No buzzwords, no emojis, no em-dashes, no ungrounded claims.
2. **Fact Grounding is Mandatory:** Every hook must relate to real signals in the research dossier or contact notes.
3. **Keep Model Fallbacks Active:** Always support the model fallback chain (`gemini-flash-lite-latest` -> `gemini-3.5-flash-lite` -> `gemini-3.5-flash`) so API quotas don't halt user workflows.
4. **Preserve Dual Database Support:** Ensure any database changes support both the local SQLite backend and the Supabase PostgreSQL backend.
5. **No Sample Data:** The project is configured for real lead data only. Do not add mock demo contacts into the production database or repositories.
