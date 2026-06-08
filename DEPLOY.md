# Deploying to Streamlit Cloud

## Live App

**https://fellas-wc2026-sweepstake.streamlit.app/**

Player portfolio links follow this pattern:
```
https://fellas-wc2026-sweepstake.streamlit.app/player_portfolios?player=Oisin%20C
```

The **Share my portfolio link** button on the Player Portfolios page generates this URL automatically.

---

## Pushing updates to GitHub (day-to-day workflow)

This is all you need once the app is live. Streamlit Cloud auto-redeploys within ~30 seconds of a push.

```powershell
cd "C:\World Cup"

# Stage everything (code + data)
git add .

# Commit with a message
git commit -m "Update scores: 2026-06-08"

# Push — Streamlit Cloud picks it up automatically
git push
```

### Entering results and keeping scores live

1. Run the dashboard locally: `streamlit run dashboard/app.py`
2. Open `http://localhost:8501` → Admin → Results Entry → enter scores
3. Run the above `git add / commit / push` — the live app updates within ~30 s

---

## One-time setup (already done)

### GitHub repo
The app is connected to a **private** GitHub repository. Private means personal
data files (purchases, allocation, predictions) are safe to commit.

### Data files committed
The `.gitignore` "Personal data" block has been removed/commented out so that
`data/purchases.csv`, `data/allocation.csv`, etc. are tracked by git and visible
to Streamlit Cloud.

### Admin password
In Streamlit Cloud → App settings → Secrets:
```toml
ADMIN_PASSWORD = "your_secure_password"
```
If not set, the default `wc2026admin` is used.

### Main file path (Streamlit Cloud setting)
```
dashboard/app.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| App shows old data | Wait 30 s after push, then hard-refresh |
| Scores look wrong | Check `data/match_stats.csv` was committed |
| Admin password not working | Check Secrets in Streamlit Cloud settings |
| App crashes on startup | Check the Streamlit Cloud logs tab for the error |
