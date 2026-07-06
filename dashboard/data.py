"""Cached data-loading layer for the dashboard.

All functions are decorated with @st.cache_data (TTL 30 s) so that rapid
page switches don't re-hit the filesystem on every render.  Admin actions
call st.cache_data.clear() to force a refresh after writes.
"""
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path regardless of working directory or case
_ROOT = Path(__file__).resolve().parent.parent
_ROOT_STR = str(_ROOT)
if not any(os.path.normcase(p) == os.path.normcase(_ROOT_STR) for p in sys.path):
    sys.path.insert(0, _ROOT_STR)

import streamlit as st
import pandas as pd

from src.team_database  import load_teams
from src.scoring_engine import load_match_stats, load_predictions, load_captains
from src.competition    import (
    load_player_status, load_purchases, load_events, load_audit_log,
    load_swaps, load_swap_offsets,
    prize_leaderboard, overall_leaderboard,
    get_team_ownership, get_predictions_centre, PRICES,
)

_PURCHASE_FLAG_COLS = [
    "BuyIn", "PredictionPack", "Mulligan", "CompleteRedraw",
    "NinthTeam", "Resurrection", "Insurance",
]
from src.event_engine      import load_allocation


# ── Raw loaders (TTL 30 s) ──────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_teams() -> pd.DataFrame:
    return load_teams()


@st.cache_data(ttl=30)
def get_match_stats() -> pd.DataFrame:
    return load_match_stats()


@st.cache_data(ttl=30)
def get_purchases() -> pd.DataFrame:
    return load_purchases()


@st.cache_data(ttl=30)
def get_statuses() -> pd.DataFrame:
    return load_player_status()


@st.cache_data(ttl=30)
def get_events() -> pd.DataFrame:
    return load_events()


@st.cache_data(ttl=30)
def get_audit_log() -> pd.DataFrame:
    return load_audit_log()


@st.cache_data(ttl=30)
def get_predictions() -> pd.DataFrame:
    return load_predictions()


@st.cache_data(ttl=30)
def get_captains() -> pd.DataFrame:
    return load_captains()


@st.cache_data(ttl=30)
def get_assignments() -> dict[str, list[str]]:
    return load_allocation().assignments


@st.cache_data(ttl=30)
def get_swaps() -> pd.DataFrame:
    return load_swaps()


@st.cache_data(ttl=30)
def get_swap_offsets() -> pd.DataFrame:
    return load_swap_offsets()


# ── Derived loaders ─────────────────────────────────────────────────────────

_PRIZE_SHARES = (0.50, 0.30, 0.20)


@st.cache_data(ttl=30)
def get_prize_pool() -> dict:
    # Implemented directly here so it is immune to stale in-memory competition.py.
    # Prize pool = sum of Budget values from players.csv.
    statuses = load_player_status()
    if statuses.empty or "Budget" not in statuses.columns:
        total = 0.0
    else:
        total = float(pd.to_numeric(statuses["Budget"], errors="coerce").fillna(0.0).sum())
    return {
        "current_pot":  round(total, 2),
        "first_prize":  round(total * _PRIZE_SHARES[0], 2),
        "second_prize": round(total * _PRIZE_SHARES[1], 2),
        "third_prize":  round(total * _PRIZE_SHARES[2], 2),
    }


@st.cache_data(ttl=30)
def get_player_budgets() -> pd.DataFrame:
    """Per-player budget summary: Budget, Spent, Available."""
    statuses = load_player_status()
    if statuses.empty:
        return pd.DataFrame(columns=["Player", "Budget", "Spent", "Available"])
    rows = []
    for _, row in statuses.iterrows():
        player = str(row["Player"])
        budget = float(pd.to_numeric(row.get("Budget", 0), errors="coerce") or 0.0)
        # Auto-rule: Budget >= 5 implies BuyIn purchased
        spent = sum(
            PRICES.get(col, 0.0)
            for col in _PURCHASE_FLAG_COLS
            if str(row.get(col, "0")).strip() in ("1", "True", "true")
        )
        rows.append({
            "Player":    player,
            "Budget":    budget,
            "Spent":     spent,
            "Available": round(budget - spent, 2),
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def get_tier_map() -> dict[str, int]:
    df = get_teams()
    return dict(zip(df["Team"], df["Tier"].astype(int)))


@st.cache_data(ttl=30)
def get_participants() -> list[str]:
    st = get_statuses()
    return sorted(st["Player"].unique().tolist()) if not st.empty else []


@st.cache_data(ttl=30)
def get_prize_leaderboard() -> pd.DataFrame:
    parts = get_participants()
    if not parts:
        return pd.DataFrame()
    return prize_leaderboard(
        parts, get_assignments(), get_match_stats(),
        get_purchases(), get_captains(), get_predictions(),
        get_statuses(), tournament_results=get_tournament_results(),
        swap_offsets=get_swap_offsets(),
    )


@st.cache_data(ttl=30)
def get_overall_leaderboard() -> pd.DataFrame:
    parts = get_participants()
    if not parts:
        return pd.DataFrame()
    return overall_leaderboard(
        parts, get_assignments(), get_match_stats(),
        get_purchases(), get_captains(), get_predictions(),
        get_statuses(), tournament_results=get_tournament_results(),
        swap_offsets=get_swap_offsets(),
    )


@st.cache_data(ttl=30)
def get_team_ownership_data() -> dict:
    return get_team_ownership(
        get_assignments(), get_captains(), get_predictions(), get_purchases()
    )


@st.cache_data(ttl=30)
def get_predictions_centre_data() -> dict:
    return get_predictions_centre(get_predictions())


@st.cache_data(ttl=30)
def get_next_event() -> dict | None:
    ev = get_events()
    if ev.empty:
        return None
    pending = ev[ev["Status"].isin(["SCHEDULED", "OPEN"])]
    if pending.empty:
        return None
    row = pending.iloc[0]
    return {"type": row["EventType"], "time": row.get("ScheduledTime", "")}


@st.cache_data(ttl=30)
def get_paid_count() -> int:
    st = get_statuses()
    if st.empty:
        return 0
    return int((st["Status"] == "PAID").sum())


@st.cache_data(ttl=30)
def get_pack_count() -> int:
    p = get_purchases()
    if p.empty:
        return 0
    return int((p["PurchaseType"] == "PredictionPack").sum())


@st.cache_data(ttl=30)
def get_top_team() -> tuple[str, float] | tuple[None, None]:
    ms   = get_match_stats()
    tmap = get_tier_map()
    if ms.empty:
        return None, None
    from src.scoring_engine import calculate_team_points
    best, best_pts = None, -1.0
    for _, row in ms.iterrows():
        t    = str(row["Team"])
        tier = tmap.get(t, 1)
        pts  = calculate_team_points(t, ms, tier)["total"]
        if pts > best_pts:
            best_pts = pts
            best = t
    return best, best_pts


def _deadline_passed(key: str) -> bool:
    from datetime import datetime, timezone
    deadlines = get_deadlines()
    iso = deadlines.get(key, "")
    if not iso:
        return False
    try:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(iso).astimezone(timezone.utc)
    except Exception:
        return False


def is_predictions_locked() -> bool:
    return _deadline_passed("prediction_lock")


def is_buyin_locked() -> bool:
    return _deadline_passed("buy_in_deadline")


def get_deadlines() -> dict:
    """Load deadlines from data/deadlines.json. Returns {} if file absent."""
    import json
    p = _ROOT / "data" / "deadlines.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(ttl=30)
def get_tournament_results() -> dict:
    """Load tournament_results.json; merge with auto-derived fields from match_stats."""
    import json
    p = _ROOT / "data" / "tournament_results.json"
    tr: dict = {}
    if p.exists():
        try:
            tr = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Remove empty strings so scoring engine treats them as absent
    return {k: v for k, v in tr.items() if v}


def save_deadlines(d: dict) -> None:
    import json
    p = _ROOT / "data" / "deadlines.json"
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


def countdown(iso: str) -> str:
    """Return 'Xd Yh Zm' remaining, or 'PASSED' if in the past."""
    from datetime import datetime, timezone
    try:
        target = datetime.fromisoformat(iso).astimezone(timezone.utc)
        diff = target - datetime.now(timezone.utc)
        if diff.total_seconds() <= 0:
            return "PASSED"
        s = int(diff.total_seconds())
        parts = []
        if s >= 86400:
            parts.append(f"{s // 86400}d")
            s %= 86400
        if s >= 3600:
            parts.append(f"{s // 3600}h")
            s %= 3600
        parts.append(f"{s // 60}m")
        return " ".join(parts)
    except Exception:
        return "—"


_NAME_FIX: dict[str, str] = {
    "CÃ´te d'Ivoire": "Cote d Ivoire", "Côte d'Ivoire": "Cote d Ivoire",
    "Cote d'Ivoire": "Cote d Ivoire", "CuraÃ§ao": "Curacao", "Curaçao": "Curacao",
    "TÃ¼rkiye": "Tuerkiye", "Türkiye": "Tuerkiye", "Turkiye": "Tuerkiye",
    "DR Congo": "Congo DR", "Cape Verde": "Cabo Verde",
}


@st.cache_data(ttl=60)
def get_fixtures() -> pd.DataFrame:
    """Load fixtures.csv — clean, normalized group stage schedule."""
    p = _ROOT / "data" / "fixtures.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
        df["match_number"] = pd.to_numeric(df["match_number"], errors="coerce").astype("Int64")
        df["match_date"]   = pd.to_datetime(df["match_date"], dayfirst=True, errors="coerce").dt.date
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=10)
def get_match_results() -> pd.DataFrame:
    """Load match_results.csv joined with fixture team names."""
    p = _ROOT / "data" / "match_results.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
        if df.empty:
            return df
        df["match_number"] = pd.to_numeric(df["match_number"], errors="coerce").astype("Int64")
        for col in ["home_goals", "away_goals"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        for col in ["extra_time", "comeback_home", "comeback_away"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        fix_p = _ROOT / "data" / "fixtures.csv"
        if fix_p.exists():
            fix = pd.read_csv(fix_p, dtype=str).fillna("")
            fix["match_number"] = pd.to_numeric(fix["match_number"], errors="coerce").astype("Int64")
            fix["match_date"] = pd.to_datetime(fix["match_date"], dayfirst=True, errors="coerce").dt.date
            df = df.merge(
                fix[["match_number", "match_date", "home_team", "away_team", "group", "venue", "kickoff_time"]],
                on="match_number", how="left",
            )
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=10)
def get_eliminated_teams() -> frozenset:
    """Return frozenset of team names that are definitively eliminated.

    Uses KO match results (not RoundReached alone) because RoundReached
    semantics are: 'R16' = won R32 (alive or later eliminated at R16),
    which is ambiguous without cross-checking actual results.
    """
    ms  = get_match_stats()
    res = get_match_results()
    fix = get_fixtures()
    elim: set[str] = set()
    if not ms.empty and "RoundReached" in ms.columns:
        elim.update(ms[ms["RoundReached"] == "GroupStage"]["Team"].tolist())
    if not res.empty and not fix.empty and "match_number" in res.columns:
        for _, r in res.iterrows():
            mn = int(pd.to_numeric(r.get("match_number", 0), errors="coerce") or 0)
            if mn < 73 or mn == 103:
                continue
            fx = fix[fix["match_number"] == mn]
            if fx.empty:
                continue
            f   = fx.iloc[0]
            hh  = str(f["home_team"]); ha = str(f["away_team"])
            hg  = int(float(r.get("home_goals", 0) or 0))
            ag  = int(float(r.get("away_goals", 0) or 0))
            pw  = str(r.get("penalty_winner", "") or "").strip()
            if pw == "home" or (not pw and hg > ag):
                elim.add(ha)
            elif pw == "away" or (not pw and ag > hg):
                elim.add(hh)
    return frozenset(elim)


@st.cache_data(ttl=10)
def get_ko_winner_of() -> dict:
    """Return {match_number: winning_team_name} for completed KO matches."""
    res = get_match_results()
    fix = get_fixtures()
    result: dict[int, str] = {}
    if res.empty or fix.empty or "match_number" not in res.columns:
        return result
    for _, r in res.iterrows():
        mn = int(pd.to_numeric(r.get("match_number", 0), errors="coerce") or 0)
        if mn < 73 or mn == 103:
            continue
        fx = fix[fix["match_number"] == mn]
        if fx.empty:
            continue
        f   = fx.iloc[0]
        hh  = str(f["home_team"]); ha = str(f["away_team"])
        hg  = int(float(r.get("home_goals", 0) or 0))
        ag  = int(float(r.get("away_goals", 0) or 0))
        pw  = str(r.get("penalty_winner", "") or "").strip()
        if pw == "home" or (not pw and hg > ag):
            result[mn] = hh
        elif pw == "away" or (not pw and ag > hg):
            result[mn] = ha
    return result


def _snapshot_score_history() -> None:
    """Write today's score snapshot to score_history.csv — called after each recalculation."""
    import json
    from datetime import date
    today = date.today().isoformat()
    history_p = _ROOT / "data" / "score_history.csv"
    try:
        from src.event_engine import load_allocation
        from src.scoring_engine import load_match_stats as _lms, load_predictions as _lp, load_captains as _lc
        from src.competition import load_player_status as _ls, load_purchases as _lpurch, overall_leaderboard as _olb

        statuses = _ls()
        participants = statuses["Player"].tolist() if not statuses.empty else []
        if not participants:
            return
        assignments = load_allocation().assignments

        tr_path = _ROOT / "data" / "tournament_results.json"
        tr = json.loads(tr_path.read_text()) if tr_path.exists() else {}

        lb = _olb(participants, assignments, _lms(), _lpurch(), _lc(), _lp(), statuses, tournament_results=tr)
        if lb.empty or "TotalPoints" not in lb.columns:
            return

        if history_p.exists() and history_p.stat().st_size > 20:
            hist = pd.read_csv(history_p, dtype=str)
        else:
            hist = pd.DataFrame(columns=["Date", "Player", "Points"])

        hist = hist[hist["Date"].astype(str) != today]
        new_rows = [{"Date": today, "Player": str(r["Player"]), "Points": f"{float(r['TotalPoints']):.2f}"}
                    for _, r in lb.iterrows()]
        hist = pd.concat([hist, pd.DataFrame(new_rows)], ignore_index=True)
        hist.to_csv(history_p, index=False)
    except Exception:
        pass  # snapshot is non-critical


def save_match_result_and_recalculate(
    match_number: int,
    home_goals: int,
    away_goals: int,
    extra_time: bool,
    penalty_winner: str,
    comeback_home: bool,
    comeback_away: bool,
    home_hat_tricks: int = 0,
    away_hat_tricks: int = 0,
    home_red_cards: int = 0,
    away_red_cards: int = 0,
    home_shirt_off: int = 0,
    away_shirt_off: int = 0,
    home_gk_goals: int = 0,
    away_gk_goals: int = 0,
    home_first_eliminated: bool = False,
    away_first_eliminated: bool = False,
) -> None:
    """Upsert a match result then fully recalculate team stats from scratch."""
    results_path = _ROOT / "data" / "match_results.csv"

    # Load / upsert
    cols = ["match_number", "home_goals", "away_goals", "extra_time",
            "penalty_winner", "comeback_home", "comeback_away",
            "home_hat_tricks", "away_hat_tricks",
            "home_red_cards", "away_red_cards",
            "home_shirt_off", "away_shirt_off",
            "home_gk_goals", "away_gk_goals",
            "home_first_eliminated", "away_first_eliminated"]
    if results_path.exists() and results_path.stat().st_size > len(",".join(cols)):
        df = pd.read_csv(results_path, dtype=str).fillna("")
        df["match_number"] = pd.to_numeric(df["match_number"], errors="coerce").astype("Int64")
        mask = df["match_number"] == match_number
        df = df[~mask]  # drop old entry for this match
    else:
        df = pd.DataFrame(columns=cols)

    new_row = pd.DataFrame([{
        "match_number":         match_number,
        "home_goals":           home_goals,
        "away_goals":           away_goals,
        "extra_time":           int(extra_time),
        "penalty_winner":       penalty_winner,
        "comeback_home":        int(comeback_home),
        "comeback_away":        int(comeback_away),
        "home_hat_tricks":      home_hat_tricks,
        "away_hat_tricks":      away_hat_tricks,
        "home_red_cards":       home_red_cards,
        "away_red_cards":       away_red_cards,
        "home_shirt_off":       home_shirt_off,
        "away_shirt_off":       away_shirt_off,
        "home_gk_goals":        home_gk_goals,
        "away_gk_goals":        away_gk_goals,
        "home_first_eliminated": int(home_first_eliminated),
        "away_first_eliminated": int(away_first_eliminated),
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(results_path, index=False)

    # Recalculate match_stats from all entered results, then snapshot scores
    _recalculate_match_stats()
    _snapshot_score_history()
    st.cache_data.clear()

    from dashboard.github_sync import push_file as _pf
    try:
        _pf(results_path, "data/match_results.csv", f"Results: match {match_number}")
        _pf(_ROOT / "data" / "match_stats.csv", "data/match_stats.csv", f"Stats: match {match_number}")
    except Exception as _e:
        st.warning(f"⚠️ GitHub sync: {_e}")


def _recalculate_match_stats() -> None:
    """Rebuild Goals + CleanSheets + PenaltyWins + ComebackWins from match_results.csv."""
    from src.scoring_engine import load_match_stats

    fixtures  = pd.read_csv(_ROOT / "data" / "fixtures.csv", dtype=str).fillna("")
    results_p = _ROOT / "data" / "match_results.csv"
    if not results_p.exists():
        return
    results = pd.read_csv(results_p, dtype=str).fillna("")
    if results.empty:
        return

    ms = load_match_stats()
    if ms.empty:
        return

    # Ensure new columns exist (preserve manual columns if present)
    for col in ["GroupUpsetWins1", "GroupUpsetWins2", "GroupUpsetWins3",
                "KnockoutUpsetWins1", "KnockoutUpsetWins2", "KnockoutUpsetWins3",
                "GroupWins", "KnockoutWins"]:
        if col not in ms.columns:
            ms[col] = 0
    for col in ["ShirtRemovals", "GKGoals", "RedCards", "FirstEliminated",
                "GroupHatTricks", "KnockoutHatTricks"]:
        if col not in ms.columns:
            ms[col] = 0

    # Reset KO-derived RoundReached (R16+) so it rebuilds from match results below.
    # "GroupStage" and "R32" are preserved (manual/group-stage-derived).
    _KO_RR_RESET = {"R16", "QF", "SF", "Final", "Winner"}
    if "RoundReached" in ms.columns:
        ms.loc[ms["RoundReached"].isin(_KO_RR_RESET), "RoundReached"] = "R32"

    # Match number → current round (loser's round) and next round (winner advances to)
    _MATCH_TO_CUR_RR: dict[int, str] = (
        {mn: "R32"   for mn in range(73, 89)}  |
        {mn: "R16"   for mn in range(89, 97)}  |
        {mn: "QF"    for mn in range(97, 101)} |
        {mn: "SF"    for mn in range(101, 103)} |
        {104: "Final"}
    )
    _MATCH_TO_NEXT_RR: dict[int, str] = (
        {mn: "R16"    for mn in range(73, 89)}  |
        {mn: "QF"     for mn in range(89, 97)}  |
        {mn: "SF"     for mn in range(97, 101)} |
        {mn: "Final"  for mn in range(101, 103)} |
        {104: "Winner"}
    )

    # Zero out all auto-derived stat columns (special events now also derived from match_results)
    for col in ["GroupGoals", "GroupCleanSheets", "GroupPenaltyWins", "GroupComebackWins",
                "GroupWins",
                "KnockoutGoals", "KnockoutCleanSheets", "KnockoutPenaltyWins", "KnockoutComebackWins",
                "KnockoutWins",
                "GroupUpsetWins1", "GroupUpsetWins2", "GroupUpsetWins3",
                "KnockoutUpsetWins1", "KnockoutUpsetWins2", "KnockoutUpsetWins3",
                "GroupHatTricks", "KnockoutHatTricks",
                "ShirtRemovals", "GKGoals", "RedCards", "FirstEliminated"]:
        if col in ms.columns:
            ms[col] = 0

    # Build tier map for upset win computation
    from src.team_database import load_teams as _lt
    _teams_df = _lt()
    _tier_map = dict(zip(_teams_df["Team"], _teams_df["Tier"].astype(int))) if not _teams_df.empty else {}

    def _int(val, default=0):
        try: return int(float(val or default))
        except Exception: return default

    for _, res in results.iterrows():
        mn = _int(res.get("match_number", 0))
        fix_rows = fixtures[
            pd.to_numeric(fixtures["match_number"], errors="coerce") == mn
        ]
        if fix_rows.empty:
            continue
        fix = fix_rows.iloc[0]
        home = str(fix["home_team"])
        away = str(fix["away_team"])
        grp  = str(fix.get("group", "")).strip()
        is_group = bool(grp)

        h_goals = _int(res.get("home_goals", 0))
        a_goals = _int(res.get("away_goals", 0))
        pwin    = str(res.get("penalty_winner", "")).strip()
        pfx = "Group" if is_group else "Knockout"

        for team, goals_for, goals_against in [(home, h_goals, a_goals), (away, a_goals, h_goals)]:
            mask = ms["Team"] == team
            if not mask.any():
                continue
            ms.loc[mask, f"{pfx}Goals"] = ms.loc[mask, f"{pfx}Goals"].astype(int) + goals_for
            if goals_against == 0:
                ms.loc[mask, f"{pfx}CleanSheets"] = ms.loc[mask, f"{pfx}CleanSheets"].astype(int) + 1

        # Penalty win (KO only)
        if pwin == "home" and not is_group:
            ms.loc[ms["Team"] == home, "KnockoutPenaltyWins"] = (
                ms.loc[ms["Team"] == home, "KnockoutPenaltyWins"].astype(int) + 1
            )
        elif pwin == "away" and not is_group:
            ms.loc[ms["Team"] == away, "KnockoutPenaltyWins"] = (
                ms.loc[ms["Team"] == away, "KnockoutPenaltyWins"].astype(int) + 1
            )

        # Win bonus — any win (normal/extra time or penalties)
        if pwin == "home":
            _win_team = home
        elif pwin == "away":
            _win_team = away
        elif h_goals > a_goals:
            _win_team = home
        elif a_goals > h_goals:
            _win_team = away
        else:
            _win_team = None  # draw (group stage only)
        if _win_team:
            _win_col = f"{pfx}Wins"
            ms.loc[ms["Team"] == _win_team, _win_col] = (
                ms.loc[ms["Team"] == _win_team, _win_col].astype(int) + 1
            )

        # Comeback wins
        if _int(res.get("comeback_home", 0)):
            ms.loc[ms["Team"] == home, f"{pfx}ComebackWins"] = (
                ms.loc[ms["Team"] == home, f"{pfx}ComebackWins"].astype(int) + 1
            )
        if _int(res.get("comeback_away", 0)):
            ms.loc[ms["Team"] == away, f"{pfx}ComebackWins"] = (
                ms.loc[ms["Team"] == away, f"{pfx}ComebackWins"].astype(int) + 1
            )

        # Tier-upset wins — determine match winner then check tier gap
        if pwin == "home":
            winner, loser = home, away
        elif pwin == "away":
            winner, loser = away, home
        elif h_goals > a_goals:
            winner, loser = home, away
        elif a_goals > h_goals:
            winner, loser = away, home
        else:
            winner, loser = None, None  # group stage draw

        if winner and loser:
            w_tier = _tier_map.get(winner, 0)
            l_tier = _tier_map.get(loser, 0)
            diff = w_tier - l_tier  # positive = winner is a lower/worse tier (upset)
            if diff in (1, 2, 3):
                upset_col = f"{pfx}UpsetWins{diff}"
                mask = ms["Team"] == winner
                if mask.any():
                    ms.loc[mask, upset_col] = ms.loc[mask, upset_col].astype(int) + 1

        # Auto-set RoundReached for knockout matches (both winner and loser)
        if not is_group:
            _cur_rr  = _MATCH_TO_CUR_RR.get(mn)
            _next_rr = _MATCH_TO_NEXT_RR.get(mn)
            if winner and _next_rr:
                ms.loc[ms["Team"] == winner, "RoundReached"] = _next_rr
            if loser and _cur_rr:
                ms.loc[ms["Team"] == loser, "RoundReached"] = _cur_rr

        # Special events — aggregated per match from match_results.csv
        ht_col = f"{pfx}HatTricks"
        for team, side in [(home, "home"), (away, "away")]:
            mask = ms["Team"] == team
            if not mask.any():
                continue
            ms.loc[mask, ht_col] = ms.loc[mask, ht_col].astype(int) + _int(res.get(f"{side}_hat_tricks", 0))
            ms.loc[mask, "RedCards"]      = ms.loc[mask, "RedCards"].astype(int)      + _int(res.get(f"{side}_red_cards", 0))
            ms.loc[mask, "ShirtRemovals"] = ms.loc[mask, "ShirtRemovals"].astype(int) + _int(res.get(f"{side}_shirt_off", 0))
            ms.loc[mask, "GKGoals"]       = ms.loc[mask, "GKGoals"].astype(int)       + _int(res.get(f"{side}_gk_goals", 0))
            if _int(res.get(f"{side}_first_eliminated", 0)):
                ms["FirstEliminated"] = 0          # clear any previous flag
                ms.loc[mask, "FirstEliminated"] = 1

    ms.to_csv(_ROOT / "data" / "match_stats.csv", index=False)


@st.cache_data(ttl=30)
def get_goals_conceded_map() -> dict[str, int]:
    """Goals conceded per team, derived from entered match results + fixtures."""
    fixtures = get_fixtures()
    results  = get_match_results()
    if fixtures.empty or results.empty:
        return {}
    conceded: dict[str, int] = {}
    for _, res in results.iterrows():
        mn = int(pd.to_numeric(res.get("match_number", 0), errors="coerce") or 0)
        fx_row = fixtures[pd.to_numeric(fixtures["match_number"], errors="coerce") == mn]
        if fx_row.empty:
            continue
        fx = fx_row.iloc[0]
        home = str(fx.get("home_team", ""))
        away = str(fx.get("away_team", ""))
        hg = int(float(res.get("home_goals", 0) or 0))
        ag = int(float(res.get("away_goals", 0) or 0))
        conceded[home] = conceded.get(home, 0) + ag
        conceded[away] = conceded.get(away, 0) + hg
    return conceded


@st.cache_data(ttl=30)
def get_remaining_potential() -> dict[str, float]:
    """Max additional progression points each player could earn from still-surviving teams."""
    detail = get_remaining_potential_detail()
    return {p: d["max_potential"] for p, d in detail.items()}


@st.cache_data(ttl=30)
def get_r16_potential() -> dict[str, dict]:
    """Per-player points if all surviving (non-eliminated) teams reach R16.

    Returns { player: {current_score, r16_additional, r16_total} }.
    'Surviving' = RoundReached not in {GroupStage, R32} (eliminated rounds).
    For teams still in groups (no round yet): awards R32+R16 progression bonuses.
    For teams already past R16: 0 additional from R16 target.
    """
    from src.scoring_engine import PROGRESSION_BONUSES, ROUND_ORDER, KNOCKOUT_ROUNDS
    from src.competition import purchases_to_scoring_format
    from src.scoring_engine import get_effective_teams

    assignments = get_assignments()
    match_stats = get_match_stats()
    tier_map    = get_tier_map()
    lb          = get_overall_leaderboard()
    purchases   = get_purchases()

    score_map: dict[str, float] = {}
    if not lb.empty and "TotalPoints" in lb.columns:
        score_map = dict(zip(lb["Player"], lb["TotalPoints"].astype(float)))

    scoring_purch = purchases_to_scoring_format(purchases) if not purchases.empty else pd.DataFrame(
        columns=["Player", "PurchaseType", "Selection", "Timestamp"]
    )

    ELIMINATED = {"GroupStage", "R32"}
    R16_TARGET = "R16"
    r16_idx = ROUND_ORDER.index(R16_TARGET)

    result: dict = {}
    for player, _ in assignments.items():
        current_score = score_map.get(player, 0.0)
        eff = get_effective_teams(player, assignments, scoring_purch)
        all_teams = list(set(eff["group_stage"]) | set(eff["knockout"]))

        r16_additional = 0.0
        for team in all_teams:
            tier = tier_map.get(team, 1)
            bonuses = PROGRESSION_BONUSES.get(tier, {})
            rnd = ""
            if not match_stats.empty:
                row = match_stats[match_stats["Team"] == team]
                if not row.empty:
                    rnd = str(row.iloc[0].get("RoundReached", "") or "").strip()

            if rnd in ELIMINATED:
                continue  # already knocked out
            if rnd in ROUND_ORDER and ROUND_ORDER.index(rnd) >= r16_idx:
                continue  # already at or past R16

            # Calculate progression bonuses from current position up to R16
            current_idx = ROUND_ORDER.index(rnd) if rnd in ROUND_ORDER else -1
            team_r16 = sum(
                float(bonuses.get(ko_rnd, 0))
                for ko_rnd in KNOCKOUT_ROUNDS
                if ROUND_ORDER.index(ko_rnd) > current_idx
                and ROUND_ORDER.index(ko_rnd) <= r16_idx
            )
            r16_additional += team_r16

        result[player] = {
            "current_score":  current_score,
            "r16_additional": r16_additional,
            "r16_total":      current_score + r16_additional,
        }
    return result


@st.cache_data(ttl=30)
def get_remaining_potential_detail() -> dict:
    """Per-player, per-team remaining potential with current score context.

    Returns:
        { player: {
            current_score: float,
            max_potential: float,
            max_possible_total: float,
            alive_count: int,
            teams: [ {team, tier, round_reached, alive, max_remaining} ]
          }
        }
    Min remaining is always 0 (a team can be knocked out next match).
    Max remaining assumes every surviving team wins the tournament.
    """
    from src.scoring_engine import PROGRESSION_BONUSES, ROUND_ORDER, KNOCKOUT_ROUNDS
    assignments = get_assignments()
    match_stats = get_match_stats()
    tier_map    = get_tier_map()
    lb          = get_overall_leaderboard()

    score_map: dict[str, float] = {}
    if not lb.empty and "TotalPoints" in lb.columns:
        score_map = dict(zip(lb["Player"], lb["TotalPoints"].astype(float)))

    ELIMINATED = {"GroupStage", "R16"}

    result: dict = {}
    for player, teams in assignments.items():
        current_score = score_map.get(player, 0.0)
        max_potential = 0.0
        team_details  = []

        for team in teams:
            tier = tier_map.get(team, 1)
            _not_started = {"team": team, "tier": tier,
                            "round_reached": "", "alive": True, "max_remaining": 0.0,
                            "goals": 0, "wins": 0}
            if match_stats.empty:
                team_details.append(_not_started)
                continue
            row = match_stats[match_stats["Team"] == team]
            if row.empty:
                team_details.append(_not_started)
                continue
            r    = row.iloc[0]
            rnd  = str(r.get("RoundReached", "") or "").strip()
            bonuses = PROGRESSION_BONUSES.get(tier, {})

            alive = rnd not in ELIMINATED and rnd != "Winner"
            if alive and rnd in ROUND_ORDER:
                current_idx = ROUND_ORDER.index(rnd)
                team_max = sum(
                    float(bonuses.get(ko_rnd, 0))
                    for ko_rnd in KNOCKOUT_ROUNDS
                    if ROUND_ORDER.index(ko_rnd) > current_idx
                )
            else:
                team_max = 0.0

            goals = int(float(r.get("GroupGoals",    0) or 0)) + int(float(r.get("KnockoutGoals", 0) or 0))
            wins  = int(float(r.get("GroupWins",     0) or 0)) + int(float(r.get("KnockoutWins",  0) or 0))

            max_potential += team_max
            team_details.append({
                "team": team, "tier": tier, "round_reached": rnd,
                "alive": alive, "max_remaining": team_max,
                "goals": goals, "wins": wins,
            })

        result[player] = {
            "current_score":      current_score,
            "max_potential":      max_potential,
            "max_possible_total": current_score + max_potential,
            "alive_count":        sum(1 for t in team_details if t["alive"]),
            "teams":              sorted(team_details, key=lambda x: (-x["max_remaining"], x["team"])),
        }
    return result


@st.cache_data(ttl=30)
def get_player_goals_wins() -> pd.DataFrame:
    """Total goals and wins per player summed across their team portfolio."""
    detail = get_remaining_potential_detail()
    rows = [
        {"Player": p,
         "Goals": sum(t.get("goals", 0) for t in info["teams"]),
         "Wins":  sum(t.get("wins",  0) for t in info["teams"])}
        for p, info in detail.items()
    ]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Player", "Goals", "Wins"])


@st.cache_data(ttl=60)
def get_score_history() -> pd.DataFrame:
    """Load score_history.csv for the points-over-time chart."""
    p = _ROOT / "data" / "score_history.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p)
        df["Date"] = df["Date"].astype(str)
        return df
    except Exception:
        return pd.DataFrame()


def get_match_impact(match_number: int) -> list[dict]:
    """Return per-player points impact from a single match result.

    Used by admin to show 'who benefits' after entering a result.
    Returns list of {player, team, goals_for, clean_sheet, pts_gained}.
    """
    fixtures = get_fixtures()
    results  = get_match_results()
    tier_map = get_tier_map()
    assignments = get_assignments()

    if fixtures.empty or results.empty:
        return []

    fx_row = fixtures[pd.to_numeric(fixtures["match_number"], errors="coerce") == match_number]
    if fx_row.empty:
        return []
    fx = fx_row.iloc[0]
    home = str(fx.get("home_team", ""))
    away = str(fx.get("away_team", ""))

    res_row = results[results["match_number"] == match_number]
    if res_row.empty:
        return []
    res = res_row.iloc[0]
    hg = int(float(res.get("home_goals", 0) or 0))
    ag = int(float(res.get("away_goals", 0) or 0))

    impact = []
    for player, teams in assignments.items():
        for team in teams:
            if team == home:
                gf, ga = hg, ag
            elif team == away:
                gf, ga = ag, hg
            else:
                continue
            cs = 1 if ga == 0 else 0
            pts = float(gf * 1 + cs * 2)
            impact.append({
                "Player": player, "Team": team,
                "Goals": gf, "CS": cs, "Pts": pts,
            })

    return sorted(impact, key=lambda x: -x["Pts"])


@st.cache_data(ttl=30)
def get_insurance_overview() -> dict:
    """Return a structured summary for the Insurance analytics panel.

    Returns:
        t1_status:     list[dict] — each T1 team with {team, tier, round_reached,
                                    eliminated, owners (list of players who own it)}
        holders:       list[dict] — players with insurance: {player, t1_teams,
                                    eliminated_count, bonus_earned, max_bonus}
    """
    from src.scoring_engine import INSURANCE_BONUS, ROUND_ORDER
    assignments  = get_assignments()
    match_stats  = get_match_stats()
    tier_map     = get_tier_map()
    purchases    = get_purchases()

    # All T1 teams (any player's allocation)
    all_t1: set[str] = set()
    for teams in assignments.values():
        for t in teams:
            if tier_map.get(t, 0) == 1:
                all_t1.add(t)

    # Build status per T1 team
    t1_status = []
    for team in sorted(all_t1):
        rnd = ""
        if not match_stats.empty:
            row = match_stats[match_stats["Team"] == team]
            if not row.empty:
                rnd = str(row.iloc[0].get("RoundReached", "") or "").strip()
        eliminated = rnd in {"GroupStage", "R32"}
        owners = [p for p, ts in assignments.items() if team in ts]
        t1_status.append({
            "team":         team,
            "round_reached": rnd,
            "eliminated":   eliminated,
            "owners":       owners,
        })

    # Insurance holders
    holders = []
    if not purchases.empty:
        ins_players = purchases[purchases["PurchaseType"] == "Insurance"]["Player"].unique()
        for player in ins_players:
            t1_teams = [t for t in assignments.get(player, []) if tier_map.get(t, 0) == 1]
            elim_count = 0
            for t in t1_teams:
                entry = next((x for x in t1_status if x["team"] == t), None)
                if entry and entry["eliminated"]:  # eliminated = GroupStage or R32
                    elim_count += 1
            holders.append({
                "player":          player,
                "t1_teams":        t1_teams,
                "eliminated_count": elim_count,
                "bonus_earned":    float(elim_count * INSURANCE_BONUS),
                "max_bonus":       float(len(t1_teams) * INSURANCE_BONUS),
            })

    return {"t1_status": t1_status, "holders": holders}


DEADLINE_LABELS: dict[str, str] = {
    "prediction_lock":           "Prediction Lock",
    "buy_in_deadline":           "Buy-In Deadline (before last group game)",
    "pre_tournament_captain":    "Pre-Tournament Captain",
    "mulligan_deadline":         "Mulligan Deadline",
    "group_stage_closes":        "Group Stage Closes",
    "ninth_team_draw":           "Ninth Team Draw",
    "knockout_captain_deadline": "Knockout Captain Deadline",
    "resurrection_window_close": "Resurrection Window Closes",
    "tournament_end":            "Tournament End",
}
