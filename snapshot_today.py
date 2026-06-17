"""Daily score snapshot — writes today's leaderboard to score_history.csv."""
import json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.competition import load_player_status, load_purchases, overall_leaderboard
from src.scoring_engine import load_match_stats, load_predictions, load_captains

today = date.today().isoformat()
history_p = ROOT / "data" / "score_history.csv"

statuses = load_player_status()
participants = statuses["Player"].tolist() if not statuses.empty else []
if not participants:
    print("No players found.")
    sys.exit(0)

alloc_df = pd.read_csv(ROOT / "data" / "allocation.csv", dtype=str).fillna("")
assignments: dict[str, list[str]] = {}
for _, r in alloc_df.iterrows():
    assignments.setdefault(str(r["Player"]), []).append(str(r["Team"]))

tr_path = ROOT / "data" / "tournament_results.json"
tr = json.loads(tr_path.read_text()) if tr_path.exists() else {}

lb = overall_leaderboard(
    participants, assignments,
    load_match_stats(), load_purchases(), load_captains(), load_predictions(),
    statuses, tournament_results=tr,
)
if lb.empty or "TotalPoints" not in lb.columns:
    print("Leaderboard empty — nothing to snapshot.")
    sys.exit(0)

hist = pd.read_csv(history_p, dtype=str) if (history_p.exists() and history_p.stat().st_size > 20) else pd.DataFrame(columns=["Date", "Player", "Points"])
hist = hist[hist["Date"].astype(str) != today]
new_rows = [{"Date": today, "Player": str(r["Player"]), "Points": f"{float(r['TotalPoints']):.2f}"} for _, r in lb.iterrows()]
hist = pd.concat([hist, pd.DataFrame(new_rows)], ignore_index=True)
hist.sort_values(["Date", "Player"]).to_csv(history_p, index=False)
print(f"Snapshotted {len(new_rows)} players for {today}.")
