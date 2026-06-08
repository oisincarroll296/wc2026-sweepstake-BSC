"""Reset all sweepstake data for a fresh start.

Run this when you want to wipe test data and begin the real tournament.
Player names are preserved; everything else is cleared.

Usage:
    .\.venv\Scripts\python.exe scripts/reset_data.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
EXPORTS = ROOT / "exports"


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [yes/no]: ").strip().lower()
    return answer == "yes"


def reset():
    print("\n  WC 2026 Sweepstake — Data Reset\n")
    print("  This will:")
    print("  - Keep all 13 player names")
    print("  - Reset all players to UNPAID")
    print("  - Clear all purchases, draws, events, predictions, captains")
    print("  - Reset all match stats to zero")
    print("  - Remove prediction and buy-in locks")
    print("  - Clear all exports\n")

    if not confirm("  Are you sure you want to wipe all data?"):
        print("  Cancelled.")
        return

    import pandas as pd

    # ── Player status: keep names/picks, reset to UNPAID ────────────────────
    status_path = DATA / "players.csv"
    if status_path.exists():
        df = pd.read_csv(status_path, dtype=str).fillna("")
        df["Status"] = "UNPAID"
        df["PaidTimestamp"] = ""
        df.to_csv(status_path, index=False)
        print(f"  [OK] players.csv — {len(df)} players reset to UNPAID")
    else:
        print("  [SKIP] players.csv not found")

    # ── Match stats: keep all 48 teams, zero all stats ──────────────────────
    stats_path = DATA / "match_stats.csv"
    if stats_path.exists():
        df = pd.read_csv(stats_path, dtype=str).fillna("")
        int_cols = [
            "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins", "GroupComebackWins",
            "GroupWinner", "KnockoutGoals", "KnockoutCleanSheets",
            "KnockoutPenaltyWins", "KnockoutComebackWins",
        ]
        for col in int_cols:
            if col in df.columns:
                df[col] = 0
        if "RoundReached" in df.columns:
            df["RoundReached"] = ""
        df.to_csv(stats_path, index=False)
        print(f"  [OK] match_stats.csv — {len(df)} teams reset to zero")
    else:
        print("  [SKIP] match_stats.csv not found")

    # ── Clear CSV files ──────────────────────────────────────────────────────
    empties = {
        "purchases.csv":     ["Player", "PurchaseType", "Selection", "Reference", "Timestamp"],
        "events.csv":        ["EventID", "EventType", "ScheduledTime", "ExecutedTime", "Status", "RandomSeed"],
        "audit_log.csv":     ["Timestamp", "Event", "Player", "Action", "Result"],
        "allocation.csv":    ["Player", "Team"],
        "match_results.csv": ["match_number", "home_goals", "away_goals", "extra_time", "penalty_winner", "comeback_home", "comeback_away"],
        "score_history.csv": ["Date", "Player", "Points"],
    }
    for filename, cols in empties.items():
        path = DATA / filename
        pd.DataFrame(columns=cols).to_csv(path, index=False)
        print(f"  [OK] {filename} cleared")

    # ── Clear picks from players.csv (keep names and status) ─────────────────
    players_path = DATA / "players.csv"
    if players_path.exists():
        df = pd.read_csv(players_path, dtype=str).fillna("")
        for col in ["PreTournamentCaptain", "KnockoutCaptain", "WorldCupWinner", "GoldenBoot", "DarkHorse"]:
            if col in df.columns:
                df[col] = ""
        df.to_csv(players_path, index=False)
        print(f"  [OK] players.csv — picks cleared")

    # ── Clear exports ────────────────────────────────────────────────────────
    if EXPORTS.exists():
        cleared = 0
        for f in EXPORTS.glob("*.csv"):
            f.unlink()
            cleared += 1
        print(f"  [OK] exports/ — {cleared} file(s) removed")

    print("\n  Reset complete. Run the initial draw when ready.\n")


if __name__ == "__main__":
    reset()
