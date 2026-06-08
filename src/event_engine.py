"""Event engine — admin operations for World Cup 2026 Sweepstake."""

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

import pandas as pd

from src.allocation_engine import (
    Allocation, generate_allocations, repick_participant,
    validate_allocations, calculate_portfolio_strength,
)
from src.competition import (
    load_player_status, load_purchases as _load_purchases,
    load_events, load_audit_log,
    purchases_to_scoring_format, calculate_prize_pool,
    log_action, create_event, update_event_status,
    mark_paid, get_paid_players, get_player_status, PRICES,
    prize_leaderboard, overall_leaderboard,
)
from src.scoring_engine import load_match_stats, calculate_team_points, get_effective_teams
from src.team_database import load_teams

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
DATA_DIR    = _ROOT / "data"
EXPORTS_DIR = _ROOT / "exports"

ALLOCATION_PATH           = DATA_DIR / "allocation.csv"
PAYMENT_LEDGER_PATH       = DATA_DIR / "payment_ledger.csv"
MULLIGAN_RESULTS_PATH     = EXPORTS_DIR / "mulligan_results.csv"
NINTH_RESULTS_PATH        = EXPORTS_DIR / "ninth_team_results.csv"
RESURRECTION_RESULTS_PATH = EXPORTS_DIR / "resurrection_results.csv"
RANDOM_SEEDS_PATH         = EXPORTS_DIR / "random_seeds.csv"
TEAM_OWNERSHIP_PATH       = EXPORTS_DIR / "team_ownership.csv"

PURCHASES_PATH = DATA_DIR / "purchases.csv"
EVENTS_PATH    = DATA_DIR / "events.csv"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.csv"
STATUS_PATH    = DATA_DIR / "players.csv"

# Purchase types processed immediately (no draw required)
_IMMEDIATE_TYPES = frozenset({"BuyIn", "PredictionPack", "Insurance"})
# Purchase types held until a draw event
_DRAW_TYPES = frozenset({"Mulligan", "NinthTeam", "Resurrection"})

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


def _group_map() -> dict[str, str]:
    df = load_teams()
    return dict(zip(df["Team"], df["Group"]))


def _tier_map() -> dict[str, int]:
    df = load_teams()
    return dict(zip(df["Team"], df["Tier"].astype(int)))

# ---------------------------------------------------------------------------
# Allocation persistence
# ---------------------------------------------------------------------------

def load_allocation(path: Optional[Path | str] = None) -> Allocation:
    """Load current allocation from CSV.  Returns empty Allocation if absent."""
    p = Path(path) if path else ALLOCATION_PATH
    if not p.exists():
        return Allocation(assignments={}, portfolio_scores={})
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
    except Exception:
        return Allocation(assignments={}, portfolio_scores={})
    assignments: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        player = row["Player"].strip()
        team   = row["Team"].strip()
        if player and team:
            assignments.setdefault(player, []).append(team)
    scores = {p: calculate_portfolio_strength(t) for p, t in assignments.items()}
    return Allocation(assignments=assignments, portfolio_scores=scores)


def save_allocation(allocation: Allocation, path: Optional[Path | str] = None) -> None:
    out = Path(path) if path else ALLOCATION_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"Player": player, "Team": team}
        for player, teams in allocation.assignments.items()
        for team in teams
    ]
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Player", "Team"])
    df.to_csv(out, index=False)

# ---------------------------------------------------------------------------
# Group-aware candidate helpers
# ---------------------------------------------------------------------------

def _owned_groups(player: str, assignments: dict, purchases: pd.DataFrame) -> set[str]:
    gmap = _group_map()
    sp = purchases_to_scoring_format(purchases)
    eff = get_effective_teams(player, assignments, sp)
    all_teams = set(eff["group_stage"]) | set(eff["knockout"])
    return {gmap[t] for t in all_teams if gmap.get(t)}


def ninth_team_candidates(
    player: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
) -> list[str]:
    """Surviving, unowned teams not from a group the player already holds."""
    gmap = _group_map()
    sp = purchases_to_scoring_format(purchases)
    eff = get_effective_teams(player, assignments, sp)
    owned = set(eff["group_stage"]) | set(eff["knockout"])
    bad_groups = _owned_groups(player, assignments, purchases)
    return sorted([
        str(r["Team"]) for _, r in match_stats.iterrows()
        if str(r.get("RoundReached", "") or "").strip() not in ("", "GroupStage")
        and str(r["Team"]) not in owned
        and gmap.get(str(r["Team"]), "") not in bad_groups
        and gmap.get(str(r["Team"]), "")
    ])


def resurrection_candidates(
    player: str,
    eliminated_team: str,
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    tier_map: dict[str, int],
) -> list[str]:
    """Surviving same-tier unowned teams whose group doesn't conflict."""
    gmap = _group_map()
    sp = purchases_to_scoring_format(purchases)
    eff = get_effective_teams(player, assignments, sp)
    owned_all = set(eff["group_stage"]) | set(eff["knockout"])
    # Group constraint: eliminated team's slot is freed, so exclude its group from bad_groups
    owned_for_groups = owned_all - {eliminated_team}
    bad_groups = {gmap[t] for t in owned_for_groups if gmap.get(t)}
    target_tier = tier_map.get(eliminated_team)
    return sorted([
        str(r["Team"]) for _, r in match_stats.iterrows()
        if str(r.get("RoundReached", "") or "").strip() not in ("", "GroupStage")
        and str(r["Team"]) != eliminated_team
        and str(r["Team"]) not in owned_all
        and tier_map.get(str(r["Team"])) == target_tier
        and gmap.get(str(r["Team"]), "") not in bad_groups
        and gmap.get(str(r["Team"]), "")
    ])

# ---------------------------------------------------------------------------
# Batch purchase processing
# ---------------------------------------------------------------------------

def process_pending_purchases(
    purchases: pd.DataFrame,
    statuses: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Mark players with a BuyIn purchase as PAID.

    Returns (purchases, updated_statuses, messages).
    """
    msgs: list[str] = []
    upurch = purchases.copy() if not purchases.empty else purchases
    ust = statuses.copy() if not statuses.empty else statuses

    if upurch.empty:
        return upurch, ust, []

    buyins = upurch[upurch["PurchaseType"] == "BuyIn"]
    for _, row in buyins.iterrows():
        player = str(row["Player"])
        if get_player_status(player, ust) != "PAID":
            ust = mark_paid(player, ust)
            msgs.append(f"{player}: marked PAID")

    return upurch, ust, msgs

# ---------------------------------------------------------------------------
# Mulligan draw
# ---------------------------------------------------------------------------

def run_mulligan_draw(
    allocation: Allocation,
    participants: list[str],
    purchases: pd.DataFrame,
    events: pd.DataFrame,
    audit_log: pd.DataFrame,
    seed: Optional[int] = None,
) -> dict:
    """Redraw all players with a PENDING MULLIGAN purchase.

    Returns updated state plus per-player results and broadcast text.
    """
    if seed is None:
        seed = random.randint(0, 2**31)
    rng = random.Random(seed)

    # Find players with unprocessed Mulligans: purchases > audit log executions
    mulligan_players: list[str] = []
    if not purchases.empty:
        mul_counts = purchases[purchases["PurchaseType"] == "Mulligan"].groupby("Player").size()
        done_counts: dict[str, int] = {}
        if not audit_log.empty and "Action" in audit_log.columns:
            done_series = audit_log[audit_log["Action"] == "MULLIGAN_EXECUTED"].groupby("Player").size()
            done_counts = done_series.to_dict()
        for player, count in mul_counts.items():
            for _ in range(count - done_counts.get(player, 0)):
                mulligan_players.append(player)

    updated_alloc = allocation
    upurch = purchases.copy()
    ulog   = audit_log.copy()
    results: dict[str, dict] = {}
    errors:  dict[str, str]  = {}

    for player in mulligan_players:
        player_seed = rng.randint(0, 2**31)
        prev = list(allocation.assignments.get(player, []))

        random.seed(player_seed)
        try:
            new_alloc = repick_participant(updated_alloc, player, max_attempts=500)
        finally:
            random.seed(None)

        violations = validate_allocations(new_alloc, participants, check_min_appearances=False)
        if violations:
            errors[player] = "; ".join(violations)
            ulog = log_action("MULLIGAN_DRAW", player, "MULLIGAN_FAILED", errors[player], ulog)
            continue

        updated_alloc = new_alloc
        new_teams = list(new_alloc.assignments.get(player, []))
        results[player] = {"previous": prev, "new": new_teams, "seed": player_seed}

        ulog = log_action("MULLIGAN_DRAW", player, "MULLIGAN_EXECUTED", str(player_seed), ulog)

    # Add event record
    uevents = create_event("MULLIGAN_DRAW", _now_iso(), events)
    event_id = uevents.iloc[-1]["EventID"]
    uevents = update_event_status(event_id, "EXECUTED", uevents, seed)

    return {
        "updated_allocation": updated_alloc,
        "updated_purchases":  upurch,
        "updated_events":     uevents,
        "updated_audit_log":  ulog,
        "results":  results,
        "errors":   errors,
        "seed":     seed,
        "broadcast": generate_draw_broadcast("Mulligan Draw", {p: " | ".join(r["new"]) for p, r in results.items()}),
    }

# ---------------------------------------------------------------------------
# Ninth team draw
# ---------------------------------------------------------------------------

def run_ninth_team_draw(
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    events: pd.DataFrame,
    audit_log: pd.DataFrame,
    seed: Optional[int] = None,
) -> dict:
    """Assign a surviving team to every player with a PENDING NINTH purchase."""
    if seed is None:
        seed = random.randint(0, 2**31)
    rng = random.Random(seed)

    pending = (
        purchases[(purchases["PurchaseType"] == "NinthTeam") & (purchases["Selection"].str.strip() == "")]
        if not purchases.empty else pd.DataFrame()
    )
    players = pending["Player"].unique().tolist() if not pending.empty else []

    upurch = purchases.copy()
    ulog   = audit_log.copy()
    results: dict[str, str] = {}
    errors:  dict[str, str] = {}

    for player in players:
        player_seed = rng.randint(0, 2**31)
        candidates = ninth_team_candidates(player, assignments, match_stats, purchases)

        if not candidates:
            errors[player] = "No valid ninth team candidates (group uniqueness)"
            ulog = log_action("NINTH_TEAM_DRAW", player, "NINTH_FAILED", errors[player], ulog)
            continue

        team = random.Random(player_seed).choice(candidates)
        results[player] = team

        mask = (
            (upurch["Player"] == player)
            & (upurch["PurchaseType"] == "NinthTeam")
            & (upurch["Selection"].str.strip() == "")
        )
        if mask.any():
            upurch.loc[upurch[mask].index[0], "Selection"] = team

        ulog = log_action("NINTH_TEAM_DRAW", player, "NINTH_ASSIGNED", team, ulog)

    uevents = create_event("NINTH_TEAM_DRAW", _now_iso(), events)
    event_id = uevents.iloc[-1]["EventID"]
    uevents = update_event_status(event_id, "EXECUTED", uevents, seed)

    return {
        "updated_purchases":  upurch,
        "updated_events":     uevents,
        "updated_audit_log":  ulog,
        "results":  results,
        "errors":   errors,
        "seed":     seed,
        "broadcast": generate_draw_broadcast("Ninth Team Draw", results),
    }

# ---------------------------------------------------------------------------
# Resurrection draw
# ---------------------------------------------------------------------------

def run_resurrection_draw(
    assignments: dict[str, list[str]],
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    events: pd.DataFrame,
    audit_log: pd.DataFrame,
    seed: Optional[int] = None,
) -> dict:
    """Assign replacements for all PENDING RESURRECTION purchases.

    Resurrection Selection field must contain the eliminated team name
    before this draw runs.

    Only valid after GROUP_STAGE_CLOSE has been executed and before
    knockout matches begin.  Replacement teams earn knockout points only
    (group stage stats are never attributed to resurrection replacements).
    """
    # Require GROUP_STAGE_CLOSE before resurrection draws can run.
    executed = events[events["Status"] == "EXECUTED"]["EventType"].tolist() if not events.empty else []
    if "GROUP_STAGE_CLOSE" not in executed:
        return {
                "updated_purchases": purchases,
                "updated_events":    events,
                "updated_audit_log": audit_log,
                "results": {},
                "errors":  {"ALL": "Group stage must be closed before resurrection draws can run. "
                                   "Run GROUP_STAGE_CLOSE first."},
                "seed": seed,
                "broadcast": "",
            }

    if seed is None:
        seed = random.randint(0, 2**31)
    rng = random.Random(seed)
    tmap = _tier_map()

    pending = (
        purchases[
            (purchases["PurchaseType"] == "Resurrection")
            & (~purchases["Selection"].str.contains("->", na=False))
        ]
        if not purchases.empty else pd.DataFrame()
    )

    upurch = purchases.copy()
    ulog   = audit_log.copy()
    results: dict[str, dict] = {}
    errors:  dict[str, str]  = {}

    for _, row in pending.iterrows():
        player = str(row["Player"])
        eliminated = str(row.get("Selection", "") or "").strip()

        if not eliminated:
            errors[player] = "No eliminated team specified in Selection field"
            continue

        player_seed = rng.randint(0, 2**31)
        candidates = resurrection_candidates(player, eliminated, assignments, match_stats, purchases, tmap)

        if not candidates:
            errors[player] = f"No valid resurrection candidates for {eliminated!r}"
            ulog = log_action("RESURRECTION_DRAW", player, "RESURRECTION_FAILED", errors[player], ulog)
            continue

        replacement = random.Random(player_seed).choice(candidates)
        results[player] = {"eliminated": eliminated, "replacement": replacement, "seed": player_seed}
        final_selection = f"{eliminated}->{replacement}"

        mask = (
            (upurch["Player"] == player)
            & (upurch["PurchaseType"] == "Resurrection")
            & (upurch["Selection"].str.strip() == eliminated)
        )
        if mask.any():
            upurch.loc[upurch[mask].index[0], "Selection"] = final_selection

        ulog = log_action("RESURRECTION_DRAW", player, "RESURRECTION_ASSIGNED", final_selection, ulog)

    uevents = create_event("RESURRECTION_DRAW", _now_iso(), events)
    event_id = uevents.iloc[-1]["EventID"]
    uevents = update_event_status(event_id, "EXECUTED", uevents, seed)

    broadcast_items = {p: f"{r['eliminated']} → {r['replacement']}" for p, r in results.items()}
    return {
        "updated_purchases":  upurch,
        "updated_events":     uevents,
        "updated_audit_log":  ulog,
        "results":  results,
        "errors":   errors,
        "seed":     seed,
        "broadcast": generate_draw_broadcast("Resurrection Draw", broadcast_items),
    }

# ---------------------------------------------------------------------------
# Group stage close
# ---------------------------------------------------------------------------

def run_group_stage_close(
    match_stats: pd.DataFrame,
    events: pd.DataFrame,
    audit_log: pd.DataFrame,
    timestamp: Optional[str] = None,
) -> dict:
    """Process group stage completion.

    Identifies group winners, surviving and eliminated teams, then schedules
    the NINTH_TEAM_DRAW and RESURRECTION_DRAW events.

    Returns summary dict with winner/survivor/eliminated lists.
    """
    ts = timestamp or _now_iso()

    group_winners = []
    surviving = []
    eliminated = []

    if not match_stats.empty:
        for _, row in match_stats.iterrows():
            team = str(row["Team"])
            rr   = str(row.get("RoundReached", "") or "").strip()
            gw   = _safe_int(row.get("GroupWinner", 0))

            if rr == "GroupStage" or not rr:
                eliminated.append(team)
            else:
                surviving.append(team)
                if gw:
                    group_winners.append(team)

    ulog    = audit_log.copy()
    uevents = events.copy()

    ulog = log_action("GROUP_STAGE_CLOSE", "", "GROUP_STAGE_CLOSED", f"{len(surviving)} surviving / {len(eliminated)} eliminated", ulog, ts)

    uevents = create_event("NINTH_TEAM_DRAW", ts, uevents)
    uevents = create_event("RESURRECTION_DRAW", ts, uevents)

    return {
        "updated_events":    uevents,
        "updated_audit_log": ulog,
        "group_winners":     group_winners,
        "surviving_teams":   surviving,
        "eliminated_teams":  eliminated,
        "summary": (
            f"Group stage closed.  "
            f"Surviving: {len(surviving)}  |  "
            f"Eliminated: {len(eliminated)}  |  "
            f"Group winners: {len(group_winners)}\n"
            f"NINTH_TEAM_DRAW and RESURRECTION_DRAW windows are now open."
        ),
    }

# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

def lock_predictions(
    events: pd.DataFrame,
    audit_log: pd.DataFrame,
    timestamp: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Record prediction lock event.  Returns (updated_events, updated_audit_log)."""
    ts = timestamp or _now_iso()
    uevents = create_event("PREDICTION_LOCK", ts, events)
    eid = uevents.iloc[-1]["EventID"]
    uevents = update_event_status(eid, "EXECUTED", uevents, executed_time=ts)
    ulog = log_action("PREDICTION_LOCK", "", "PREDICTIONS_LOCKED", ts, audit_log, ts)
    return uevents, ulog


def lock_buyins(
    statuses: pd.DataFrame,
    events: pd.DataFrame,
    audit_log: pd.DataFrame,
    timestamp: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Record buy-in lock event (1 hr before R16).  Returns (statuses, events, log)."""
    ts = timestamp or _now_iso()
    uevents = create_event("BUYIN_LOCK", ts, events)
    eid = uevents.iloc[-1]["EventID"]
    uevents = update_event_status(eid, "EXECUTED", uevents, executed_time=ts)
    ulog = log_action("BUYIN_LOCK", "", "BUYINS_LOCKED", ts, audit_log, ts)
    return statuses, uevents, ulog

# ---------------------------------------------------------------------------
# Results provider (pluggable)
# ---------------------------------------------------------------------------

class ResultsProvider(Protocol):
    """Interface for pluggable match-results sources."""
    def update(self, team: str, stats: dict) -> pd.DataFrame: ...
    def get_stats(self) -> pd.DataFrame: ...


def update_results(
    team: str,
    stats: dict,
    match_stats: pd.DataFrame,
) -> pd.DataFrame:
    """Return updated match_stats with new values for one team.

    Accepted stat keys: GroupGoals, GroupCleanSheets, GroupPenaltyWins,
    GroupComebackWins, GroupWinner, KnockoutGoals, KnockoutCleanSheets,
    KnockoutPenaltyWins, KnockoutComebackWins, RoundReached.
    """
    df = match_stats.copy()
    mask = df["Team"] == team
    if not mask.any():
        new_row = {"Team": team, **stats}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        for key, val in stats.items():
            if key in df.columns:
                df.loc[mask, key] = val
    return df


class ManualResultsProvider:
    """Results provider for admin manual entry."""

    def __init__(self, match_stats: pd.DataFrame):
        self._stats = match_stats.copy()

    def update(self, team: str, stats: dict) -> "ManualResultsProvider":
        return ManualResultsProvider(update_results(team, stats, self._stats))

    def get_stats(self) -> pd.DataFrame:
        return self._stats.copy()

# ---------------------------------------------------------------------------
# Text generators
# ---------------------------------------------------------------------------

def generate_whatsapp_update(
    prize_lb: pd.DataFrame,
    overall_lb: pd.DataFrame,
    prize_pool: dict,
    events: pd.DataFrame,
    match_stats: pd.DataFrame,
    prev_overall_lb: Optional[pd.DataFrame] = None,
) -> str:
    """Format a WhatsApp-ready competition update."""
    lines: list[str] = [
        "🏆 World Cup 2026 Sweepstake Update",
        "",
        f"💰 Prize Pool: €{prize_pool.get('current_pot', 0):.2f}  |  "
        f"1st: €{prize_pool.get('first_prize', 0):.2f}  |  "
        f"2nd: €{prize_pool.get('second_prize', 0):.2f}  |  "
        f"3rd: €{prize_pool.get('third_prize', 0):.2f}",
        "",
    ]

    if not prize_lb.empty:
        lines.append("📊 PRIZE LEADERBOARD (Paid Players)")
        for _, row in prize_lb.iterrows():
            lines.append(f"  {int(row['Rank'])}. {row['Player']:<15} {row['TotalPoints']:.0f} pts")
        lines.append("")

    if not overall_lb.empty:
        lines.append("🌍 OVERALL LEADERBOARD")
        for _, row in overall_lb.iterrows():
            status = f"[{row.get('PaymentStatus', 'UNPAID')}]"
            lines.append(f"  {int(row['Rank'])}. {row['Player']:<15} {row['TotalPoints']:.0f} pts  {status}")
        lines.append("")

    # Biggest movers
    if prev_overall_lb is not None and not overall_lb.empty and not prev_overall_lb.empty:
        movers = _calculate_movers(overall_lb, prev_overall_lb)
        if movers:
            lines.append("⬆️ Biggest Movers")
            for name, delta in movers[:3]:
                sign = "+" if delta > 0 else ""
                lines.append(f"  {name}  {sign}{delta} places")
            lines.append("")

    # Top individual team
    if not match_stats.empty:
        df_teams = load_teams()
        tmap = dict(zip(df_teams["Team"], df_teams["Tier"].astype(int)))
        best_team = None
        best_pts  = -1.0
        for _, row in match_stats.iterrows():
            tier = tmap.get(str(row["Team"]), 1)
            pts  = calculate_team_points(str(row["Team"]), match_stats, tier)["total"]
            if pts > best_pts:
                best_pts = pts
                best_team = str(row["Team"])
        if best_team and best_pts > 0:
            lines.append(f"⚽ Top Team: {best_team} — {best_pts:.0f} pts")
            lines.append("")

    # Next scheduled event
    if not events.empty:
        nxt = events[events["Status"].isin(["SCHEDULED", "OPEN"])]
        if not nxt.empty:
            row = nxt.iloc[0]
            lines.append(f"📅 Next Event: {row['EventType']}  ({row['ScheduledTime']})")
        lines.append("")

    return "\n".join(lines)


def _calculate_movers(
    current: pd.DataFrame,
    previous: pd.DataFrame,
) -> list[tuple[str, int]]:
    prev_map = dict(zip(previous["Player"], previous["Rank"].astype(int)))
    movers: list[tuple[str, int]] = []
    for _, row in current.iterrows():
        prev_rank = prev_map.get(row["Player"])
        if prev_rank is not None:
            delta = prev_rank - int(row["Rank"])  # positive = moved up
            if delta != 0:
                movers.append((row["Player"], delta))
    movers.sort(key=lambda x: abs(x[1]), reverse=True)
    return movers


def generate_draw_broadcast(draw_type: str, results: dict[str, str]) -> str:
    """Format a draw result announcement for WhatsApp.

    results: {player_name: result_string}
    """
    lines = [f"🎲 {draw_type} Results", ""]
    if not results:
        lines.append("No draws to report.")
    else:
        for player, result in results.items():
            lines.append(f"  {player} → {result}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# VAR Room exports
# ---------------------------------------------------------------------------

def generate_team_ownership_csv(
    assignments: dict[str, list[str]],
    captains: pd.DataFrame,
    predictions: pd.DataFrame,
    purchases: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Write team_ownership.csv — one row per team with ownership details."""
    out = Path(path) if path else TEAM_OWNERSHIP_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    from src.competition import get_team_ownership
    ownership = get_team_ownership(assignments, captains, predictions, purchases)

    rows = []
    for team, data in sorted(ownership.items()):
        rows.append({
            "Team":            team,
            "Owners":          "; ".join(sorted(data["owners"])),
            "PreCaptains":     "; ".join(sorted(data["pre_captains"])),
            "KnockoutCaptains": "; ".join(sorted(data["knockout_captains"])),
            "DarkHorsePickers": "; ".join(sorted(data["dark_horse_pickers"])),
        })

    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    return df


def export_random_seeds(
    events: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Export EventID, EventType, RandomSeed for all events that stored a seed."""
    out = Path(path) if path else RANDOM_SEEDS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    if events.empty:
        df = pd.DataFrame(columns=["EventID", "EventType", "RandomSeed"])
    else:
        df = events[events["RandomSeed"].fillna("") != ""][
            ["EventID", "EventType", "RandomSeed"]
        ].copy()
    df.to_csv(out, index=False)
    return df


def generate_payment_ledger(
    purchases: pd.DataFrame,
    path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Write data/payment_ledger.csv — one row per purchase transaction."""
    out = Path(path) if path else PAYMENT_LEDGER_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    if purchases.empty:
        df = pd.DataFrame(columns=["Player", "Purchase", "Amount", "Reference", "Timestamp"])
    else:
        rows = []
        for _, row in purchases.iterrows():
            ptype = str(row.get("PurchaseType", "") or "")
            rows.append({
                "Player":    row.get("Player", ""),
                "Purchase":  ptype,
                "Amount":    PRICES.get(ptype, 0.0),
                "Reference": row.get("Reference", ""),
                "Timestamp": row.get("Timestamp", ""),
            })
        df = pd.DataFrame(rows)

    df.to_csv(out, index=False)
    return df

# ---------------------------------------------------------------------------
# Top-level run_event dispatcher (handles all file I/O)
# ---------------------------------------------------------------------------

def run_event(event_type: str, seed: Optional[int] = None) -> dict:
    """Execute a competition event end-to-end.

    Loads all state from data/, executes the event, writes updated state.
    Returns a summary dict.
    """
    if seed is None:
        seed = random.randint(0, 2**31)

    purchases  = _load_purchases()
    statuses   = load_player_status()
    events     = load_events()
    audit_log  = load_audit_log()
    match_stats = load_match_stats()
    allocation  = load_allocation()
    participants = (
        sorted(statuses["Player"].unique().tolist()) if not statuses.empty else []
    )

    if event_type == "INITIAL_DRAW":
        if not participants:
            return {"error": "No participants in player_status.csv"}
        random.seed(seed)
        alloc = generate_allocations(participants)
        random.seed(None)
        save_allocation(alloc)
        uevents = create_event("INITIAL_DRAW", _now_iso(), events)
        eid = uevents.iloc[-1]["EventID"]
        uevents = update_event_status(eid, "EXECUTED", uevents, seed)
        ulog = log_action("INITIAL_DRAW", "", "DRAW_EXECUTED", str(seed), audit_log)
        uevents.to_csv(EVENTS_PATH, index=False)
        ulog.to_csv(AUDIT_LOG_PATH, index=False)
        return {
            "event_type": event_type, "seed": seed,
            "allocation": alloc.assignments,
            "broadcast": generate_draw_broadcast(
                "Initial Draw",
                {p: " | ".join(t) for p, t in alloc.assignments.items()},
            ),
        }

    elif event_type == "MULLIGAN_DRAW":
        result = run_mulligan_draw(allocation, participants, purchases, events, audit_log, seed)
        if "updated_allocation" in result:
            save_allocation(result["updated_allocation"])
        result["updated_purchases"].to_csv(PURCHASES_PATH, index=False)
        result["updated_events"].to_csv(EVENTS_PATH, index=False)
        result["updated_audit_log"].to_csv(AUDIT_LOG_PATH, index=False)
        _export_mulligan_results(result["results"])
        return result

    elif event_type == "GROUP_STAGE_CLOSE":
        result = run_group_stage_close(match_stats, events, audit_log)
        result["updated_events"].to_csv(EVENTS_PATH, index=False)
        result["updated_audit_log"].to_csv(AUDIT_LOG_PATH, index=False)
        return result

    elif event_type == "NINTH_TEAM_DRAW":
        result = run_ninth_team_draw(allocation.assignments, match_stats, purchases, events, audit_log, seed)
        result["updated_purchases"].to_csv(PURCHASES_PATH, index=False)
        result["updated_events"].to_csv(EVENTS_PATH, index=False)
        result["updated_audit_log"].to_csv(AUDIT_LOG_PATH, index=False)
        _export_ninth_results(result["results"], seed)
        return result

    elif event_type == "RESURRECTION_DRAW":
        result = run_resurrection_draw(allocation.assignments, match_stats, purchases, events, audit_log, seed)
        result["updated_purchases"].to_csv(PURCHASES_PATH, index=False)
        result["updated_events"].to_csv(EVENTS_PATH, index=False)
        result["updated_audit_log"].to_csv(AUDIT_LOG_PATH, index=False)
        _export_resurrection_results(result["results"], seed)
        return result

    elif event_type == "TOURNAMENT_COMPLETE":
        uevents = create_event("TOURNAMENT_COMPLETE", _now_iso(), events)
        eid = uevents.iloc[-1]["EventID"]
        uevents = update_event_status(eid, "EXECUTED", uevents, seed)
        ulog = log_action("TOURNAMENT_COMPLETE", "", "TOURNAMENT_COMPLETE", _now_iso(), audit_log)
        uevents.to_csv(EVENTS_PATH, index=False)
        ulog.to_csv(AUDIT_LOG_PATH, index=False)
        return {"event_type": event_type, "seed": seed}

    else:
        raise ValueError(f"Unknown event type: {event_type!r}")


def _export_mulligan_results(results: dict, path: Optional[Path | str] = None) -> None:
    out = Path(path) if path else MULLIGAN_RESULTS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "Player": p,
            "PreviousTeams": " | ".join(r["previous"]),
            "NewTeams": " | ".join(r["new"]),
            "Seed": r.get("seed", ""),
        }
        for p, r in results.items()
    ]
    pd.DataFrame(rows).to_csv(out, index=False)


def _export_ninth_results(results: dict[str, str], seed: int, path: Optional[Path | str] = None) -> None:
    out = Path(path) if path else NINTH_RESULTS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"Player": p, "AssignedTeam": t, "MasterSeed": seed} for p, t in results.items()]
    pd.DataFrame(rows).to_csv(out, index=False)


def _export_resurrection_results(results: dict, seed: int, path: Optional[Path | str] = None) -> None:
    out = Path(path) if path else RESURRECTION_RESULTS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"Player": p, "EliminatedTeam": r["eliminated"], "ReplacementTeam": r["replacement"], "MasterSeed": seed}
        for p, r in results.items()
    ]
    pd.DataFrame(rows).to_csv(out, index=False)
