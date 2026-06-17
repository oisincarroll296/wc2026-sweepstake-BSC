"""Recalculate and snapshot today's WCW player scores into score_history.csv.

Run after syncing match_stats.csv from WC:
    python "c:\\World Cup Work\\recalc_scores.py"
"""
import sys
import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.event_engine import load_allocation
from src.scoring_engine import load_match_stats, load_predictions, load_captains
from src.competition import load_player_status, load_purchases, overall_leaderboard

today      = date.today().isoformat()
history_p  = ROOT / "data" / "score_history.csv"
tr_path    = ROOT / "data" / "tournament_results.json"

statuses = load_player_status()
participants = statuses["Player"].dropna().tolist() if not statuses.empty else []
if not participants:
    print("No participants found — aborting.")
    sys.exit(1)

alloc = load_allocation()
assignments: dict[str, list[str]] = alloc.assignments

tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {}

lb = overall_leaderboard(
    participants, assignments,
    load_match_stats(), load_purchases(), load_captains(), load_predictions(),
    statuses, tournament_results=tr,
)
if lb.empty or "TotalPoints" not in lb.columns:
    print("Leaderboard empty — nothing to snapshot.")
    sys.exit(0)

wcw_players = set(participants)

# Load existing history, strip any foreign players (e.g. from a bad sync)
if history_p.exists() and history_p.stat().st_size > 20:
    hist = pd.read_csv(history_p, dtype=str)
    hist = hist[hist["Player"].isin(wcw_players)]
else:
    hist = pd.DataFrame(columns=["Date", "Player", "Points"])

# Replace today's rows
hist = hist[hist["Date"].astype(str) != today]
new_rows = [
    {"Date": today, "Player": str(r["Player"]), "Points": f"{float(r['TotalPoints']):.2f}"}
    for _, r in lb.iterrows()
]
hist = pd.concat([hist, pd.DataFrame(new_rows)], ignore_index=True)
hist = hist.sort_values(["Date", "Player"]).reset_index(drop=True)
hist.to_csv(history_p, index=False)
print(f"Score history updated ({today}): {len(new_rows)} players — {', '.join(r['Player'] for r in new_rows)}")
