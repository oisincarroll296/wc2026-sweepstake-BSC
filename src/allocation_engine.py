"""Allocation engine for World Cup 2026 Sweepstake."""

import csv
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from src.team_database import load_teams

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIERS = (1, 2, 3, 4)
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
# Public API — core engine
# ---------------------------------------------------------------------------


def calculate_portfolio_strength(teams: list[str]) -> float:
    """Return the sum of StrengthScore (101 − FIFARank) for a list of teams.

    Unknown team names contribute 0; no error is raised.
    """
    _ensure_lookups()
    return float(sum(_strength_of.get(t, 0) for t in teams))


def generate_allocations(
    participants: list[str],
    max_attempts: int = MAX_GENERATION_ATTEMPTS,
) -> Allocation:
    """Generate a balanced, fully-constrained allocation for all participants.

    Retries random assignment up to *max_attempts* times until every
    validation rule passes and the portfolio spread is within
    BALANCE_THRESHOLD.

    Raises RuntimeError if no valid allocation is found within max_attempts.
    """
    _ensure_lookups()

    for _ in range(max_attempts):
        assignments = _try_generate(participants)
        if assignments is None:
            continue
        alloc = _make_alloc(assignments)
        alloc = balance_allocations(alloc)
        if not validate_allocations(alloc, participants):
            return alloc

    raise RuntimeError(
        f"Could not generate a valid allocation after {max_attempts} attempts."
    )


def balance_allocations(
    alloc: Allocation,
    max_iterations: int = MAX_BALANCE_ITERATIONS,
) -> Allocation:
    """Reduce portfolio spread through iterative same-tier team swaps.

    Swaps are only accepted when they:
      - improve the global spread, and
      - preserve group uniqueness in both affected portfolios.

    Stops when spread <= BALANCE_THRESHOLD or no improving swap exists.
    """
    _ensure_lookups()
    assignments = {p: list(teams) for p, teams in alloc.assignments.items()}
    participants = list(assignments.keys())

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
) -> list[str]:
    """Check every allocation rule. Returns error strings; empty list = valid.

    Rules
    -----
    R1  Every participant has exactly 8 teams.
    R2  Exactly 2 teams from each tier per participant.
    R3  No team appears more than 3 times across all participants.
    R4  Every team appears at least 2 times (skipped when check_min_appearances=False).
    R5  No two teams in a participant's portfolio share a World Cup group.
    R6  No duplicate team within a participant's portfolio.
    R7  No blank team assignments.
    R8  Portfolio spread (max − min) <= BALANCE_THRESHOLD.
    R9  Stored portfolio scores match freshly calculated values.
    """
    _ensure_lookups()
    errors: list[str] = []
    assignments = alloc.assignments

    # Global usage tally (needed for R3/R4)
    usage: dict[str, int] = {}
    for teams in assignments.values():
        for t in teams:
            usage[t] = usage.get(t, 0) + 1

    for p in participants:
        teams = assignments.get(p, [])

        # R1 — count
        if len(teams) != 8:
            errors.append(f"R1 {p}: {len(teams)} teams (expected 8)")

        # R2 — tier distribution
        tier_counts: dict[int, int] = {}
        for t in teams:
            tr = _tier_of.get(t, 0)
            tier_counts[tr] = tier_counts.get(tr, 0) + 1
        for tier in TIERS:
            if tier_counts.get(tier, 0) != 2:
                errors.append(
                    f"R2 {p}: Tier {tier} has {tier_counts.get(tier, 0)} teams (expected 2)"
                )

        # R5 — group uniqueness
        groups = [_group_of.get(t, "?") for t in teams]
        if len(groups) != len(set(groups)):
            dupes = sorted({g for g in groups if groups.count(g) > 1})
            errors.append(f"R5 {p}: shared groups {dupes}")

        # R6 — duplicate teams
        if len(teams) != len(set(teams)):
            dupes_t = sorted({t for t in teams if teams.count(t) > 1})
            errors.append(f"R6 {p}: duplicate teams {dupes_t}")

        # R7 — blank assignments
        blanks = [t for t in teams if not t or not str(t).strip()]
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
        if count > 3:
            errors.append(f"R3 {team}: {count} appearances (max 3)")

    # R4 — min appearances
    if check_min_appearances:
        for team in _all_teams:
            if usage.get(team, 0) < 2:
                errors.append(
                    f"R4 {team}: {usage.get(team, 0)} appearances (min 2)"
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
    """Regenerate teams for one participant without altering any other assignment.

    Runs up to max_attempts random draws for the target participant. Returns
    the draw that minimises the global portfolio spread. If no draw achieves
    spread <= BALANCE_THRESHOLD, returns the best found rather than raising.

    Raises RuntimeError if no valid 8-team set can be generated at all.
    """
    _ensure_lookups()

    other_usage: dict[str, int] = {}
    other_scores: dict[str, float] = {}
    for p, teams in alloc.assignments.items():
        if p == participant:
            continue
        other_scores[p] = calculate_portfolio_strength(teams)
        for t in teams:
            other_usage[t] = other_usage.get(t, 0) + 1

    best_result: Allocation | None = None
    best_spread = float("inf")

    for _ in range(max_attempts):
        new_teams = _try_pick_one(other_usage)
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
    """Return a structured audit of one allocation.

    Returns a dict with keys:
        passed                      bool
        spread                      float
        min_score                   float
        max_score                   float
        failure_reasons             list[str]   — empty when passed
        duplicate_team_violations   int         — participants with R6 errors
        duplicate_group_violations  int         — participants with R5 errors
        appearance_count_violations int         — teams violating R3 or R4
        blank_assignment_violations int         — participants with R7 errors
    """
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
    """Run *n* allocation simulations, write a CSV report, and return a summary.

    CSV path defaults to exports/allocation_audit.csv relative to the project root.

    CSV columns
    -----------
    run_number, min_score, max_score, spread, passed, failure_reason,
    duplicate_team_violations, duplicate_group_violations,
    appearance_count_violations, blank_assignment_violations

    Returns
    -------
    dict with keys: n, passes, failures, pass_rate, spreads (min/max/mean), rows
    """
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


def _try_generate(participants: list[str]) -> dict[str, list[str]] | None:
    """One random generation pass. Returns None if any constraint is unresolvable."""
    usage: dict[str, int] = {t: 0 for t in _all_teams}
    assignments: dict[str, list[str]] = {p: [] for p in participants}

    for tier in TIERS:
        tier_teams = _teams_in_tier[tier]
        # Shuffle participant order per tier for fair spread of appearances
        p_order = list(participants)
        random.shuffle(p_order)

        for participant in p_order:
            used_groups = {_group_of[t] for t in assignments[participant]}

            # Under usage cap and group not already in this portfolio
            eligible = [
                t for t in tier_teams
                if usage[t] < 3 and _group_of[t] not in used_groups
            ]
            if len(eligible) < 2:
                return None

            # Prefer under-used teams (ensures min 2 appearances globally);
            # shuffle first so equal-usage teams are drawn at random
            random.shuffle(eligible)
            eligible.sort(key=lambda t: usage[t])

            # Pick 2 from different groups
            chosen: list[str] = []
            chosen_groups: set[str] = set()
            for t in eligible:
                g = _group_of[t]
                if g not in chosen_groups:
                    chosen.append(t)
                    chosen_groups.add(g)
                if len(chosen) == 2:
                    break

            if len(chosen) < 2:
                return None

            for t in chosen:
                usage[t] += 1
            assignments[participant].extend(chosen)

    return assignments


def _try_pick_one(other_usage: dict[str, int]) -> list[str] | None:
    """Pick 8 valid teams for one participant given fixed usage from all others."""
    assigned: list[str] = []

    for tier in TIERS:
        used_groups = {_group_of[t] for t in assigned}

        eligible = [
            t for t in _teams_in_tier[tier]
            if other_usage.get(t, 0) < 3 and _group_of[t] not in used_groups
        ]
        if len(eligible) < 2:
            return None

        random.shuffle(eligible)
        chosen: list[str] = []
        chosen_groups: set[str] = set()
        for t in eligible:
            g = _group_of[t]
            if g not in chosen_groups:
                chosen.append(t)
                chosen_groups.add(g)
            if len(chosen) == 2:
                break

        if len(chosen) < 2:
            return None

        assigned.extend(chosen)

    return assigned


def _best_swap(
    assignments: dict[str, list[str]],
    scores: dict[str, float],
    max_p: str,
    min_p: str,
) -> tuple[int, int] | None:
    """Return (i, j) index pair for the swap that most reduces global spread.

    Considers only same-tier swaps between max_p and min_p that preserve
    group uniqueness in both resulting portfolios.
    Returns None when no improving swap exists.
    """
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

            # Tentative post-swap portfolios
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
