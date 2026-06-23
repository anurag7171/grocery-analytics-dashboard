"""
Push the current working tree to the HuggingFace Space so the live app picks up
refreshed data. Requires the HF_TOKEN environment variable (a write token).

Usage (from repo root):
    HF_TOKEN=hf_xxx python scripts/deploy_hf.py
"""

import os
import sys

from huggingface_hub import HfApi

REPO_ID = "Anurag717/grocery-analytics-dashboard"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IGNORE = [
    ".git/*", ".git/**",
    "data/retail.db",
    "**/__pycache__/*", "*.pyc", "*.pyo",
    ".DS_Store", "**/.DS_Store",
    "notebooks/*", "**/.ipynb_checkpoints/*",
    ".venv/*", "venv/*",
]


def main() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("HF_TOKEN not set — skipping HuggingFace redeploy.")
        sys.exit(0)

    HfApi().upload_folder(
        folder_path=ROOT,
        repo_id=REPO_ID,
        repo_type="space",
        token=token,
        commit_message="chore: scheduled data refresh (roll forecast forward)",
        ignore_patterns=IGNORE,
    )
    print(f"Redeployed {REPO_ID} — Space will rebuild.")


if __name__ == "__main__":
    main()
