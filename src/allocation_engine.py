"""Allocation engine — variable player count, auto teams-per-tier."""

import csv
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from src.team_database import load_teams

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIERS = (1, 2, 3, 4)
TEAMS_PER_TIER_COUNT = 12       # teams in each tier (fixed by FIFA draw structure)
BALANCE_THRESHOLD = 20          # max allowed (max_score - min_score)
MAX_BALANCE_ITERATIONS = 1000
MAX_GENERATION_ATTEMPTS = 500

_DEFAULT_AUDIT_PATH = Path(__file__).parent.parent / "exports" / "allocation_audit.csv"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Allocation:
    """Complete allocation result for all participants."""
    assignments: dict[str, list[str]]   # participant -> [team, ...]
    portfolio_scores: dict[str, float]  # participant -> sum of StrengthScores


# ---------------------------------------------------------------------------
# Module-level lookups — populated once, never mutated
# ---------------------------------------------------------------------------

_group_of: dict[str, str] = {}
_tier_of: dict[str, int] = {}
_strength_of: dict[str, int] = {}
_teams_in_tier: dict[int, list[str]] = {}   # tier -> teams sorted by FIFARank ascending
_all_teams: list[str] = []


def _ensure_lookups() -> None:
    global _group_of, _tier_of, _strength_of, _teams_in_tier, _all_teams
    if _group_of:
        return
    df = load_teams()
    _group_of = dict(zip(df["Team"], df["Group"]))
    _tier_of = {t: int(v) for t, v in zip(df["Team"], df["Tier"])}
    _strength_of = {t: int(v) for t, v in zip(df["Team"], df["StrengthScore"])}
    _all_teams = df["Team"].tolist()
    for tier in TIERS:
        _teams_in_tier[tier] = (
            df[df["Tier"] == tier]
            .sort_values("FIFARank")["Team"]
            .tolist()
        )


# ---------------------------------------------------------------------------
# Variable player count helpers
# ---------------------------------------------------------------------------


def get_teams_per_tier(n_players: int) -> int:
    """Return teams-per-tier per player, computed from the player count.

    Targets ~2 appearances per team across all portfolios:
      teams_per_tier × n_players ≈ TEAMS_PER_TIER_COUNT × 2 = 24

    Examples:
      6  players → 4 per tier (16 teams each)
      8  players → 3 per tier (12 teams each)
      12 players → 2 per tier ( 8 teams each)
      13 players → 2 per tier ( 8 teams each)
      24 players → 1 per tier ( 4 teams each)
    """
    return max(1, round(TEAMS_PER_TIER_COUNT * 2 / n_players))


def _appearance_limits(n_players: int, teams_per_tier: int) -> tuple[int, int]:
    """Return (min_appearances, max_appearances) per team given allocation parameters."""
    total = n_players * teams_per_tier
    min_app = max(0, total // TEAMS_PER_TIER_COUNT)
    max_app = math.ceil(total / TEAMS_PER_TIER_COUNT)
    return min_app, max_app


# ---------------------------------------------------------------------------
# Public API — core engine
# ---------------------------------------------------------------------------


def calculate_portfolio_strength(teams: list[str]) -> float:
    """Return the sum of StrengthScore (101 − FIFARank) for a list of teams."""
    _ensure_lookups()
    return float(sum(_strength_of.get(t, 0) for t in teams))


def generate_allocations(
    participants: list[str],
    teams_per_tier: int | None = None,
    max_attempts: int = MAX_GENERATION_ATTEMPTS,
) -> Allocation:
    """Generate a balanced, fully-constrained allocation for all participants.

    teams_per_tier defaults to get_teams_per_tier(len(participants)).
    Retries random assignment up to max_attempts until every validation rule
    passes and the portfolio spread is within BALANCE_THRESHOLD.
    """
    _ensure_lookups()
    n = len(participants)
    t = teams_per_tier if teams_per_tier is not None else get_teams_per_tier(n)

    for _ in range(max_attempts):
        assignments = _try_generate(participants, t)
        if assignments is None:
            continue
        alloc = _make_alloc(assignments)
        alloc = balance_allocations(alloc)
        if not validate_allocations(alloc, participants, teams_per_tier=t):
            return alloc

    raise RuntimeError(
        f"Could not generate a valid allocation after {max_attempts} attempts."
    )


def balance_allocations(
    alloc: Allocation,
    max_iterations: int = MAX_BALANCE_ITERATIONS,
) -> Allocation:
    """Reduce portfolio spread through iterative same-tier team swaps."""
    _ensure_lookups()
    assignments = {p: list(teams) for p, teams in alloc.assignments.items()}

    for _ in range(max_iterations):
        scores = _scores(assignments)
        max_p = max(scores, key=scores.__getitem__)
        min_p = min(scores, key=scores.__getitem__)

        if scores[max_p] - scores[min_p] <= BALANCE_THRESHOLD:
            break

        swap = _best_swap(assignments, scores, max_p, min_p)
        if swap is None:
            break

        i, j = swap
        assignments[max_p][i], assignments[min_p][j] = (
            assignments[min_p][j],
            assignments[max_p][i],
        )

    return _make_alloc(assignments)


def validate_allocations(
    alloc: Allocation,
    participants: list[str],
    check_min_appearances: bool = True,
    teams_per_tier: int | None = None,
) -> list[str]:
    """Check every allocation rule. Returns error strings; empty list = valid.

    Rules
    -----
    R1  Every participant has exactly teams_per_tier * 4 teams.
    R2  Exactly teams_per_tier teams from each tier per participant.
    R3  No team appears more than max_appearances times across all participants.
    R4  Every team appears at least min_appearances times (skipped when check_min_appearances=False).
    R5  No two teams in a participant's portfolio share a World Cup group.
    R6  No duplicate team within a participant's portfolio.
    R7  No blank team assignments.
    R8  Portfolio spread (max − min) <= BALANCE_THRESHOLD.
    R9  Stored portfolio scores match freshly calculated values.
    """
    _ensure_lookups()
    errors: list[str] = []
    assignments = alloc.assignments
    n = len(participants)
    t = teams_per_tier if teams_per_tier is not None else get_teams_per_tier(n)
    expected_total = t * len(TIERS)
    min_app, max_app = _appearance_limits(n, t)

    # Global usage tally (needed for R3/R4)
    usage: dict[str, int] = {}
    for teams in assignments.values():
        for team in teams:
            usage[team] = usage.get(team, 0) + 1

    for p in participants:
        teams = assignments.get(p, [])

        # R1 — count
        if len(teams) != expected_total:
            errors.append(f"R1 {p}: {len(teams)} teams (expected {expected_total})")

        # R2 — tier distribution
        tier_counts: dict[int, int] = {}
        for team in teams:
            tr = _tier_of.get(team, 0)
            tier_counts[tr] = tier_counts.get(tr, 0) + 1
        for tier in TIERS:
            if tier_counts.get(tier, 0) != t:
                errors.append(
                    f"R2 {p}: Tier {tier} has {tier_counts.get(tier, 0)} teams (expected {t})"
                )

        # R5 — group uniqueness
        groups = [_group_of.get(team, "?") for team in teams]
        if len(groups) != len(set(groups)):
            dupes = sorted({g for g in groups if groups.count(g) > 1})
            errors.append(f"R5 {p}: shared groups {dupes}")

        # R6 — duplicate teams
        if len(teams) != len(set(teams)):
            dupes_t = sorted({team for team in teams if teams.count(team) > 1})
            errors.append(f"R6 {p}: duplicate teams {dupes_t}")

        # R7 — blank assignments
        blanks = [team for team in teams if not team or not str(team).strip()]
        if blanks:
            errors.append(f"R7 {p}: {len(blanks)} blank assignment(s)")

        # R9 — score accuracy
        expected = calculate_portfolio_strength(teams)
        actual = alloc.portfolio_scores.get(p, 0.0)
        if abs(expected - actual) > 0.001:
            errors.append(
                f"R9 {p}: stored score {actual:.1f} != calculated {expected:.1f}"
            )

    # R3 — max appearances
    for team, count in usage.items():
        if count > max_app:
            errors.append(f"R3 {team}: {count} appearances (max {max_app})")

    # R4 — min appearances
    if check_min_appearances and min_app > 0:
        for team in _all_teams:
            if usage.get(team, 0) < min_app:
                errors.append(
                    f"R4 {team}: {usage.get(team, 0)} appearances (min {min_app})"
                )

    # R8 — spread
    if alloc.portfolio_scores:
        spread = (
            max(alloc.portfolio_scores.values())
            - min(alloc.portfolio_scores.values())
        )
        if spread > BALANCE_THRESHOLD:
            errors.append(f"R8 spread {spread:.1f} > {BALANCE_THRESHOLD}")

    return errors


def repick_participant(
    alloc: Allocation,
    participant: str,
    max_attempts: int = MAX_GENERATION_ATTEMPTS,
) -> Allocation:
    """Regenerate teams for one participant without altering any other assignment."""
    _ensure_lookups()
    # Derive teams_per_tier from existing assignments rather than player count so
    # the function works correctly when the allocation has fewer entries than the
    # real game (e.g. in tests with 3-player fixtures built for 8-teams/player).
    sample = next(iter(alloc.assignments.values()), [])
    t = max(1, len(sample) // len(TIERS))

    other_usage: dict[str, int] = {}
    other_scores: dict[str, float] = {}
    for p, teams in alloc.assignments.items():
        if p == participant:
            continue
        other_scores[p] = calculate_portfolio_strength(teams)
        for team in teams:
            other_usage[team] = other_usage.get(team, 0) + 1

    best_result: Allocation | None = None
    best_spread = float("inf")

    for _ in range(max_attempts):
        new_teams = _try_pick_one(other_usage, t)
        if new_teams is None:
            continue

        new_score = calculate_portfolio_strength(new_teams)
        all_scores = {**other_scores, participant: new_score}
        spread = max(all_scores.values()) - min(all_scores.values())

        if spread < best_spread:
            best_spread = spread
            best_result = Allocation(
                assignments={**alloc.assignments, participant: new_teams},
                portfolio_scores=all_scores,
            )

        if spread <= BALANCE_THRESHOLD:
            break

    if best_result is None:
        raise RuntimeError(
            f"Could not generate valid teams for {participant!r}."
        )

    return best_result


# ---------------------------------------------------------------------------
# Public API — audit & simulation
# ---------------------------------------------------------------------------


def audit_allocation_run(
    alloc: Allocation,
    participants: list[str],
) -> dict:
    """Return a structured audit of one allocation."""
    _ensure_lookups()
    errors = validate_allocations(alloc, participants)

    scores = alloc.portfolio_scores
    if scores:
        min_score = min(scores.values())
        max_score = max(scores.values())
        spread = max_score - min_score
    else:
        min_score = max_score = spread = 0.0

    return {
        "passed": not errors,
        "spread": spread,
        "min_score": min_score,
        "max_score": max_score,
        "failure_reasons": errors,
        "duplicate_team_violations": sum(1 for e in errors if e.startswith("R6")),
        "duplicate_group_violations": sum(1 for e in errors if e.startswith("R5")),
        "appearance_count_violations": sum(
            1 for e in errors if e.startswith("R3") or e.startswith("R4")
        ),
        "blank_assignment_violations": sum(1 for e in errors if e.startswith("R7")),
    }


def run_allocation_simulation(
    participants: list[str],
    n: int = 1000,
    output_path: Path | str | None = None,
) -> dict:
    """Run n allocation simulations, write a CSV report, and return a summary."""
    _ensure_lookups()
    csv_path = Path(output_path) if output_path else _DEFAULT_AUDIT_PATH
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    passes = 0
    fail_runtime = 0
    spreads: list[float] = []

    for run in range(1, n + 1):
        try:
            alloc = generate_allocations(participants)
            audit = audit_allocation_run(alloc, participants)
        except RuntimeError as exc:
            fail_runtime += 1
            audit = {
                "passed": False,
                "spread": float("nan"),
                "min_score": float("nan"),
                "max_score": float("nan"),
                "failure_reasons": [str(exc)],
                "duplicate_team_violations": 0,
                "duplicate_group_violations": 0,
                "appearance_count_violations": 0,
                "blank_assignment_violations": 0,
            }

        if audit["passed"]:
            passes += 1
            spreads.append(audit["spread"])

        rows.append({
            "run_number": run,
            "min_score": audit["min_score"],
            "max_score": audit["max_score"],
            "spread": audit["spread"],
            "passed": audit["passed"],
            "failure_reason": "; ".join(audit["failure_reasons"]),
            "duplicate_team_violations": audit["duplicate_team_violations"],
            "duplicate_group_violations": audit["duplicate_group_violations"],
            "appearance_count_violations": audit["appearance_count_violations"],
            "blank_assignment_violations": audit["blank_assignment_violations"],
        })

    _write_csv(csv_path, rows)

    failures = n - passes
    return {
        "n": n,
        "passes": passes,
        "failures": failures,
        "fail_runtime": fail_runtime,
        "pass_rate": passes / n,
        "spreads": {
            "min": min(spreads) if spreads else float("nan"),
            "max": max(spreads) if spreads else float("nan"),
            "mean": statistics.mean(spreads) if spreads else float("nan"),
        },
        "rows": rows,
        "csv_path": str(csv_path),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "run_number", "min_score", "max_score", "spread", "passed",
        "failure_reason", "duplicate_team_violations",
        "duplicate_group_violations", "appearance_count_violations",
        "blank_assignment_violations",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_alloc(assignments: dict[str, list[str]]) -> Allocation:
    return Allocation(
        assignments=assignments,
        portfolio_scores=_scores(assignments),
    )


def _scores(assignments: dict[str, list[str]]) -> dict[str, float]:
    return {p: calculate_portfolio_strength(teams) for p, teams in assignments.items()}


def _try_generate(participants: list[str], teams_per_tier: int) -> dict[str, list[str]] | None:
    """One random generation pass. Returns None if any constraint is unresolvable."""
    n = len(participants)
    _, max_app = _appearance_limits(n, teams_per_tier)

    usage: dict[str, int] = {t: 0 for t in _all_teams}
    assignments: dict[str, list[str]] = {p: [] for p in participants}

    for tier in TIERS:
        tier_teams = _teams_in_tier[tier]
        p_order = list(participants)
        random.shuffle(p_order)

        for participant in p_order:
            used_groups = {_group_of[t] for t in assignments[participant]}

            eligible = [
                t for t in tier_teams
                if usage[t] < max_app and _group_of[t] not in used_groups
            ]
            if len(eligible) < teams_per_tier:
                return None

            random.shuffle(eligible)
            eligible.sort(key=lambda t: usage[t])

            chosen: list[str] = []
            chosen_groups: set[str] = set()
            for t in eligible:
                g = _group_of[t]
                if g not in chosen_groups:
                    chosen.append(t)
                    chosen_groups.add(g)
                if len(chosen) == teams_per_tier:
                    break

            if len(chosen) < teams_per_tier:
                return None

            for t in chosen:
                usage[t] += 1
            assignments[participant].extend(chosen)

    return assignments


def _try_pick_one(other_usage: dict[str, int], teams_per_tier: int) -> list[str] | None:
    """Pick a valid set of teams for one participant given fixed usage from all others."""
    assigned: list[str] = []

    for tier in TIERS:
        used_groups = {_group_of[t] for t in assigned}

        eligible = [
            t for t in _teams_in_tier[tier]
            if other_usage.get(t, 0) < 3 and _group_of[t] not in used_groups
        ]
        if len(eligible) < teams_per_tier:
            return None

        random.shuffle(eligible)
        chosen: list[str] = []
        chosen_groups: set[str] = set()
        for t in eligible:
            g = _group_of[t]
            if g not in chosen_groups:
                chosen.append(t)
                chosen_groups.add(g)
            if len(chosen) == teams_per_tier:
                break

        if len(chosen) < teams_per_tier:
            return None

        assigned.extend(chosen)

    return assigned


def _best_swap(
    assignments: dict[str, list[str]],
    scores: dict[str, float],
    max_p: str,
    min_p: str,
) -> tuple[int, int] | None:
    """Return (i, j) index pair for the swap that most reduces global spread."""
    old_spread = max(scores.values()) - min(scores.values())
    best_gain = 0.0
    best: tuple[int, int] | None = None

    max_teams = assignments[max_p]
    min_teams = assignments[min_p]

    for i, t_max in enumerate(max_teams):
        tier = _tier_of[t_max]
        s_max = _strength_of[t_max]

        for j, t_min in enumerate(min_teams):
            if _tier_of[t_min] != tier:
                continue
            s_min = _strength_of[t_min]
            if s_max == s_min:
                continue

            new_max = list(max_teams)
            new_min = list(min_teams)
            new_max[i] = t_min
            new_min[j] = t_max

            if not _groups_unique(new_max) or not _groups_unique(new_min):
                continue

            new_scores = dict(scores)
            new_scores[max_p] = scores[max_p] - s_max + s_min
            new_scores[min_p] = scores[min_p] - s_min + s_max
            new_spread = max(new_scores.values()) - min(new_scores.values())
            gain = old_spread - new_spread

            if gain > best_gain:
                best_gain = gain
                best = (i, j)

    return best


def _groups_unique(teams: list[str]) -> bool:
    """Return True if no two teams in the list share a World Cup group."""
    groups = [_group_of[t] for t in teams]
    return len(groups) == len(set(groups))
