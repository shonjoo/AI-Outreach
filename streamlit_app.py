"""Root entrypoint for Streamlit Community Cloud and container deployments."""

import os
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import runpy

if __name__ == "__main__":
    app_path = root_dir / "src" / "dashboard" / "app.py"
    runpy.run_path(str(app_path), run_name="__main__")
