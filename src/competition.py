"""Competition logic layer for World Cup 2026 Sweepstake."""

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from src.allocation_engine import repick_participant, validate_allocations, Allocation
from src.scoring_engine import (
    calculate_leaderboard as _score_leaderboard,
    get_effective_teams,
    INSURANCE_BONUS,
)
from src.team_database import load_teams as _load_teams

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
DATA_DIR  = _ROOT / "data"
EXPORTS_DIR = _ROOT / "exports"

PLAYER_STATUS_PATH = DATA_DIR / "players.csv"
PURCHASES_PATH     = DATA_DIR / "purchases.csv"
EVENTS_PATH        = DATA_DIR / "events.csv"
AUDIT_LOG_PATH     = DATA_DIR / "audit_log.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLAYER_STATUSES    = frozenset({"UNPAID", "PAID"})
PURCHASE_TYPES     = frozenset({
    "BuyIn", "PredictionPack", "Mulligan", "NinthTeam", "Resurrection", "Insurance",
})
PURCHASE_STATUSES  = frozenset({"PENDING", "PROCESSED", "CANCELLED"})
EVENT_TYPES        = frozenset({
    "INITIAL_DRAW", "MULLIGAN_DRAW", "NINTH_TEAM_DRAW", "RESURRECTION_DRAW",
})
EVENT_STATUSES     = frozenset({"SCHEDULED", "OPEN", "CLOSED", "EXECUTED"})

QF_ROUNDS = frozenset({"QF", "SF", "Final", "Winner"})

PRICES: dict[str, float] = {
    "BuyIn":        5.0,
    "PredictionPack": 5.0,
    "Mulligan":     3.0,
    "NinthTeam":    3.0,
    "Resurrection": 5.0,
    "Insurance":    2.0,
}

PRIZE_SHARES = (0.50, 0.30, 0.20)   # 1st, 2nd, 3rd

# Maps competition purchase types → scoring engine purchase types
_SCORING_TYPE_MAP: dict[str, str] = {
    "NinthTeam":      "NinthTeam",
    "Resurrection":   "Resurrection",
    "PredictionPack": "PredictionPack",
    "Insurance":      "Insurance",
}

# Full purchase name → PURCHASE_TYPE (for payment reference parsing)
_NAME_TO_TYPE: dict[str, str] = {
    "BUY IN":          "BuyIn",
    "PREDICTION PACK": "PredictionPack",
    "MULLIGAN":        "Mulligan",
    "NINTH TEAM":      "NinthTeam",
    "RESURRECTION":    "Resurrection",
    "INSURANCE":       "Insurance",
}

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_int(val: object) -> int:
    try:
        if val is None:
            return 0
        f = float(val)  # type: ignore[arg-type]
        return 0 if f != f else int(f)
    except (TypeError, ValueError):
        return 0

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_player_status(path: Optional[Path | str] = None) -> pd.DataFrame:
    p = Path(path) if path else PLAYER_STATUS_PATH
    if not p.exists():
        return pd.DataFrame(columns=[
            "Player", "Status", "PaidTimestamp",
            "PreTournamentCaptain", "KnockoutCaptain",
            "WorldCupWinner", "GoldenBoot", "DarkHorse",
        ])
    return pd.read_csv(p, dtype=str).fillna("")


def load_purchases(path: Optional[Path | str] = None) -> pd.DataFrame:
    p = Path(path) if path else PURCHASES_PATH
    if not p.exists():
        return pd.DataFrame(columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])
    return pd.read_csv(p, dtype=str).fillna("")


def load_events(path: Optional[Path | str] = None) -> pd.DataFrame:
    p = Path(path) if path else EVENTS_PATH
    if not p.exists():
        return pd.DataFrame(columns=[
            "EventID", "EventType", "ScheduledTime", "ExecutedTime", "Status", "RandomSeed",
        ])
    return pd.read_csv(p, dtype=str).fillna("")


def load_audit_log(path: Optional[Path | str] = None) -> pd.DataFrame:
    p = Path(path) if path else AUDIT_LOG_PATH
    if not p.exists():
        return pd.DataFrame(columns=["Timestamp", "Event", "Player", "Action", "Result"])
    return pd.read_csv(p, dtype=str).fillna("")

# ---------------------------------------------------------------------------
# Player status
# ---------------------------------------------------------------------------

def get_player_status(player: str, statuses: pd.DataFrame) -> str:
    """Return PAID or UNPAID. Defaults to UNPAID if player not found."""
    if statuses.empty:
        return "UNPAID"
    row = statuses[statuses["Player"] == player]
    return str(row.iloc[0]["Status"]).strip() if not row.empty else "UNPAID"


def mark_paid(
    player: str,
    statuses: pd.DataFrame,
    timestamp: Optional[str] = None,
) -> pd.DataFrame:
    """Return updated statuses with player set to PAID."""
    ts = timestamp or _now_iso()
    df = statuses.copy() if not statuses.empty else pd.DataFrame(
        columns=["Player", "Status", "PaidTimestamp"]
    )
    mask = df["Player"] == player
    if mask.any():
        df.loc[mask, "Status"] = "PAID"
        df.loc[mask, "PaidTimestamp"] = ts
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"Player": player, "Status": "PAID", "PaidTimestamp": ts}])],
            ignore_index=True,
        )
    return df


def mark_unpaid(player: str, statuses: pd.DataFrame) -> pd.DataFrame:
    """Return updated statuses with player set to UNPAID."""
    df = statuses.copy() if not statuses.empty else pd.DataFrame(
        columns=["Player", "Status", "PaidTimestamp"]
    )
    mask = df["Player"] == player
    if mask.any():
        df.loc[mask, "Status"] = "UNPAID"
        df.loc[mask, "PaidTimestamp"] = ""
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"Player": player, "Status": "UNPAID", "PaidTimestamp": ""}])],
            ignore_index=True,
        )
    return df


def get_paid_players(statuses: pd.DataFrame) -> list[str]:
    if statuses.empty:
        return []
    return statuses[statuses["Status"] == "PAID"]["Player"].tolist()


def get_unpaid_players(statuses: pd.DataFrame) -> list[str]:
    if statuses.empty:
        return []
    return statuses[statuses["Status"] != "PAID"]["Player"].tolist()

# ---------------------------------------------------------------------------
# Purchase management
# ---------------------------------------------------------------------------

def add_purchase(
    player: str,
    ptype: str,
    reference: str,
    purchases: pd.DataFrame,
    timestamp: Optional[str] = None,
    selection: str = "",
) -> pd.DataFrame:
    """Return updated purchases with a new row."""
    new_row = {
        "Player": player, "PurchaseType": ptype,
        "Timestamp": timestamp or _now_iso(), "Reference": reference, "Selection": selection,
    }
    return pd.concat([purchases, pd.DataFrame([new_row])], ignore_index=True)




def get_player_purchases(player: str, purchases: pd.DataFrame) -> pd.DataFrame:
    if purchases.empty:
        return pd.DataFrame(columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])
    return purchases[purchases["Player"] == player].copy()


def purchases_to_scoring_format(purchases: pd.DataFrame) -> pd.DataFrame:
    """Translate competition purchases to scoring engine format.

    Only NINTH, RESURRECTION, PACK, and INSURANCE are meaningful to the scorer.
    BUYIN and MULLIGAN are financial-only and have no scoring effect.
    """
    cols = ["Player", "PurchaseType", "Selection", "Timestamp"]
    if purchases.empty:
        return pd.DataFrame(columns=cols)

    relevant = purchases[purchases["PurchaseType"].isin(_SCORING_TYPE_MAP)].copy()
    if relevant.empty:
        return pd.DataFrame(columns=cols)

    relevant["PurchaseType"] = relevant["PurchaseType"].map(_SCORING_TYPE_MAP)
    if "Selection" not in relevant.columns:
        relevant["Selection"] = ""
    relevant["Selection"] = relevant["Selection"].fillna("")
    return relevant[cols].reset_index(drop=True)

# ---------------------------------------------------------------------------
# Payment reference parsing
# ---------------------------------------------------------------------------

def parse_payment_reference(reference: str) -> dict:
    """Parse a Revolut payment reference into player and purchase types.

    Format: "PLAYER - PURCHASE NAME, PURCHASE NAME"
    Returns {"player": str, "items": list[str]}.
    """
    if " - " not in reference:
        return {"player": "", "items": []}
    player_part, items_part = reference.split(" - ", 1)
    player = player_part.strip()
    items = []
    for raw in items_part.split(","):
        ptype = _NAME_TO_TYPE.get(raw.strip().upper())
        if ptype:
            items.append(ptype)
    return {"player": player, "items": items}

# ---------------------------------------------------------------------------
# Prize pool
# ---------------------------------------------------------------------------

def calculate_prize_pool(purchases: pd.DataFrame) -> dict:
    """Sum all purchase fees and return prize distribution.

    Returns {current_pot, first_prize, second_prize, third_prize}.
    """
    if purchases.empty:
        total = 0.0
    else:
        total = float(purchases["PurchaseType"].map(PRICES).fillna(0.0).sum())

    return {
        "current_pot":  total,
        "first_prize":  round(total * PRIZE_SHARES[0], 2),
        "second_prize": round(total * PRIZE_SHARES[1], 2),
        "third_prize":  round(total * PRIZE_SHARES[2], 2),
    }


def export_prize_pool(
    purchases: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    out = Path(path) if path else EXPORTS_DIR / "prize_pool.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pool = calculate_prize_pool(purchases)
    df = pd.DataFrame([{
        "CurrentPot": pool["current_pot"], "FirstPrize":  pool["first_prize"],
        "SecondPrize": pool["second_prize"], "ThirdPrize": pool["third_prize"],
    }])
    df.to_csv(out, index=False)
    return df

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def create_event(
    event_type: str,
    scheduled_time: str,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Return updated events with a new SCHEDULED event appended."""
    if events.empty or "EventID" not in events.columns:
        event_id = "1"
    else:
        numeric = pd.to_numeric(events["EventID"], errors="coerce").dropna()
        event_id = str(int(numeric.max()) + 1) if not numeric.empty else "1"

    new_row = {
        "EventID": event_id, "EventType": event_type,
        "ScheduledTime": scheduled_time, "ExecutedTime": "",
        "Status": "SCHEDULED", "RandomSeed": "",
    }
    return pd.concat([events, pd.DataFrame([new_row])], ignore_index=True)


def update_event_status(
    event_id: str,
    status: str,
    events: pd.DataFrame,
    seed: Optional[int] = None,
    executed_time: Optional[str] = None,
) -> pd.DataFrame:
    """Return updated events with the given event moved to a new status."""
    df = events.copy()
    mask = df["EventID"].astype(str) == str(event_id)
    if not mask.any():
        return df
    idx = df[mask].index[0]
    df.loc[idx, "Status"] = status
    if status == "EXECUTED":
        df.loc[idx, "ExecutedTime"] = executed_time or _now_iso()
        if seed is not None:
            df.loc[idx, "RandomSeed"] = str(seed)
    return df

# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def log_action(
    event: str,
    player: str,
    action: str,
    result: str,
    audit_log: pd.DataFrame,
    timestamp: Optional[str] = None,
) -> pd.DataFrame:
    """Return updated audit log with a new entry appended."""
    new_row = {
        "Timestamp": timestamp or _now_iso(),
        "Event": event, "Player": player, "Action": action, "Result": result,
    }
    return pd.concat([audit_log, pd.DataFrame([new_row])], ignore_index=True)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_dark_horse(
    player: str,
    team: str,
    assignments: dict[str, list[str]],
    tier_map: dict[str, int],
) -> list[str]:
    """Dark Horse must be Tier 3 or 4 and not a team owned by the player."""
    errors: list[str] = []
    tier = tier_map.get(team)
    if tier is None:
        errors.append(f"Unknown team: {team!r}")
    elif tier < 3:
        errors.append(f"Dark Horse must be Tier 3 or 4; {team!r} is Tier {tier}")
    if team in assignments.get(player, []):
        errors.append(f"Dark Horse cannot be owned by {player}: {team!r}")
    return errors


def validate_ninth_team(
    player: str,
    team: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
) -> list[str]:
    """Ninth team must be surviving and not already effectively owned."""
    errors: list[str] = []
    owned = _effective_owned(player, assignments, purchases)
    if team in owned:
        errors.append(f"{team!r} is already owned by {player}")
    if not match_stats.empty:
        row = match_stats[match_stats["Team"] == team]
        if not row.empty:
            rr = str(row.iloc[0].get("RoundReached", "") or "").strip()
            if not rr or rr == "GroupStage":
                errors.append(f"{team!r} did not survive the group stage")
    return errors


def validate_resurrection(
    player: str,
    eliminated_team: str,
    replacement_team: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    tier_map: dict[str, int],
    purchases: pd.DataFrame,
) -> list[str]:
    """Resurrection rules: eliminated must be owned+eliminated; replacement must be
    same tier, surviving, and not already owned.
    """
    errors: list[str] = []
    owned = _effective_owned(player, assignments, purchases)

    if eliminated_team not in assignments.get(player, []):
        errors.append(f"{eliminated_team!r} is not in {player}'s base allocation")

    if not match_stats.empty:
        row = match_stats[match_stats["Team"] == eliminated_team]
        if not row.empty:
            rr = str(row.iloc[0].get("RoundReached", "") or "").strip()
            if rr and rr != "GroupStage":
                errors.append(f"{eliminated_team!r} has not been eliminated (round={rr!r})")

    elim_tier = tier_map.get(eliminated_team)
    repl_tier = tier_map.get(replacement_team)
    if repl_tier is None:
        errors.append(f"Unknown replacement team: {replacement_team!r}")
    elif elim_tier != repl_tier:
        errors.append(
            f"Replacement must be same tier as eliminated; "
            f"{eliminated_team!r} is Tier {elim_tier}, {replacement_team!r} is Tier {repl_tier}"
        )

    if replacement_team in owned:
        errors.append(f"{replacement_team!r} is already owned by {player}")

    if not match_stats.empty:
        row = match_stats[match_stats["Team"] == replacement_team]
        if not row.empty:
            rr = str(row.iloc[0].get("RoundReached", "") or "").strip()
            if not rr or rr == "GroupStage":
                errors.append(f"{replacement_team!r} did not survive the group stage")

    return errors


def _effective_owned(
    player: str,
    assignments: dict[str, list[str]],
    purchases: pd.DataFrame,
) -> set[str]:
    scoring_purch = purchases_to_scoring_format(purchases)
    eff = get_effective_teams(player, assignments, scoring_purch)
    return set(eff["group_stage"]) | set(eff["knockout"])

# ---------------------------------------------------------------------------
# Random draws
# ---------------------------------------------------------------------------

def assign_ninth_team(
    player: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    seed: Optional[int] = None,
) -> Optional[str]:
    """Pick a random surviving, unowned team for the ninth team slot."""
    owned = _effective_owned(player, assignments, purchases)
    candidates = sorted([
        str(r["Team"]) for _, r in match_stats.iterrows()
        if str(r.get("RoundReached", "") or "").strip() not in ("", "GroupStage")
        and str(r["Team"]) not in owned
    ])
    return random.Random(seed).choice(candidates) if candidates else None


def assign_resurrection_team(
    player: str,
    eliminated_team: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    tier_map: dict[str, int],
    purchases: pd.DataFrame,
    seed: Optional[int] = None,
) -> Optional[str]:
    """Pick a random surviving same-tier unowned team for resurrection."""
    owned = _effective_owned(player, assignments, purchases)
    target_tier = tier_map.get(eliminated_team)
    if target_tier is None:
        return None
    candidates = sorted([
        str(r["Team"]) for _, r in match_stats.iterrows()
        if tier_map.get(str(r["Team"])) == target_tier
        and str(r.get("RoundReached", "") or "").strip() not in ("", "GroupStage")
        and str(r["Team"]) not in owned
    ])
    return random.Random(seed).choice(candidates) if candidates else None

# ---------------------------------------------------------------------------
# Mulligan
# ---------------------------------------------------------------------------

def execute_mulligan(
    player: str,
    allocation: Allocation,
    participants: list[str],
    purchases: pd.DataFrame,
    seed: Optional[int] = None,
    max_attempts: int = 500,
) -> tuple[Allocation, list[str]]:
    """Full redraw of a player's 8 teams using the allocation engine.

    Validates that the player has a PROCESSED MULLIGAN purchase.
    Returns (new_allocation, errors).  On failure errors is non-empty and
    allocation is unchanged.
    """
    errors: list[str] = []

    p = purchases[purchases["Player"] == player] if not purchases.empty else pd.DataFrame()
    if p.empty or p[p["PurchaseType"] == "Mulligan"].empty:
        errors.append(f"{player} has no Mulligan purchase")
        return allocation, errors

    rng_state = random.getstate()
    if seed is not None:
        random.seed(seed)

    try:
        new_alloc = repick_participant(allocation, player, max_attempts=max_attempts)
    finally:
        if seed is not None:
            random.setstate(rng_state)

    violations = validate_allocations(new_alloc, participants, check_min_appearances=False)
    if violations:
        errors.extend(violations)
        return allocation, errors

    return new_alloc, []

# ---------------------------------------------------------------------------
# Tiebreakers
# ---------------------------------------------------------------------------

def calculate_tiebreak_stats(
    teams: list[str],
    match_stats: pd.DataFrame,
) -> dict:
    """Goals scored and QF-reach count for a team list (tiebreak criteria 1 & 2)."""
    goals = 0
    qf_count = 0
    for team in set(teams):
        row = match_stats[match_stats["Team"] == team]
        if row.empty:
            continue
        r = row.iloc[0]
        goals += _safe_int(r.get("GroupGoals", 0)) + _safe_int(r.get("KnockoutGoals", 0))
        if str(r.get("RoundReached", "") or "").strip() in QF_ROUNDS:
            qf_count += 1
    return {"tiebreak_goals": goals, "tiebreak_qf": qf_count}

# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------

def prize_leaderboard(
    participants: list[str],
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    statuses: pd.DataFrame,
    tournament_results: Optional[dict] = None,
    tiebreak_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Prize Leaderboard — PAID players only, eligible for prizes."""
    paid = set(get_paid_players(statuses))
    paid_participants = [p for p in participants if p in paid]
    return _build_leaderboard(
        paid_participants, assignments, match_stats, purchases,
        captains, predictions, tournament_results, tiebreak_seed, statuses,
    )


def overall_leaderboard(
    participants: list[str],
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    statuses: pd.DataFrame,
    tournament_results: Optional[dict] = None,
    tiebreak_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Overall Leaderboard — all participants, paid and unpaid."""
    return _build_leaderboard(
        participants, assignments, match_stats, purchases,
        captains, predictions, tournament_results, tiebreak_seed, statuses,
    )


def _build_leaderboard(
    participants: list[str],
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    tournament_results: Optional[dict],
    tiebreak_seed: Optional[int],
    statuses: pd.DataFrame,
) -> pd.DataFrame:
    scoring_purch = purchases_to_scoring_format(purchases)

    lb = _score_leaderboard(
        participants, assignments, match_stats, scoring_purch,
        captains, predictions, tournament_results,
    )
    if lb.empty or "TotalPoints" not in lb.columns:
        return pd.DataFrame(columns=[
            "Rank", "Player", "BasePoints", "CaptainBonus",
            "InsuranceBonus", "PredictionBonus", "TotalPoints",
            "tiebreak_goals", "tiebreak_qf", "PaymentStatus",
        ])

    # Tiebreak stats per player
    teams_df = _load_teams()
    strength_map = dict(zip(teams_df["Team"], teams_df["StrengthScore"].astype(float)))

    tb_rows = []
    for player in participants:
        eff = get_effective_teams(player, assignments, scoring_purch)
        all_teams = list(set(eff["group_stage"]) | set(eff["knockout"]))
        stats = calculate_tiebreak_stats(all_teams, match_stats)
        # Tiebreaker 3: lowest original portfolio strength (original 8 teams only)
        orig_teams = assignments.get(player, [])
        portfolio_strength = sum(strength_map.get(t, 0.0) for t in orig_teams)
        tb_rows.append({"Player": player, **stats, "tiebreak_portfolio_strength": portfolio_strength})

    lb = lb.merge(pd.DataFrame(tb_rows), on="Player", how="left")

    # Sort: 1) points desc, 2) goals desc, 3) QF teams desc, 4) portfolio strength asc, 5) coin toss
    rng = random.Random(tiebreak_seed)
    lb["_coin"] = [rng.random() for _ in range(len(lb))]
    lb = lb.sort_values(
        ["TotalPoints", "tiebreak_goals", "tiebreak_qf", "tiebreak_portfolio_strength", "_coin"],
        ascending=[False, False, False, True, False],
    ).reset_index(drop=True)
    lb["Rank"] = range(1, len(lb) + 1)
    lb = lb.drop(columns=["_coin"], errors="ignore")

    status_map = dict(zip(statuses["Player"], statuses["Status"])) if not statuses.empty else {}
    lb["PaymentStatus"] = lb["Player"].map(status_map).fillna("UNPAID")

    return lb

# ---------------------------------------------------------------------------
# Team Ownership
# ---------------------------------------------------------------------------

def get_team_ownership(
    assignments: dict[str, list[str]],
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    purchases: pd.DataFrame,
) -> dict[str, dict]:
    """Return ownership data keyed by team name.

    Each entry: {owners, pre_captains, knockout_captains, dark_horse_pickers}
    """
    result: dict[str, dict] = {}

    def _entry(team: str) -> dict:
        if team not in result:
            result[team] = {
                "owners": [],
                "pre_captains": [],
                "knockout_captains": [],
                "dark_horse_pickers": [],
            }
        return result[team]

    # Base + effective ownership (ninth team / resurrection)
    for player, teams in assignments.items():
        scoring_purch = purchases_to_scoring_format(purchases)
        eff = get_effective_teams(player, assignments, scoring_purch)
        for team in set(eff["group_stage"]) | set(eff["knockout"]):
            _entry(team)["owners"].append(player)

    # Pre-tournament captains
    if not captains.empty:
        for _, row in captains[captains["CaptainType"] == "PreTournament"].iterrows():
            _entry(str(row["Team"]))["pre_captains"].append(str(row["Player"]))

    # Knockout captains
    if not captains.empty:
        for _, row in captains[captains["CaptainType"] == "Knockout"].iterrows():
            _entry(str(row["Team"]))["knockout_captains"].append(str(row["Player"]))

    # Dark horse pickers
    if not predictions.empty and "DarkHorse" in predictions.columns:
        for _, row in predictions.iterrows():
            dh = str(row.get("DarkHorse", "") or "").strip()
            if dh:
                _entry(dh)["dark_horse_pickers"].append(str(row["Player"]))

    return result

# ---------------------------------------------------------------------------
# Predictions Centre
# ---------------------------------------------------------------------------

def get_predictions_centre(predictions: pd.DataFrame) -> dict:
    """Aggregate all predictions for the Predictions Centre.

    Returns {world_cup_winner, golden_boot, dark_horse} each mapping
    pick → list[player].
    """
    centre: dict[str, dict] = {
        "world_cup_winner": {},
        "golden_boot": {},
        "dark_horse": {},
    }
    if predictions.empty:
        return centre

    field_map = {
        "WorldCupWinner": "world_cup_winner",
        "GoldenBoot":     "golden_boot",
        "DarkHorse":      "dark_horse",
    }
    for _, row in predictions.iterrows():
        player = str(row.get("Player", "") or "").strip()
        for col, key in field_map.items():
            val = str(row.get(col, "") or "").strip()
            if val:
                centre[key].setdefault(val, []).append(player)

    return centre

# ---------------------------------------------------------------------------
# The VAR Room exports
# ---------------------------------------------------------------------------

def export_event_history(
    events: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    out = Path(path) if path else EXPORTS_DIR / "event_history.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(out, index=False)
    return events


def export_transaction_history(
    purchases: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    out = Path(path) if path else EXPORTS_DIR / "transaction_history.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    purchases.to_csv(out, index=False)
    return purchases


def export_audit_log(
    audit_log: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    out = Path(path) if path else EXPORTS_DIR / "audit_log.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    audit_log.to_csv(out, index=False)
    return audit_log


def export_payment_ledger(
    purchases: pd.DataFrame,
    statuses: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Payment ledger — one row per player with per-type amounts and total."""
    out = Path(path) if path else EXPORTS_DIR / "payment_ledger.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    players: set[str] = set()
    if not statuses.empty:
        players |= set(statuses["Player"].unique())
    if not purchases.empty:
        players |= set(purchases["Player"].unique())

    status_map = dict(zip(statuses["Player"], statuses["Status"])) if not statuses.empty else {}

    rows = []
    for player in sorted(players):
        p = purchases[purchases["Player"] == player] if not purchases.empty else pd.DataFrame()
        row: dict = {"Player": player}
        total = 0.0
        for ptype, price in PRICES.items():
            count = int((p["PurchaseType"] == ptype).sum()) if not p.empty else 0
            row[ptype] = count
            total += count * price
        row["TotalPaid"] = total
        row["PaymentStatus"] = status_map.get(player, "UNPAID")
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    return df


def export_player_summary(
    participants: list[str],
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    statuses: pd.DataFrame,
    tournament_results: Optional[dict] = None,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Player summary for The VAR Room with payment status included."""
    from src.scoring_engine import generate_player_summary

    out = Path(path) if path else EXPORTS_DIR / "player_summary.csv"
    scoring_purch = purchases_to_scoring_format(purchases)

    df = generate_player_summary(
        participants, assignments, match_stats, scoring_purch,
        captains, predictions, tournament_results, output_path=out,
    )

    if not statuses.empty:
        status_map = dict(zip(statuses["Player"], statuses["Status"]))
        df.insert(1, "PaymentStatus", df["Player"].map(status_map).fillna("UNPAID"))
        df.to_csv(out, index=False)

    return df
