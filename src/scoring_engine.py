"""Scoring engine for World Cup 2026 Sweepstake."""

from pathlib import Path
from typing import Optional

import pandas as pd

from src.team_database import load_teams

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
MATCH_STATS_PATH  = _ROOT / "data" / "match_stats.csv"
PLAYER_PICKS_PATH = _ROOT / "data" / "players.csv"
PLAYER_SUMMARY_PATH = _ROOT / "exports" / "player_summary.csv"

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------
CAPTAIN_MULTIPLIER = 1.5          # effective multiplier; bonus = 0.5 × base
INSURANCE_BONUS = 25              # +25 if either T1 team eliminated in groups
PREDICTION_WINNER_BONUS = 30
PREDICTION_GOLDEN_BOOT_BONUS = 25
PREDICTION_RUNNER_UP_BONUS = 20
PREDICTION_BRONZE_BONUS = 15

# Regular match result bonuses
WIN_BONUS = 3                     # any win (normal time, extra time, or penalties)
HAT_TRICK_BONUS = 10              # hat trick scored by any player in the match

# Special match event bonuses
SHIRT_REMOVAL_BONUS = 25          # player removes shirt celebrating
GK_GOAL_BONUS = 75                # goalkeeper scores
RED_CARD_PENALTY = 5              # per red card (applied negatively)
FIRST_ELIMINATED_BONUS = 35       # consolation for owner of first team knocked out

# Tier-upset win bonuses (winner is N tiers below/worse than loser)
UPSET_WIN_BONUSES: dict[int, int] = {1: 15, 2: 30, 3: 50}

# Cumulative dark horse bonuses — awarded for each round reached
DARK_HORSE_BONUSES: dict[str, int] = {
    "QF": 15, "SF": 30, "Final": 40, "Winner": 50,
}

# Progression bonuses per tier — cumulative for each knockout round cleared
PROGRESSION_BONUSES: dict[int, dict[str, int]] = {
    1: {"R32": 2,  "R16": 4,  "QF": 8,  "SF": 16, "Final": 24, "Winner": 30},
    2: {"R32": 4,  "R16": 8,  "QF": 16, "SF": 24, "Final": 36, "Winner": 42},
    3: {"R32": 10, "R16": 16, "QF": 30, "SF": 40, "Final": 64, "Winner": 69},
    4: {"R32": 16, "R16": 24, "QF": 50, "SF": 60, "Final": 90, "Winner": 98},
}

ROUND_ORDER: list[str] = ["GroupStage", "R32", "R16", "QF", "SF", "Final", "Winner"]
KNOCKOUT_ROUNDS: list[str] = ["R32", "R16", "QF", "SF", "Final", "Winner"]
DARK_HORSE_QUALIFYING_ROUNDS: list[str] = ["QF", "SF", "Final", "Winner"]

# Insurance triggers for T1 teams eliminated at or before R32
INSURANCE_ELIGIBLE_ROUNDS = frozenset({"GroupStage", "R32"})

VALID_PURCHASE_TYPES = frozenset({
    "Mulligan", "CompleteRedraw", "PredictionPack", "Insurance", "NinthTeam",
    "Resurrection", "PreTournamentCaptain", "KnockoutCaptain",
})
VALID_CAPTAIN_TYPES = frozenset({"PreTournament", "Knockout"})

# ---------------------------------------------------------------------------
# Data loaders  (return empty schema-correct DataFrames when files are absent)
# ---------------------------------------------------------------------------

def load_match_stats(path: Optional[Path | str] = None) -> pd.DataFrame:
    """Load match stats CSV. Returns empty DataFrame with correct schema if absent."""
    p = Path(path) if path else MATCH_STATS_PATH
    if not p.exists():
        return _empty_match_stats()
    df = pd.read_csv(p)
    _coerce_match_stats(df)
    return df


def load_purchases(path: Optional[Path | str] = None) -> pd.DataFrame:
    from src.competition import load_purchases as _lp
    return _lp()


def load_predictions(path: Optional[Path | str] = None) -> pd.DataFrame:
    p = Path(path) if path else PLAYER_PICKS_PATH
    if not p.exists():
        return pd.DataFrame(columns=[
            "Player", "WorldCupWinner", "RunnerUp", "BronzeMedal",
            "GoldenBoot", "DarkHorse",
        ])
    df = pd.read_csv(p, dtype=str).fillna("")
    cols = ["Player", "WorldCupWinner", "RunnerUp", "BronzeMedal",
            "GoldenBoot", "DarkHorse"]
    return df[[c for c in cols if c in df.columns]].copy()


def load_captains(path: Optional[Path | str] = None) -> pd.DataFrame:
    p = Path(path) if path else PLAYER_PICKS_PATH
    if not p.exists():
        return pd.DataFrame(columns=["Player", "CaptainType", "Team"])
    df = pd.read_csv(p, dtype=str).fillna("")
    rows = []
    for _, row in df.iterrows():
        if row.get("PreTournamentCaptain", "").strip():
            rows.append({"Player": row["Player"], "CaptainType": "PreTournament", "Team": row["PreTournamentCaptain"].strip()})
        if row.get("KnockoutCaptain", "").strip():
            rows.append({"Player": row["Player"], "CaptainType": "Knockout", "Team": row["KnockoutCaptain"].strip()})
    return pd.DataFrame(rows, columns=["Player", "CaptainType", "Team"]) if rows else pd.DataFrame(columns=["Player", "CaptainType", "Team"])


def _empty_match_stats() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "Team", "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins",
        "GroupComebackWins", "GroupWinner", "GroupWins", "GroupHatTricks",
        "KnockoutGoals", "KnockoutCleanSheets", "KnockoutPenaltyWins",
        "KnockoutComebackWins", "KnockoutWins", "KnockoutHatTricks",
        "RoundReached",
        "GroupUpsetWins1", "GroupUpsetWins2", "GroupUpsetWins3",
        "KnockoutUpsetWins1", "KnockoutUpsetWins2", "KnockoutUpsetWins3",
        "ShirtRemovals", "GKGoals", "RedCards", "FirstEliminated",
    ])


def _coerce_match_stats(df: pd.DataFrame) -> None:
    """In-place numeric coercion for match stats columns."""
    int_cols = [
        "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins", "GroupComebackWins",
        "GroupWinner", "GroupWins", "GroupHatTricks",
        "KnockoutGoals", "KnockoutCleanSheets", "KnockoutPenaltyWins",
        "KnockoutComebackWins", "KnockoutWins", "KnockoutHatTricks",
        "GroupUpsetWins1", "GroupUpsetWins2", "GroupUpsetWins3",
        "KnockoutUpsetWins1", "KnockoutUpsetWins2", "KnockoutUpsetWins3",
        "ShirtRemovals", "GKGoals", "RedCards", "FirstEliminated",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "RoundReached" in df.columns:
        df["RoundReached"] = df["RoundReached"].fillna("").astype(str)


def _safe_int(val: object) -> int:
    """Convert a value to int safely, returning 0 for None / NaN / invalid."""
    try:
        if val is None:
            return 0
        f = float(val)  # type: ignore[arg-type]
        return 0 if f != f else int(f)  # f != f is True only for NaN
    except (TypeError, ValueError):
        return 0

# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------

def get_effective_teams(
    player: str,
    assignments: dict[str, list[str]],
    purchases: pd.DataFrame,
) -> dict[str, list[str]]:
    """Return effective team rosters per tournament stage after purchases.

    group_stage:  base 8 teams — never modified
    knockout:     base ± resurrections + ninth team

    Resurrection Selection format: "EliminatedTeam->ReplacementTeam"
    NinthTeam    Selection format: "<team name>"
    """
    base = list(assignments.get(player, []))
    gs_teams: list[str] = list(base)
    ko_teams: list[str] = list(base)

    if purchases.empty:
        return {"group_stage": gs_teams, "knockout": ko_teams}

    p = purchases[purchases["Player"] == player]

    # Ninth team — first purchase wins; appended to knockout roster only
    ninth_rows = p[p["PurchaseType"] == "NinthTeam"]
    if not ninth_rows.empty:
        sel = str(ninth_rows.iloc[0].get("Selection", "") or "").strip()
        if sel:
            ko_teams = ko_teams + [sel]

    # Resurrections — replace eliminated team in knockout roster
    for _, row in p[p["PurchaseType"] == "Resurrection"].iterrows():
        sel = str(row.get("Selection", "") or "").strip()
        if "->" in sel:
            eliminated, replacement = [s.strip() for s in sel.split("->", 1)]
            if eliminated in ko_teams:
                ko_teams = list(ko_teams)
                ko_teams[ko_teams.index(eliminated)] = replacement

    return {"group_stage": gs_teams, "knockout": ko_teams}

# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------

def calculate_team_points(
    team: str,
    match_stats: pd.DataFrame,
    tier: int,
) -> dict:
    """Points earned by one team from match events, progression bonuses, and special events.

    Returns {group_stage, knockout, special, total, breakdown}.
    - group_stage: goals + clean sheets + group-stage upset wins
    - knockout:    the same from knockout rounds PLUS cumulative progression bonuses + KO upset wins
    - special:     shirt removals, GK goals, red cards, first-eliminated bonus
                   (included in pre-tournament captain bonus but NOT knockout captain)
    """
    row = match_stats.loc[match_stats["Team"] == team]
    if row.empty:
        return {"group_stage": 0.0, "knockout": 0.0, "special": 0.0, "total": 0.0, "breakdown": {}}

    r = row.iloc[0]
    breakdown: dict[str, float] = {}
    gs = 0.0
    ko = 0.0

    # Group stage match points
    for col, pts_each in [
        ("GroupGoals", 1), ("GroupCleanSheets", 2),
        ("GroupPenaltyWins", 3), ("GroupComebackWins", 3),
        ("GroupWins", WIN_BONUS), ("GroupHatTricks", HAT_TRICK_BONUS),
    ]:
        count = _safe_int(r.get(col, 0))
        pts = float(count * pts_each)
        if pts:
            breakdown[col] = pts
        gs += pts

    if _safe_int(r.get("GroupWinner", 0)):
        breakdown["GroupWinner"] = 3.0
        gs += 3.0

    # Group stage upset wins
    for diff, bonus in UPSET_WIN_BONUSES.items():
        col = f"GroupUpsetWins{diff}"
        count = _safe_int(r.get(col, 0))
        pts = float(count * bonus)
        if pts:
            breakdown[col] = pts
        gs += pts

    # Knockout match points
    for col, pts_each in [
        ("KnockoutGoals", 1), ("KnockoutCleanSheets", 2),
        ("KnockoutPenaltyWins", 3), ("KnockoutComebackWins", 3),
        ("KnockoutWins", WIN_BONUS), ("KnockoutHatTricks", HAT_TRICK_BONUS),
    ]:
        count = _safe_int(r.get(col, 0))
        pts = float(count * pts_each)
        if pts:
            breakdown[col] = pts
        ko += pts

    # Knockout upset wins
    for diff, bonus in UPSET_WIN_BONUSES.items():
        col = f"KnockoutUpsetWins{diff}"
        count = _safe_int(r.get(col, 0))
        pts = float(count * bonus)
        if pts:
            breakdown[col] = pts
        ko += pts

    # Progression bonuses — cumulative for each round cleared
    round_reached = str(r.get("RoundReached", "") or "").strip()
    if round_reached in ROUND_ORDER:
        reached_idx = ROUND_ORDER.index(round_reached)
        tier_bonuses = PROGRESSION_BONUSES.get(tier, {})
        for rnd in KNOCKOUT_ROUNDS:
            if ROUND_ORDER.index(rnd) <= reached_idx:
                pts = float(tier_bonuses.get(rnd, 0))
                if pts:
                    breakdown[f"Progression_{rnd}"] = pts
                    ko += pts

    # Special event bonuses (separate bucket — included in pre-tournament captain bonus)
    shirt   = _safe_int(r.get("ShirtRemovals", 0))
    gk      = _safe_int(r.get("GKGoals", 0))
    red     = _safe_int(r.get("RedCards", 0))
    first_e = _safe_int(r.get("FirstEliminated", 0))

    if shirt:   breakdown["ShirtRemovals"]  = float(shirt * SHIRT_REMOVAL_BONUS)
    if gk:      breakdown["GKGoals"]        = float(gk * GK_GOAL_BONUS)
    if red:     breakdown["RedCards"]       = float(-red * RED_CARD_PENALTY)
    if first_e: breakdown["FirstEliminated"] = float(FIRST_ELIMINATED_BONUS)

    special = float(
        shirt   * SHIRT_REMOVAL_BONUS
        + gk    * GK_GOAL_BONUS
        - red   * RED_CARD_PENALTY
        + first_e * FIRST_ELIMINATED_BONUS
    )

    total = gs + ko + special
    return {"group_stage": gs, "knockout": ko, "special": special, "total": total, "breakdown": breakdown}


def calculate_captain_bonus(
    player: str,
    team_points_map: dict[str, dict],
    captains: pd.DataFrame,
    effective_teams: dict[str, list[str]],
) -> dict:
    """Extra points from captain selections.

    PreTournament captain: +0.5 × total team points (all stages)
    Knockout captain:      +0.5 × knockout team points only

    The same team cannot be chosen for both captain slots.

    Returns {pre_tournament_captain, pre_tournament_bonus,
             knockout_captain, knockout_bonus, total}
    """
    result = {
        "pre_tournament_captain": None,
        "pre_tournament_bonus": 0.0,
        "knockout_captain": None,
        "knockout_bonus": 0.0,
        "total": 0.0,
    }
    if captains.empty:
        return result

    p = captains[captains["Player"] == player]
    gs_set = set(effective_teams.get("group_stage", []))
    ko_set = set(effective_teams.get("knockout", []))

    pre_rows = p[p["CaptainType"] == "PreTournament"]
    if not pre_rows.empty:
        team = str(pre_rows.iloc[0]["Team"]).strip()
        result["pre_tournament_captain"] = team
        if team in gs_set or team in ko_set:
            pts = team_points_map.get(team, {})
            bonus = 0.5 * pts.get("total", 0.0)
            result["pre_tournament_bonus"] = bonus
            result["total"] += bonus

    ko_rows = p[p["CaptainType"] == "Knockout"]
    if not ko_rows.empty:
        team = str(ko_rows.iloc[0]["Team"]).strip()
        result["knockout_captain"] = team
        if team in ko_set:
            pts = team_points_map.get(team, {})
            bonus = 0.5 * pts.get("knockout", 0.0)
            result["knockout_bonus"] = bonus
            result["total"] += bonus

    return result


def calculate_insurance_bonus(
    player: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    tier_map: dict[str, int],
) -> float:
    """Return INSURANCE_BONUS per base Tier 1 team eliminated in the group stage.

    +25 if one T1 team goes out before the Round of 16.
    +50 if both T1 teams go out before the Round of 16.
    Only applies to the player's original 8-team allocation (not Ninth/Resurrection).
    Requires a processed Insurance purchase.
    """
    if purchases.empty:
        return 0.0

    p = purchases[purchases["Player"] == player]
    if p[p["PurchaseType"] == "Insurance"].empty:
        return 0.0

    t1_teams = [t for t in assignments.get(player, []) if tier_map.get(t, 0) == 1]
    count = 0
    for team in t1_teams:
        row = match_stats[match_stats["Team"] == team]
        if row.empty:
            continue
        round_reached = str(row.iloc[0].get("RoundReached", "") or "").strip()
        if round_reached in INSURANCE_ELIGIBLE_ROUNDS:
            count += 1

    return float(count * INSURANCE_BONUS)


def calculate_prediction_points(
    player: str,
    predictions: pd.DataFrame,
    tournament_results: dict,
) -> dict:
    """Bonus points from Prediction Pack.

    tournament_results expected keys:
        world_cup_winner:    str  — winning team name
        runner_up:           str  — runner-up team name
        bronze_winner:       str  — 3rd place team name
        golden_boot_winner:  str  — golden boot winner name
        first_knocked_out:   str  — first team eliminated (auto-derived if absent)
        dark_horse_rounds:   dict[str, str]  — team -> round_reached

    Dark horse bonuses are cumulative: each qualifying round adds more.

    Returns prediction picks and bonus values for all categories.
    """
    result = {
        "world_cup_winner": None, "runner_up": None, "bronze_winner": None,
        "golden_boot": None, "dark_horse": None,
        "winner_bonus": 0.0, "runner_up_bonus": 0.0, "bronze_bonus": 0.0,
        "golden_boot_bonus": 0.0, "dark_horse_bonus": 0.0,
        "total": 0.0,
    }
    if predictions.empty or not tournament_results:
        return result

    p = predictions[predictions["Player"] == player]
    if p.empty:
        return result

    pred = p.iloc[0]

    # World Cup Winner (+30)
    predicted_winner = str(pred.get("WorldCupWinner", "") or "").strip()
    result["world_cup_winner"] = predicted_winner or None
    actual_winner = str(tournament_results.get("world_cup_winner", "") or "").strip()
    if predicted_winner and predicted_winner == actual_winner:
        result["winner_bonus"] = float(PREDICTION_WINNER_BONUS)
        result["total"] += result["winner_bonus"]

    # Runner-up (+20)
    predicted_ru = str(pred.get("RunnerUp", "") or "").strip()
    result["runner_up"] = predicted_ru or None
    actual_ru = str(tournament_results.get("runner_up", "") or "").strip()
    if predicted_ru and predicted_ru == actual_ru:
        result["runner_up_bonus"] = float(PREDICTION_RUNNER_UP_BONUS)
        result["total"] += result["runner_up_bonus"]

    # Bronze Medal (+15)
    predicted_bronze = str(pred.get("BronzeMedal", "") or "").strip()
    result["bronze_winner"] = predicted_bronze or None
    actual_bronze = str(tournament_results.get("bronze_winner", "") or "").strip()
    if predicted_bronze and predicted_bronze == actual_bronze:
        result["bronze_bonus"] = float(PREDICTION_BRONZE_BONUS)
        result["total"] += result["bronze_bonus"]

    # Golden Boot (+25)
    predicted_gb = str(pred.get("GoldenBoot", "") or "").strip()
    result["golden_boot"] = predicted_gb or None
    actual_gb = str(tournament_results.get("golden_boot_winner", "") or "").strip()
    if predicted_gb and predicted_gb == actual_gb:
        result["golden_boot_bonus"] = float(PREDICTION_GOLDEN_BOOT_BONUS)
        result["total"] += result["golden_boot_bonus"]

    # Dark Horse — cumulative per qualifying round reached
    predicted_dh = str(pred.get("DarkHorse", "") or "").strip()
    result["dark_horse"] = predicted_dh or None
    dh_rounds_map = tournament_results.get("dark_horse_rounds", {})
    dh_round = str(dh_rounds_map.get(predicted_dh, "") or "").strip()

    if predicted_dh and dh_round and dh_round in ROUND_ORDER:
        reached_idx = ROUND_ORDER.index(dh_round)
        dh_total = 0.0
        for rnd in DARK_HORSE_QUALIFYING_ROUNDS:
            if ROUND_ORDER.index(rnd) <= reached_idx:
                dh_total += float(DARK_HORSE_BONUSES.get(rnd, 0))
        result["dark_horse_bonus"] = dh_total
        result["total"] += dh_total

    return result


def calculate_player_points(
    player: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    tournament_results: Optional[dict] = None,
    tier_map: Optional[dict[str, int]] = None,
    swap_offsets: Optional["pd.DataFrame"] = None,
) -> dict:
    """Complete points calculation for one player.  No file I/O — all data
    must be passed in.  Use load_* helpers to hydrate arguments from disk.

    Returns a detailed breakdown dict with grand_total as the summary figure.
    """
    if tier_map is None:
        df = load_teams()
        tier_map = dict(zip(df["Team"], df["Tier"].astype(int)))

    tr = dict(tournament_results or {})

    eff = get_effective_teams(player, assignments, purchases)
    gs_teams = eff["group_stage"]
    ko_teams = eff["knockout"]

    all_relevant = list({*gs_teams, *ko_teams})
    team_pts: dict[str, dict] = {
        t: calculate_team_points(t, match_stats, tier_map.get(t, 1))
        for t in all_relevant
    }

    # Apply team-swap point offsets
    hist_teams: list[str] = []
    if swap_offsets is not None and not swap_offsets.empty:
        # Teams this player received — deduct the points those teams had at swap time
        received = swap_offsets[swap_offsets["NewOwner"] == player]
        for _, row in received.iterrows():
            team = str(row["Team"])
            if team in team_pts:
                tp = team_pts[team]
                gs_d = float(row["GroupStagePoints"])
                ko_d = float(row["KnockoutPoints"])
                sp_d = float(row["SpecialPoints"])
                team_pts[team] = {
                    "group_stage": max(0.0, tp["group_stage"] - gs_d),
                    "knockout":    max(0.0, tp["knockout"]    - ko_d),
                    "special":     max(0.0, tp["special"]     - sp_d),
                    "total":       max(0.0, tp["total"]       - gs_d - ko_d - sp_d),
                    "breakdown":   tp.get("breakdown", {}),
                }
        # Teams this player gave away — add their pre-swap points back as historical credit
        gave_away = swap_offsets[swap_offsets["OriginalOwner"] == player]
        for _, row in gave_away.iterrows():
            team = str(row["Team"])
            hist_teams.append(team)
            team_pts[team] = {
                "group_stage": float(row["GroupStagePoints"]),
                "knockout":    float(row["KnockoutPoints"]),
                "special":     float(row["SpecialPoints"]),
                "total":       float(row["TotalPoints"]),
                "breakdown":   {},
            }

    gs_total      = sum(team_pts[t]["group_stage"] for t in list(gs_teams) + hist_teams)
    ko_total      = sum(team_pts[t]["knockout"]    for t in list(ko_teams) + hist_teams)
    special_total = sum(team_pts[t]["special"]     for t in list(all_relevant) + hist_teams)
    base_total    = gs_total + ko_total  # match events + progression + upset wins

    # For captain bonus: include historical teams so pre-swap captain credit is preserved
    eff_for_captain = {
        "group_stage": list(gs_teams) + hist_teams,
        "knockout":    list(ko_teams) + hist_teams,
    }
    captain_info  = calculate_captain_bonus(player, team_pts, captains, eff_for_captain)
    insurance_pts = calculate_insurance_bonus(
        player, assignments, match_stats, purchases, tier_map
    )
    pred_info = calculate_prediction_points(player, predictions, tr)

    grand_total = (
        base_total
        + captain_info["total"]
        + insurance_pts
        + special_total
        + pred_info["total"]
    )

    return {
        "player": player,
        "group_stage_teams": gs_teams,
        "knockout_teams": ko_teams,
        "historical_teams": hist_teams,
        "team_points": team_pts,
        "group_stage_points": gs_total,
        "knockout_points": ko_total,
        "special_bonus": special_total,
        "base_total": base_total,
        "captain": captain_info,
        "insurance_bonus": insurance_pts,
        "predictions": pred_info,
        "grand_total": grand_total,
    }


def calculate_leaderboard(
    participants: list[str],
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    tournament_results: Optional[dict] = None,
    swap_offsets: Optional["pd.DataFrame"] = None,
) -> pd.DataFrame:
    """Full ranked leaderboard for all participants.

    Auto-builds dark_horse_rounds from match_stats if not in tournament_results.

    Returns DataFrame: Rank, Player, BasePoints, CaptainBonus,
    InsuranceBonus, PredictionBonus, TotalPoints.
    """
    df = load_teams()
    tier_map = dict(zip(df["Team"], df["Tier"].astype(int)))

    tr = dict(tournament_results or {})
    if "dark_horse_rounds" not in tr and not match_stats.empty:
        tr["dark_horse_rounds"] = {
            str(row["Team"]): str(row.get("RoundReached", "") or "")
            for _, row in match_stats.iterrows()
        }
    rows = []
    for player in participants:
        info = calculate_player_points(
            player, assignments, match_stats, purchases,
            captains, predictions, tr, tier_map, swap_offsets=swap_offsets,
        )
        # Sum per-event breakdown across all this player's teams
        all_teams = list({*info["group_stage_teams"], *info["knockout_teams"]})
        bd: dict[str, float] = {}
        for t in all_teams:
            for k, v in info["team_points"].get(t, {}).get("breakdown", {}).items():
                bd[k] = bd.get(k, 0.0) + float(v)

        rows.append({
            "Player":            player,
            "BasePoints":        info["base_total"],
            "GroupStagePoints":  info["group_stage_points"],
            "KnockoutPoints":    info["knockout_points"],
            "CaptainBonus":      info["captain"]["total"],
            "InsuranceBonus":    info["insurance_bonus"],
            "SpecialBonus":      info["special_bonus"],
            "PredictionBonus":   info["predictions"]["total"],
            "TotalPoints":       info["grand_total"],
            # Detailed match-event breakdown
            "GoalsPoints":      bd.get("GroupGoals", 0) + bd.get("KnockoutGoals", 0),
            "CleanSheetPoints": bd.get("GroupCleanSheets", 0) + bd.get("KnockoutCleanSheets", 0),
            "WinPoints":        bd.get("GroupWins", 0) + bd.get("KnockoutWins", 0) + bd.get("GroupWinner", 0),
            "WinBonusPoints":   (bd.get("GroupPenaltyWins", 0) + bd.get("KnockoutPenaltyWins", 0) +
                                 bd.get("GroupComebackWins", 0) + bd.get("KnockoutComebackWins", 0)),
            "HatTrickPoints":   bd.get("GroupHatTricks", 0) + bd.get("KnockoutHatTricks", 0),
            "UpsetPoints":      sum(v for k, v in bd.items() if "UpsetWins" in k),
            "ProgressionPoints": sum(v for k, v in bd.items() if k.startswith("Progression_")),
            "ShirtPoints":      bd.get("ShirtRemovals", 0),
            "GKGoalPoints":     bd.get("GKGoals", 0),
            "RedCardPoints":    bd.get("RedCards", 0),
            "FirstElimPoints":  bd.get("FirstEliminated", 0),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "Rank", "Player", "BasePoints", "CaptainBonus",
            "InsuranceBonus", "SpecialBonus", "PredictionBonus", "TotalPoints",
            "GoalsPoints", "CleanSheetPoints", "WinPoints", "WinBonusPoints",
            "HatTrickPoints", "UpsetPoints", "ProgressionPoints",
            "ShirtPoints", "GKGoalPoints", "RedCardPoints", "FirstElimPoints",
        ])

    lb = (
        pd.DataFrame(rows)
        .sort_values("TotalPoints", ascending=False)
        .reset_index(drop=True)
    )
    lb.insert(0, "Rank", range(1, len(lb) + 1))
    return lb

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_captains(player: str, captains: pd.DataFrame) -> list[str]:
    """Validate captain selections for a player.  Returns list of error strings."""
    errors: list[str] = []
    if captains.empty:
        return errors

    p = captains[captains["Player"] == player]
    pre_rows = p[p["CaptainType"] == "PreTournament"]
    ko_rows  = p[p["CaptainType"] == "Knockout"]

    if len(pre_rows) > 1:
        errors.append(f"{player}: multiple PreTournament captain entries")
    if len(ko_rows) > 1:
        errors.append(f"{player}: multiple Knockout captain entries")

    if not pre_rows.empty and not ko_rows.empty:
        pre_team = str(pre_rows.iloc[0]["Team"]).strip()
        ko_team  = str(ko_rows.iloc[0]["Team"]).strip()
        if pre_team and pre_team == ko_team:
            errors.append(
                f"{player}: same team '{pre_team}' selected for both captain types"
            )
    return errors


def validate_purchases(player: str, purchases: pd.DataFrame) -> list[str]:
    """Validate purchase history for a player.  Returns list of error strings."""
    errors: list[str] = []
    if purchases.empty:
        return errors

    p = purchases[purchases["Player"] == player]

    for ptype in ["NinthTeam", "Resurrection", "Insurance", "PredictionPack"]:
        count = int((p["PurchaseType"] == ptype).sum())
        if count > 1:
            errors.append(f"{player}: {ptype} purchased {count} times (max 1)")

    for ptype in p["PurchaseType"].unique():
        if ptype not in VALID_PURCHASE_TYPES:
            errors.append(f"{player}: unknown purchase type '{ptype}'")

    return errors

# ---------------------------------------------------------------------------
# Player summary (transparency)
# ---------------------------------------------------------------------------

def generate_player_summary(
    participants: list[str],
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    tournament_results: Optional[dict] = None,
    output_path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Write exports/player_summary.csv so every participant can verify their score.

    Returns the summary as a DataFrame in addition to writing the file.
    """
    df_teams = load_teams()
    tier_map = dict(zip(df_teams["Team"], df_teams["Tier"].astype(int)))

    out = Path(output_path) if output_path else PLAYER_SUMMARY_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    tr = dict(tournament_results or {})
    if "dark_horse_rounds" not in tr and not match_stats.empty:
        tr["dark_horse_rounds"] = {
            str(row["Team"]): str(row.get("RoundReached", "") or "")
            for _, row in match_stats.iterrows()
        }

    rows = []
    for player in participants:
        info = calculate_player_points(
            player, assignments, match_stats, purchases,
            captains, predictions, tr, tier_map,
        )
        p_rows = (
            purchases[purchases["Player"] == player]
            if not purchases.empty
            else pd.DataFrame()
        )

        has_insurance = (
            not p_rows.empty
            and not p_rows[p_rows["PurchaseType"] == "Insurance"].empty
        )
        ninth = ""
        if not p_rows.empty:
            n = p_rows[p_rows["PurchaseType"] == "NinthTeam"]
            if not n.empty:
                ninth = str(n.iloc[0].get("Selection", "") or "").strip()

        resurrection = ""
        if not p_rows.empty:
            r = p_rows[p_rows["PurchaseType"] == "Resurrection"]
            if not r.empty:
                sel = str(r.iloc[0].get("Selection", "") or "").strip()
                if "->" in sel:
                    resurrection = sel.split("->", 1)[1].strip()

        cap  = info["captain"]
        pred = info["predictions"]
        rows.append({
            "Player":               player,
            "TeamsOwned":           "; ".join(info["group_stage_teams"]),
            "PreTournamentCaptain": cap["pre_tournament_captain"] or "",
            "KnockoutCaptain":      cap["knockout_captain"] or "",
            "WorldCupWinnerPick":   pred["world_cup_winner"] or "",
            "RunnerUpPick":         pred["runner_up"] or "",
            "BronzeMedalPick":      pred["bronze_winner"] or "",
            "GoldenBootPick":       pred["golden_boot"] or "",
            "DarkHorsePick":        pred["dark_horse"] or "",
            "InsuranceStatus":      "Yes" if has_insurance else "No",
            "NinthTeam":            ninth,
            "ResurrectionTeam":     resurrection,
            "BasePoints":           info["base_total"],
            "CaptainBonus":         cap["total"],
            "InsuranceBonus":       info["insurance_bonus"],
            "SpecialBonus":         info["special_bonus"],
            "PredictionBonus":      pred["total"],
            "TotalPoints":          info["grand_total"],
        })

    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    return df
