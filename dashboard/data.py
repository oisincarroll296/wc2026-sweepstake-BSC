"""Cached data-loading layer for the dashboard.

All functions are decorated with @st.cache_data (TTL 30 s) so that rapid
page switches don't re-hit the filesystem on every render.  Admin actions
call st.cache_data.clear() to force a refresh after writes.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of working directory
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import pandas as pd

from src.team_database  import load_teams
from src.scoring_engine import load_match_stats, load_predictions, load_captains
from src.competition    import (
    load_player_status, load_purchases, load_events, load_audit_log,
    calculate_prize_pool, prize_leaderboard, overall_leaderboard,
    get_team_ownership, get_predictions_centre,
)
from src.event_engine      import load_allocation


# ── Raw loaders (TTL 30 s) ──────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_teams() -> pd.DataFrame:
    return load_teams()


@st.cache_data(ttl=30)
def get_match_stats() -> pd.DataFrame:
    return load_match_stats()


@st.cache_data(ttl=30)
def _purchases_cached() -> pd.DataFrame:
    return load_purchases()


def get_purchases() -> pd.DataFrame:
    """Return purchases, bypassing a stale empty cache if the file has content."""
    df = _purchases_cached()
    if df.empty:
        path = _ROOT / "data" / "purchases.csv"
        if path.exists() and path.stat().st_size > 100:
            # Cache served empty despite file having content — re-read directly.
            _purchases_cached.clear()
            return load_purchases()
    return df


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


# ── Derived loaders ─────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_prize_pool() -> dict:
    # Load directly — avoids nested @st.cache_data call which can return
    # a stale/empty result on first render before the inner cache is primed.
    return calculate_prize_pool(load_purchases())


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
        get_statuses(),
    )


@st.cache_data(ttl=30)
def get_overall_leaderboard() -> pd.DataFrame:
    parts = get_participants()
    if not parts:
        return pd.DataFrame()
    return overall_leaderboard(
        parts, get_assignments(), get_match_stats(),
        get_purchases(), get_captains(), get_predictions(),
        get_statuses(),
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
    """Load match_results.csv — entered match scores."""
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
        return df
    except Exception:
        return pd.DataFrame()


def save_match_result_and_recalculate(
    match_number: int,
    home_goals: int,
    away_goals: int,
    extra_time: bool,
    penalty_winner: str,
    comeback_home: bool,
    comeback_away: bool,
) -> None:
    """Upsert a match result then fully recalculate team stats from scratch."""
    results_path = _ROOT / "data" / "match_results.csv"

    # Load / upsert
    cols = ["match_number", "home_goals", "away_goals", "extra_time",
            "penalty_winner", "comeback_home", "comeback_away"]
    if results_path.exists() and results_path.stat().st_size > len(",".join(cols)):
        df = pd.read_csv(results_path, dtype=str).fillna("")
        df["match_number"] = pd.to_numeric(df["match_number"], errors="coerce").astype("Int64")
        mask = df["match_number"] == match_number
        df = df[~mask]  # drop old entry for this match
    else:
        df = pd.DataFrame(columns=cols)

    new_row = pd.DataFrame([{
        "match_number":  match_number,
        "home_goals":    home_goals,
        "away_goals":    away_goals,
        "extra_time":    int(extra_time),
        "penalty_winner": penalty_winner,
        "comeback_home": int(comeback_home),
        "comeback_away": int(comeback_away),
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(results_path, index=False)

    # Recalculate match_stats from all entered results
    _recalculate_match_stats()
    st.cache_data.clear()


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

    # Zero out all derived stat columns
    for col in ["GroupGoals", "GroupCleanSheets", "GroupPenaltyWins", "GroupComebackWins",
                "KnockoutGoals", "KnockoutCleanSheets", "KnockoutPenaltyWins", "KnockoutComebackWins"]:
        if col in ms.columns:
            ms[col] = 0

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
        pfx = "Group" if is_group else "Knockout"

        for team, goals_for, goals_against in [(home, h_goals, a_goals), (away, a_goals, h_goals)]:
            mask = ms["Team"] == team
            if not mask.any():
                continue
            ms.loc[mask, f"{pfx}Goals"] = ms.loc[mask, f"{pfx}Goals"].astype(int) + goals_for
            if goals_against == 0:
                ms.loc[mask, f"{pfx}CleanSheets"] = ms.loc[mask, f"{pfx}CleanSheets"].astype(int) + 1

        # Penalty win (KO only)
        pwin = str(res.get("penalty_winner", "")).strip()
        if pwin == "home" and not is_group:
            ms.loc[ms["Team"] == home, "KnockoutPenaltyWins"] = (
                ms.loc[ms["Team"] == home, "KnockoutPenaltyWins"].astype(int) + 1
            )
        elif pwin == "away" and not is_group:
            ms.loc[ms["Team"] == away, "KnockoutPenaltyWins"] = (
                ms.loc[ms["Team"] == away, "KnockoutPenaltyWins"].astype(int) + 1
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
            if match_stats.empty:
                td = {"team": team, "tier": tier_map.get(team, 1),
                      "round_reached": "", "alive": True, "max_remaining": 0.0}
                team_details.append(td)
                continue
            row = match_stats[match_stats["Team"] == team]
            if row.empty:
                continue
            rnd  = str(row.iloc[0].get("RoundReached", "") or "").strip()
            tier = tier_map.get(team, 1)
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

            max_potential += team_max
            team_details.append({
                "team": team, "tier": tier, "round_reached": rnd,
                "alive": alive, "max_remaining": team_max,
            })

        result[player] = {
            "current_score":      current_score,
            "max_potential":      max_potential,
            "max_possible_total": current_score + max_potential,
            "alive_count":        sum(1 for t in team_details if t["alive"]),
            "teams":              sorted(team_details, key=lambda x: (-x["max_remaining"], x["team"])),
        }
    return result


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
        eliminated = rnd == "GroupStage"
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
                if entry and entry["eliminated"]:
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
