# 📬 Personalized Outreach Automation Platform

An intelligent, ethical cold outreach system designed for freelancers and agencies offering websites and AI automation to small local businesses (dental clinics, restaurants, hair salons, boutique shops).

Instead of generic spam or robotic mail-merges, this system:
1. **Researches each business individually** (crawling their website for technical gaps like lack of 24/7 online booking, PDF-only menus, or mobile responsiveness issues, and checking public review sentiment).
2. **Crafts grounded, highly personalized outreach drafts** with a single verifiable hook, polite tone, strict length limits, and zero fluff or emojis.
3. **Presents everything in a visual Review Dashboard** (Streamlit) for you to edit, approve, regenerate, or skip.
4. **Automates email sending via the official Gmail API** with rate limits (max 20/day), organic delays between sends (90–240s), duplicate-send prevention, and one-click suppression/opt-out.
5. **Keeps your LinkedIn account safe**: Zero automated scraping or bot sending (which risks account ban). Provides 1-click **Copy Message** and **Open Profile** buttons for effortless manual outreach.

---

## 📋 Table of Contents
- [Quick Start in 3 Steps](#-quick-start-in-3-steps)
- [How to Get Your Gemini API Key](#-how-to-get-your-gemini-api-key)
- [How to Set Up Gmail API (OAuth 2.0)](#-how-to-set-up-gmail-api-oauth-20)
- [How to Use the Review Dashboard](#-how-to-use-the-review-dashboard)
- [Compliance & Best Practices (CAN-SPAM / GDPR)](#-compliance--best-practices-can-spam--gdpr)
- [Command Line Reference](#-command-line-reference)
- [Architecture & File Structure](#-architecture--file-structure)

---

## ⚡ Quick Start in 3 Steps

You don't need deep technical knowledge to run this project. Follow these 3 simple steps:

### Step 1: Open Terminal and Navigate to the Project
```bash
cd /Users/sanjanasengupta/Documents/antigravity/adventurous-galileo
```

### Step 2: Set Up Your Configuration & Secrets
Copy the environment template:
```bash
cp .env.example .env
```
Open `.env` in any text editor and paste your **Gemini API key**:
```ini
GEMINI_API_KEY="your-gemini-api-key-here"
DRY_RUN="True"
```
*(By default, `DRY_RUN="True"` is turned on. In Dry-Run mode, all research, personalization, and sending simulations happen without sending real emails.)*

### Step 3: Launch the Dashboard
Run:
```bash
./run.sh dashboard
```
This automatically sets up the Python environment, installs all required packages, and opens your review dashboard at:
👉 **[http://localhost:8501](http://localhost:8501)**

In the dashboard, click **"Load Sample Contacts"** to see 3 pre-built realistic local businesses (Dental Clinic, Italian Restaurant, Hair Salon).

---

## 🔑 How to Get Your Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click on **"Get API key"** in the left sidebar.
4. Click **"Create API key"** (select or create a Google Cloud project).
5. Copy the generated key string.
6. Paste it into your `.env` file:
   ```ini
   GEMINI_API_KEY="AIzaSy..."
   ```

*(Note: The system also includes an intelligent offline grounded generator, so you can test the entire pipeline immediately even before adding your API key!)*

---

## ✉️ How to Set Up Gmail API (OAuth 2.0)

To send approved emails from your official account (`nillohitfreelanceco@gmail.com`), set up Google OAuth:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Freelance-Outreach`).
3. Enable the **Gmail API**:
   - In the search bar at the top, type `Gmail API` and click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Go to **APIs & Services > OAuth consent screen**.
   - Choose **External** (or Internal if using Google Workspace) and click **Create**.
   - App Name: `Outreach Tool`
   - User Support Email: `nillohitfreelanceco@gmail.com`
   - Under **Test Users**, add: `nillohitfreelanceco@gmail.com`
   - Click **Save and Continue**.
5. Create OAuth Credentials:
   - Go to **APIs & Services > Credentials**.
   - Click **+ CREATE CREDENTIALS** > **OAuth client ID**.
   - Application type: **Desktop app**.
   - Name: `Outreach Desktop Client`.
   - Click **Create**.
6. Download the Client Secret:
   - Click the download icon (⬇️) next to your newly created OAuth 2.0 Client ID.
   - Save the file in the project folder as `credentials.json`.
7. Authorize your account:
   - In your terminal, run:
     ```bash
     ./run.sh auth
     ```
   - A browser window will open asking you to sign in with `nillohitfreelanceco@gmail.com` and grant permission to send emails and read thread history.
   - Once completed, a `token.json` file is saved locally. You only need to do this once!

---

## 🖥️ How to Use the Review Dashboard

### 1. Ingest Contacts
- Use the sidebar to upload any CSV containing:
  `first_name, last_name, company, job_title, linkedin_url, email, notes`
- Or click **Load Sample Contacts** to start testing immediately with 3 realistic prospects.

### 2. Review & Edit Drafts
- Click on any contact card to view:
  - **Research Dossier**: Verified facts extracted from their website, reviews, and notes.
  - **1-Line Personalization Hook**: The single verifiable angle connecting their business gap to your offer.
  - **Email Variant**: Subject line with 2 alternatives and a 100–150 word body. You can edit any sentence directly in the text box.
  - **LinkedIn Variant**: Connection note (under 300 chars) and InMail draft (under 600 chars).
- Click **Approve Email** when you are satisfied with the draft.

### 3. Send & Track
- **Email Sending**: Click **Send Email**. If **Dry-Run Mode** is active (default), it safely simulates the send and logs the exact message to SQLite. When you are ready for live outreach, flip the toggle in the sidebar to Live Mode.
- **LinkedIn Outreach**: Click **Open LinkedIn Profile** to jump to the prospect's page, and copy the text with one click. Then click **Mark LinkedIn Sent** to log your progress.
- **Follow-Ups**: The "Follow-Ups" tab displays prepared follow-up drafts for contacts who haven't replied after 4–5 days. Follow-ups always present a fresh angle and require your manual approval before anything is sent.

---

## 🛡️ Compliance & Best Practices (CAN-SPAM / GDPR)

This tool is built from the ground up to follow ethical and legal outreach standards:

1. **Truthful Sender Identity**: Every message clearly identifies Nillohit Debnath and `nillohitfreelanceco@gmail.com`.
2. **Mandatory Opt-Out Footer**: Every outgoing email automatically appends:
   > *If you'd prefer not to hear from me again, simply reply with 'unsubscribe' or let me know, and I will remove you from my list immediately.*
3. **Permanent Suppression List**: Anyone who replies with "unsubscribe" or is added to the suppression list is permanently blocked by the system from receiving future emails.
4. **Strict Rate Limiting**: Sending is throttled to a maximum of **20 emails per day** with randomized delays between 90 and 240 seconds to prevent spam behavior and protect your domain reputation.
5. **Legitimate Interest**: Only contact business owners who have a genuine, verifiable need for websites or booking automation. Never purchase generic scraped email lists.

---

## 💻 Command Line Reference

You can also run the full pipeline headlessly using `./run.sh`:

| Command | Description |
|---|---|
| `./run.sh dashboard` | Launches the Streamlit review dashboard |
| `./run.sh pipeline` | Runs ingest, research, and generation on `data/sample_contacts.csv` |
| `./run.sh pipeline path/to/file.csv` | Runs pipeline on your own custom CSV |
| `./run.sh dry-run` | Simulates sending all approved emails without dispatching live emails |
| `./run.sh send` | Sends approved emails via Gmail API with rate limiting |
| `./run.sh stats` | Prints an overview of contacts, daily quota progress, and suppression stats |
| `./run.sh replies` | Checks Gmail API threads to identify contacts who replied |
| `./run.sh auth` | Opens browser to complete one-time Gmail OAuth authorization |
| `./run.sh test` | Runs the automated test suite |

---

## 🏗️ Architecture & File Structure

```
adventurous-galileo/
├── config.yaml              # User configuration (sender, offer, limits, style)
├── .env.example             # Template for API keys and OAuth secrets
├── requirements.txt         # Pinned Python package dependencies
├── run.sh                   # One-click runner script
├── outreach.db              # SQLite database (contacts, dossiers, drafts, logs)
├── data/
│   └── sample_contacts.csv  # 3 sample small businesses for testing
├── src/
│   ├── config.py            # Configuration loader and validator
│   ├── db/
│   │   ├── database.py      # SQLite repository and CRUD queries
│   │   └── models.py        # Dataclasses and pipeline statuses
│   ├── research/
│   │   ├── crawler.py       # Website scraper and technical signal detector
│   │   ├── web_search.py    # DuckDuckGo search integration
│   │   └── dossier.py       # Fact aggregation and verification
│   ├── generation/
│   │   ├── llm_client.py    # Multi-provider client (Gemini, Anthropic, OpenAI)
│   │   ├── prompts.py       # Grounded prompt engineering & negative constraints
│   │   ├── generator.py     # Draft generator orchestrator
│   │   └── uniqueness.py    # Cross-draft similarity checker
│   ├── sending/
│   │   ├── gmail_client.py  # Gmail OAuth API client
│   │   ├── sender.py        # Rate limiting, jitter delay, and duplicate guard
│   │   ├── reply_tracker.py # Thread inspector for incoming replies
│   │   └── suppression.py   # Opt-out footer and suppression manager
│   ├── dashboard/
│   │   └── app.py           # Streamlit visual review UI
│   └── cli.py               # Headless command-line runner
└── tests/
    └── test_pipeline.py     # End-to-end unit and integration test suite
```
