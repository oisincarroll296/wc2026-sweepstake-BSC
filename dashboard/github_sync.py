"""GitHub Contents API sync — persists data/ files back to the repo after writes.

Requires a GitHub PAT stored in Streamlit secrets as GITHUB_TOKEN.
On local dev (no secret), all calls are silent no-ops.
"""
import base64
from pathlib import Path

import requests

REPO   = "oisincarroll296/wc2026-sweepstake-BSC"
BRANCH = "master"
_API   = f"https://api.github.com/repos/{REPO}/contents"


def _token() -> str:
    try:
        import streamlit as st
        return st.secrets.get("GITHUB_TOKEN", "") or ""
    except Exception:
        return ""


def push_file(local_path: Path, repo_path: str, message: str) -> bool:
    """Commit local_path to GitHub at repo_path. Returns True on success.

    Silent no-op (returns False) when GITHUB_TOKEN is absent — safe for local dev.
    On conflict (concurrent write), retries once with a fresh SHA.
    """
    tok = _token()
    if not tok:
        return False

    headers = {
        "Authorization": f"token {tok}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"{_API}/{repo_path}"

    def _do_put(sha: str) -> requests.Response:
        payload: dict = {
            "message": message,
            "content": base64.b64encode(local_path.read_bytes()).decode(),
            "branch":  BRANCH,
        }
        if sha:
            payload["sha"] = sha
        return requests.put(url, headers=headers, json=payload, timeout=10)

    # Fetch current SHA
    r = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=10)
    sha = r.json().get("sha", "") if r.ok else ""

    resp = _do_put(sha)
    if resp.status_code == 409:
        # SHA stale (concurrent write) — refresh and retry once
        r2 = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=10)
        sha2 = r2.json().get("sha", "") if r2.ok else ""
        resp = _do_put(sha2)

    return resp.ok


def push_data_files(data_dir: Path, *filenames: str) -> None:
    """Push a set of data/ files to GitHub. Swallows errors — never blocks the caller."""
    for fn in filenames:
        local = data_dir / fn
        if local.exists():
            try:
                push_file(local, f"data/{fn}", f"Admin sync: {fn}")
            except Exception:
                pass
