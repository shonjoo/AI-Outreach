#!/usr/bin/env bash
set -e

# Outreach Automation Runner Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure Python environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if command -v uv &> /dev/null; then
        uv venv --python 3.11 .venv
        uv pip install -r requirements.txt --python .venv/bin/python
    elif [ -f "$HOME/.local/bin/uv" ]; then
        "$HOME/.local/bin/uv" venv --python 3.11 .venv
        "$HOME/.local/bin/uv" pip install -r requirements.txt --python .venv/bin/python
    else
        python3 -m venv .venv
        .venv/bin/pip install -r requirements.txt
    fi
fi

PYTHON=".venv/bin/python"
STREAMLIT=".venv/bin/streamlit"

CMD="${1:-dashboard}"

case "$CMD" in
    dashboard|ui)
        echo "🚀 Starting Outreach Review Dashboard on http://localhost:8501..."
        "$STREAMLIT" run src/dashboard/app.py --server.headless=true
        ;;
    pipeline)
        CSV="$2"
        if [ -z "$CSV" ]; then
            echo "❌ Please provide a path to a contacts CSV file: ./run.sh pipeline path/to/contacts.csv"
            exit 1
        fi
        echo "⚡ Running pipeline on $CSV..."
        "$PYTHON" src/cli.py pipeline --csv "$CSV"
        ;;
    dry-run)
        echo "🔒 Running simulated send in Dry-Run mode..."
        "$PYTHON" src/cli.py send --dry-run
        ;;
    send)
        echo "⚠️ Sending approved emails via Gmail API..."
        "$PYTHON" src/cli.py send
        ;;
    stats)
        "$PYTHON" src/cli.py stats
        ;;
    replies)
        "$PYTHON" src/cli.py replies
        ;;
    auth)
        echo "🔐 Launching Gmail API OAuth authentication..."
        "$PYTHON" src/cli.py auth
        ;;
    test)
        echo "🧪 Running automated test suite..."
        "$PYTHON" -m unittest tests/test_pipeline.py
        ;;
    share|tunnel)
        echo "🌐 Starting dashboard and creating a secure public HTTPS link..."
        echo "Tip: Install cloudflared (brew install cloudflared) or ngrok for instant remote access."
        if command -v cloudflared &> /dev/null; then
            "$STREAMLIT" run src/dashboard/app.py --server.headless=true &
            sleep 2
            cloudflared tunnel --url http://localhost:8501
        elif command -v ngrok &> /dev/null; then
            "$STREAMLIT" run src/dashboard/app.py --server.headless=true &
            sleep 2
            ngrok http 8501
        else
            echo "Neither cloudflared nor ngrok found."
            echo "To create an instant shareable link from your Mac, run: brew install cloudflared"
            echo "Then run: ./run.sh share"
        fi
        ;;
    *)
        echo "Usage: ./run.sh [dashboard|pipeline|dry-run|send|stats|replies|auth|test|share]"
        exit 1
        ;;
esac
