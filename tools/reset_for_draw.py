"""
Reset data to a clean pre-draw state, keeping real player/purchase data.

Steps:
  1. Snapshot current state first (so you can undo)
  2. Clear allocation.csv
  3. Clear events.csv
  4. Clear match_results.csv
  5. Zero out match_stats.csv (keeps teams, blanks all stats/progress)
  6. Clear score_history.csv
  7. Clear audit_log.csv
  8. Remove future-dated NinthTeam/Resurrection purchases (simulation only)
  9. Keep: player_status.csv, real purchases, captains.csv, predictions.csv,
           teams.csv, fixtures.csv, deadlines.json

Usage:
    python tools/reset_for_draw.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from tools.snapshot import snapshot

DATA = ROOT / "data"


def reset() -> None:
    # ── 1. Snapshot first ─────────────────────────────────────────────────────
    snap = snapshot("pre_draw_reset")
    print()

    # ── 2. Clear allocation ────────────────────────────────────────────────────
    (DATA / "allocation.csv").write_text("Player,Team\n")
    print("✓ Cleared allocation.csv")

    # ── 3. Clear events ────────────────────────────────────────────────────────
    pd.DataFrame(columns=[
        "EventID", "EventType", "Status", "Seed", "ScheduledTime", "ExecutedTime",
    ]).to_csv(DATA / "events.csv", index=False)
    print("✓ Cleared events.csv")

    # ── 4. Clear match results ─────────────────────────────────────────────────
    pd.DataFrame(columns=[
        "match_number", "home_goals", "away_goals", "extra_time",
        "penalty_winner", "comeback_home", "comeback_away",
    ]).to_csv(DATA / "match_results.csv", index=False)
    print("✓ Cleared match_results.csv")

    # ── 5. Zero match stats (keep team list, blank all stats) ──────────────────
    ms = pd.read_csv(DATA / "match_stats.csv", dtype=str).fillna("")
    for col in [
        "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins", "GroupComebackWins",
        "GroupWinner", "KnockoutGoals", "KnockoutCleanSheets",
        "KnockoutPenaltyWins", "KnockoutComebackWins",
    ]:
        if col in ms.columns:
            ms[col] = 0
    if "RoundReached" in ms.columns:
        ms["RoundReached"] = ""
    ms.to_csv(DATA / "match_stats.csv", index=False)
    print("✓ Zeroed match_stats.csv")

    # ── 6. Clear score history ─────────────────────────────────────────────────
    pd.DataFrame(columns=["Date", "Player", "Points"]).to_csv(
        DATA / "score_history.csv", index=False
    )
    print("✓ Cleared score_history.csv")

    # ── 7. Clear audit log ─────────────────────────────────────────────────────
    pd.DataFrame(columns=["Timestamp", "Event", "Player", "Action", "Result"]).to_csv(
        DATA / "audit_log.csv", index=False
    )
    print("✓ Cleared audit_log.csv")

    # ── 8. Remove simulation purchases (future-dated NinthTeam/Resurrection) ───
    p = pd.read_csv(DATA / "purchases.csv", dtype=str).fillna("")
    now = datetime.now(timezone.utc)
    sim_types = {"NinthTeam", "Resurrection"}

    def _is_sim_purchase(row: pd.Series) -> bool:
        if row["PurchaseType"] not in sim_types:
            return False
        try:
            ts = datetime.fromisoformat(row["Timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts > now
        except Exception:
            return True

    mask = p.apply(_is_sim_purchase, axis=1)
    removed = p[mask]
    p = p[~mask]
    p.to_csv(DATA / "purchases.csv", index=False)
    if not removed.empty:
        print(f"✓ Removed {len(removed)} simulation purchases: "
              f"{removed['PurchaseType'].tolist()}")
    else:
        print("✓ No simulation purchases to remove")
    print(f"  Kept {len(p)} real purchases")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("Ready for the real draw.")
    print(f"Snapshot saved: {snap.name}")
    print()
    print("To undo at any time:")
    print(f"  python tools/restore.py pre_draw_reset")


if __name__ == "__main__":
    print("=== Reset for Draw ===")
    print("This will clear simulation data and snapshot the current state.")
    confirm = input("Continue? (yes/no): ").strip()
    if confirm.lower() != "yes":
        print("Cancelled.")
        sys.exit(0)
    reset()
