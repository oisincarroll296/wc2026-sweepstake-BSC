# Deployment Guide — WC 2026 Sweepstake

## Local Execution

**Requirements:** Python 3.11+

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run dashboard/app.py
```

The app will open at `http://localhost:8501`.

---

## Admin Password

The default password is `wc2026admin`.

**Change it** by setting an environment variable before starting:

```bash
# Windows PowerShell
$env:ADMIN_PASSWORD = "your-secure-password"
streamlit run dashboard/app.py

# macOS / Linux
ADMIN_PASSWORD="your-secure-password" streamlit run dashboard/app.py
```

For Streamlit Cloud, add `ADMIN_PASSWORD` in the **Secrets** section (see below).

---

## Streamlit Cloud Deployment

1. Push the repository to GitHub (public or private).

2. Go to [share.streamlit.io](https://share.streamlit.io) and click **New app**.

3. Configure:
   - **Repository:** your GitHub repo
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`

4. Under **Advanced settings → Secrets**, add:
   ```toml
   ADMIN_PASSWORD = "your-secure-password"
   ```

5. Click **Deploy**.

---

## Environment Variables

| Variable         | Default         | Description                     |
|------------------|-----------------|---------------------------------|
| `ADMIN_PASSWORD` | `wc2026admin`   | Admin page password             |

---

## Data Files

All data lives in `data/` at the project root. On Streamlit Cloud the app reads and writes these files — they persist between page refreshes but **not between redeploys** unless you use a mounted volume or external storage.

For a long-running tournament:
- Back up `data/*.csv` regularly.
- Consider mounting a persistent disk (Streamlit Cloud does not persist file writes across redeploys — use a database or GitHub-backed storage for production).

---

## Running Tests

```bash
.venv\Scripts\python.exe -m pytest -q   # Windows
python -m pytest -q                      # macOS / Linux
```

All 589 tests should pass.
