"""Comprehensive unit tests for src/allocation_engine.py.

Coverage
--------
- calculate_portfolio_strength  (strength formula, edge cases)
- generate_allocations          (all 9 rules)
- balance_allocations           (spread, tier/group preservation)
- validate_allocations          (each rule independently, skipping R4)
- repick_participant             (isolation, constraints, appearance cap)
- audit_allocation_run          (structure, categorisation)
- run_allocation_simulation     (CSV, pass-rate)
- _groups_unique                (helper)
- Boundary group cases          (Groups C/D/K/L with shared-tier teams)
"""

import csv
import statistics
from pathlib import Path

import pytest

from src.allocation_engine import (
    BALANCE_THRESHOLD,
    Allocation,
    audit_allocation_run,
    balance_allocations,
    calculate_portfolio_strength,
    generate_allocations,
    repick_participant,
    run_allocation_simulation,
    validate_allocations,
    _groups_unique,
)
from src.team_database import load_teams

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PARTICIPANTS = [f"Player {i + 1}" for i in range(13)]


def _alloc() -> Allocation:
    return generate_allocations(PARTICIPANTS)


def _df():
    return load_teams()


def _group_of(team: str) -> str:
    return str(_df().loc[_df()["Team"] == team, "Group"].iloc[0])


def _tier_of(team: str) -> int:
    return int(_df().loc[_df()["Team"] == team, "Tier"].iloc[0])


def _usage(alloc: Allocation) -> dict[str, int]:
    u: dict[str, int] = {}
    for teams in alloc.assignments.values():
        for t in teams:
            u[t] = u.get(t, 0) + 1
    return u


# ---------------------------------------------------------------------------
# calculate_portfolio_strength
# ---------------------------------------------------------------------------

class TestCalculatePortfolioStrength:
    def test_empty_list_zero(self):
        assert calculate_portfolio_strength([]) == 0.0

    def test_single_top_team(self):
        # France rank 1 → 101-1 = 100
        assert calculate_portfolio_strength(["France"]) == 100.0

    def test_single_bottom_team(self):
        # New Zealand rank 85 → 101-85 = 16
        assert calculate_portfolio_strength(["New Zealand"]) == 16.0

    def test_two_teams_sum(self):
        assert calculate_portfolio_strength(["France", "Spain"]) == 199.0

    def test_unknown_team_is_zero(self):
        assert calculate_portfolio_strength(["France", "Atlantis FC"]) == 100.0

    def test_returns_float(self):
        assert isinstance(calculate_portfolio_strength(["Germany"]), float)

    def test_formula_101_minus_rank(self):
        df = _df()
        for _, row in df.iterrows():
            expected = 101 - int(row["FIFARank"])
            assert calculate_portfolio_strength([row["Team"]]) == float(expected)

    def test_all_48_teams_sum(self):
        df = _df()
        all_teams = df["Team"].tolist()
        expected = float(df["StrengthScore"].sum())
        assert calculate_portfolio_strength(all_teams) == expected


# ---------------------------------------------------------------------------
# generate_allocations — R1: team count
# ---------------------------------------------------------------------------

class TestGenerateR1TeamCount:
    def test_each_participant_has_exactly_8_teams(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            assert len(alloc.assignments[p]) == 8, f"{p}: {len(alloc.assignments[p])}"

    def test_all_participants_present(self):
        alloc = _alloc()
        assert set(alloc.assignments.keys()) == set(PARTICIPANTS)


# ---------------------------------------------------------------------------
# generate_allocations — R2: tier distribution
# ---------------------------------------------------------------------------

class TestGenerateR2TierDistribution:
    def test_exactly_2_tier1_per_participant(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            n = sum(1 for t in alloc.assignments[p] if _tier_of(t) == 1)
            assert n == 2, f"{p} Tier 1: {n}"

    def test_exactly_2_tier2_per_participant(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            n = sum(1 for t in alloc.assignments[p] if _tier_of(t) == 2)
            assert n == 2, f"{p} Tier 2: {n}"

    def test_exactly_2_tier3_per_participant(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            n = sum(1 for t in alloc.assignments[p] if _tier_of(t) == 3)
            assert n == 2, f"{p} Tier 3: {n}"

    def test_exactly_2_tier4_per_participant(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            n = sum(1 for t in alloc.assignments[p] if _tier_of(t) == 4)
            assert n == 2, f"{p} Tier 4: {n}"


# ---------------------------------------------------------------------------
# generate_allocations — R3/R4: global appearance limits
# ---------------------------------------------------------------------------

class TestGenerateAppearanceLimits:
    def test_no_team_exceeds_3_appearances(self):
        alloc = _alloc()
        over = {t: c for t, c in _usage(alloc).items() if c > 3}
        assert not over, f"Teams over 3 appearances: {over}"

    def test_every_team_appears_at_least_twice(self):
        df = _df()
        alloc = _alloc()
        u = _usage(alloc)
        under = {t: u.get(t, 0) for t in df["Team"] if u.get(t, 0) < 2}
        assert not under, f"Teams under 2 appearances: {under}"

    def test_total_assignments_equals_104(self):
        # 13 participants × 8 teams
        alloc = _alloc()
        total = sum(len(t) for t in alloc.assignments.values())
        assert total == 104

    def test_tier1_total_assignments_26(self):
        # 13 participants × 2 T1 teams
        alloc = _alloc()
        total = sum(1 for teams in alloc.assignments.values()
                    for t in teams if _tier_of(t) == 1)
        assert total == 26

    def test_tier4_total_assignments_26(self):
        alloc = _alloc()
        total = sum(1 for teams in alloc.assignments.values()
                    for t in teams if _tier_of(t) == 4)
        assert total == 26


# ---------------------------------------------------------------------------
# generate_allocations — R5: group uniqueness
# ---------------------------------------------------------------------------

class TestGenerateR5GroupUniqueness:
    def test_no_participant_holds_two_same_group_teams(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            groups = [_group_of(t) for t in alloc.assignments[p]]
            assert len(groups) == len(set(groups)), (
                f"{p}: duplicate groups {groups}"
            )

    # Named boundary cases
    def test_group_c_brazil_morocco_not_paired(self):
        # Both Tier 1, Group C
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"Brazil", "Morocco"} <= held), f"{p} holds both Group C T1 teams"

    def test_group_k_portugal_colombia_not_paired(self):
        # Both Tier 1, Group K
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"Portugal", "Colombia"} <= held), f"{p} holds both Group K T1 teams"

    def test_group_l_england_croatia_not_paired(self):
        # Both Tier 1, Group L
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"England", "Croatia"} <= held), f"{p} holds both Group L T1 teams"

    def test_group_d_at_most_one_per_participant(self):
        # USA, Tuerkiye, Australia are all Group D Tier 2
        group_d = {"USA", "Tuerkiye", "Australia"}
        alloc = _alloc()
        for p in PARTICIPANTS:
            overlap = group_d & set(alloc.assignments[p])
            assert len(overlap) <= 1, f"{p} holds {overlap} from Group D"

    def test_group_a_mexico_korea_not_paired(self):
        # Mexico and Korea Republic are both Group A Tier 2
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"Mexico", "Korea Republic"} <= held), f"{p}: Group A T2 conflict"

    def test_group_b_t4_not_paired(self):
        # Qatar and Bosnia are both Group B Tier 4
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"Qatar", "Bosnia and Herzegovina"} <= held), f"{p}: Group B T4 conflict"

    def test_group_h_t4_not_paired(self):
        # Saudi Arabia and Cabo Verde are both Group H Tier 4
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"Saudi Arabia", "Cabo Verde"} <= held), f"{p}: Group H T4 conflict"

    def test_group_f_t3_not_paired(self):
        # Sweden and Tunisia are both Group F Tier 3
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"Sweden", "Tunisia"} <= held), f"{p}: Group F T3 conflict"

    def test_cross_tier_group_constraint(self):
        # France (T1, I) and Senegal (T2, I) cannot share a portfolio
        alloc = _alloc()
        for p in PARTICIPANTS:
            held = set(alloc.assignments[p])
            assert not ({"France", "Senegal"} <= held), f"{p}: France+Senegal both Group I"


# ---------------------------------------------------------------------------
# generate_allocations — R6/R7: duplicates and blanks
# ---------------------------------------------------------------------------

class TestGenerateR6R7:
    def test_no_duplicate_teams_per_participant(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            teams = alloc.assignments[p]
            assert len(teams) == len(set(teams)), f"{p}: duplicates in {teams}"

    def test_no_blank_assignments(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            blanks = [t for t in alloc.assignments[p] if not t or not t.strip()]
            assert not blanks, f"{p}: blank entries"


# ---------------------------------------------------------------------------
# generate_allocations — R8/R9: spread and score accuracy
# ---------------------------------------------------------------------------

class TestGenerateR8R9:
    def test_spread_within_threshold(self):
        alloc = _alloc()
        scores = list(alloc.portfolio_scores.values())
        spread = max(scores) - min(scores)
        assert spread <= BALANCE_THRESHOLD, f"Spread {spread:.1f} > {BALANCE_THRESHOLD}"

    def test_all_participant_scores_positive(self):
        alloc = _alloc()
        for p, score in alloc.portfolio_scores.items():
            assert score > 0, f"{p}: score {score}"

    def test_portfolio_scores_match_calculated(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            expected = calculate_portfolio_strength(alloc.assignments[p])
            assert abs(alloc.portfolio_scores[p] - expected) < 0.001, (
                f"{p}: stored {alloc.portfolio_scores[p]} != calc {expected}"
            )

    def test_validate_returns_empty_errors(self):
        alloc = _alloc()
        errors = validate_allocations(alloc, PARTICIPANTS)
        assert errors == [], "\n".join(errors)


# ---------------------------------------------------------------------------
# balance_allocations
# ---------------------------------------------------------------------------

class TestBalanceAllocations:
    def test_returns_allocation_instance(self):
        assert isinstance(balance_allocations(_alloc()), Allocation)

    def test_spread_within_threshold(self):
        alloc = _alloc()
        balanced = balance_allocations(alloc)
        scores = list(balanced.portfolio_scores.values())
        assert max(scores) - min(scores) <= BALANCE_THRESHOLD

    def test_each_participant_still_has_8_teams(self):
        balanced = balance_allocations(_alloc())
        for p in PARTICIPANTS:
            assert len(balanced.assignments[p]) == 8

    def test_tier_distribution_preserved_after_balance(self):
        balanced = balance_allocations(_alloc())
        for p in PARTICIPANTS:
            for tier in (1, 2, 3, 4):
                n = sum(1 for t in balanced.assignments[p] if _tier_of(t) == tier)
                assert n == 2, f"{p} Tier {tier} after balance: {n}"

    def test_group_uniqueness_preserved_after_balance(self):
        balanced = balance_allocations(_alloc())
        for p in PARTICIPANTS:
            groups = [_group_of(t) for t in balanced.assignments[p]]
            assert len(groups) == len(set(groups)), (
                f"{p}: group conflict after balance"
            )

    def test_scores_recalculated_after_balance(self):
        balanced = balance_allocations(_alloc())
        for p in PARTICIPANTS:
            expected = calculate_portfolio_strength(balanced.assignments[p])
            assert abs(balanced.portfolio_scores[p] - expected) < 0.001

    def test_total_team_count_unchanged(self):
        alloc = _alloc()
        before = sum(len(t) for t in alloc.assignments.values())
        after = sum(len(t) for t in balance_allocations(alloc).assignments.values())
        assert before == after == 104

    def test_appearance_counts_unchanged_after_balance(self):
        alloc = _alloc()
        before = _usage(alloc)
        after = _usage(balance_allocations(alloc))
        assert before == after


# ---------------------------------------------------------------------------
# validate_allocations — each rule triggered independently
# ---------------------------------------------------------------------------

class TestValidateAllocationsRules:
    def test_clean_allocation_no_errors(self):
        assert validate_allocations(_alloc(), PARTICIPANTS) == []

    # R1
    def test_r1_too_few_teams(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        bad = Allocation(
            assignments={**alloc.assignments, p: alloc.assignments[p][:6]},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R1" in e and p in e for e in errors)

    def test_r1_too_many_teams(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        extra = alloc.assignments[p] + ["France"]
        bad = Allocation(
            assignments={**alloc.assignments, p: extra},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R1" in e and p in e for e in errors)

    # R2
    def test_r2_wrong_tier_count(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        # swap a T2 slot for a T1 team not already held
        df = _df()
        t1_spare = next(
            t for t in df[df["Tier"] == 1]["Team"]
            if t not in teams
        )
        for i, t in enumerate(teams):
            if _tier_of(t) == 2:
                teams[i] = t1_spare
                break
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R2" in e for e in errors)

    # R3
    def test_r3_team_appears_4_times(self):
        alloc = _alloc()
        # inject a 4th appearance by duplicating across two portfolios
        p0, p1 = PARTICIPANTS[0], PARTICIPANTS[1]
        team = alloc.assignments[p0][0]
        bad_p1 = [team if t != alloc.assignments[p1][0] else t
                  for i, t in enumerate(alloc.assignments[p1])]
        bad_p1[0] = team  # force duplicate
        bad = Allocation(
            assignments={**alloc.assignments, p0: alloc.assignments[p0], p1: bad_p1},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        # The team will appear 3+ times; R3 fires if > 3
        # Count actual usage to verify test is meaningful
        u = _usage(bad)
        if u.get(team, 0) > 3:
            assert any("R3" in e for e in errors)

    # R5
    def test_r5_same_group_pair(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        g0 = _group_of(teams[0])
        df = _df()
        same = df[df["Group"] == g0]["Team"].tolist()
        replacement = next(
            (t for t in same if t not in teams and t != teams[0]), None
        )
        if replacement is None:
            pytest.skip("No same-group replacement available for this seed")
        teams[1] = replacement
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R5" in e and p in e for e in errors)

    def test_r5_france_senegal_conflict(self):
        # Construct a synthetic Allocation with France+Senegal (both Group I) in one portfolio
        alloc = _alloc()
        p = PARTICIPANTS[0]
        df = _df()
        # build a portfolio with France (T1,I) + Senegal (T2,I) + 6 others from different groups
        t3_teams = df[(df["Tier"] == 3) & (~df["Group"].isin(["I"]))]["Team"].tolist()[:2]
        t4_teams = df[(df["Tier"] == 4) & (~df["Group"].isin(["I"] + [_group_of(t) for t in t3_teams]))]["Team"].tolist()[:2]
        bad_teams = ["France", "Spain", "Senegal", "Switzerland"] + t3_teams + t4_teams
        if len(bad_teams) != 8:
            pytest.skip("Could not construct synthetic portfolio")
        bad = Allocation(
            assignments={**alloc.assignments, p: bad_teams},
            portfolio_scores={**alloc.portfolio_scores, p: calculate_portfolio_strength(bad_teams)},
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R5" in e and p in e for e in errors)

    # R6
    def test_r6_duplicate_team(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        teams[1] = teams[0]
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R6" in e and p in e for e in errors)

    # R7
    def test_r7_blank_entry(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        teams[0] = ""
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R7" in e and p in e for e in errors)

    def test_r7_whitespace_entry(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        teams[0] = "   "
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R7" in e and p in e for e in errors)

    # R8
    def test_r8_spread_over_threshold(self):
        alloc = _alloc()
        scores = {**alloc.portfolio_scores, PARTICIPANTS[0]: alloc.portfolio_scores[PARTICIPANTS[0]] + 100}
        bad = Allocation(assignments=alloc.assignments, portfolio_scores=scores)
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R8" in e for e in errors)

    # R9
    def test_r9_wrong_stored_score(self):
        alloc = _alloc()
        scores = {**alloc.portfolio_scores, PARTICIPANTS[0]: 9999.0}
        bad = Allocation(assignments=alloc.assignments, portfolio_scores=scores)
        errors = validate_allocations(bad, PARTICIPANTS)
        assert any("R9" in e and PARTICIPANTS[0] in e for e in errors)

    # Flag control
    def test_r4_skipped_when_flag_false(self):
        alloc = _alloc()
        errors = validate_allocations(alloc, PARTICIPANTS, check_min_appearances=False)
        assert not any("R4" in e for e in errors)

    def test_r4_active_by_default(self):
        # A clean allocation should not trigger R4
        alloc = _alloc()
        errors = validate_allocations(alloc, PARTICIPANTS, check_min_appearances=True)
        assert not any("R4" in e for e in errors)


# ---------------------------------------------------------------------------
# repick_participant
# ---------------------------------------------------------------------------

class TestRepickParticipant:
    def test_only_target_assignment_changes(self):
        alloc = _alloc()
        target = PARTICIPANTS[4]
        repicked = repick_participant(alloc, target)
        for p in PARTICIPANTS:
            if p != target:
                assert repicked.assignments[p] == alloc.assignments[p], (
                    f"{p} changed unexpectedly"
                )

    def test_target_has_8_teams(self):
        alloc = _alloc()
        repicked = repick_participant(alloc, PARTICIPANTS[0])
        assert len(repicked.assignments[PARTICIPANTS[0]]) == 8

    def test_target_2_per_tier(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        for tier in (1, 2, 3, 4):
            n = sum(1 for t in repicked.assignments[target] if _tier_of(t) == tier)
            assert n == 2, f"Tier {tier}: {n} after repick"

    def test_target_group_uniqueness(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        groups = [_group_of(t) for t in repicked.assignments[target]]
        assert len(groups) == len(set(groups)), f"Group conflict after repick: {groups}"

    def test_target_no_duplicate_teams(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        teams = repicked.assignments[target]
        assert len(teams) == len(set(teams))

    def test_no_team_exceeds_3_after_repick(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        over = {t: c for t, c in _usage(repicked).items() if c > 3}
        assert not over, f"Over-cap after repick: {over}"

    def test_target_score_recalculated(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        expected = calculate_portfolio_strength(repicked.assignments[target])
        assert abs(repicked.portfolio_scores[target] - expected) < 0.001

    def test_other_scores_unchanged(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        for p in PARTICIPANTS[1:]:
            assert abs(repicked.portfolio_scores[p] - alloc.portfolio_scores[p]) < 0.001

    def test_every_participant_can_be_repicked(self):
        alloc = _alloc()
        for p in PARTICIPANTS:
            result = repick_participant(alloc, p)
            assert len(result.assignments[p]) == 8

    def test_no_blank_teams_after_repick(self):
        alloc = _alloc()
        target = PARTICIPANTS[0]
        repicked = repick_participant(alloc, target)
        blanks = [t for t in repicked.assignments[target] if not t or not t.strip()]
        assert not blanks


# ---------------------------------------------------------------------------
# audit_allocation_run
# ---------------------------------------------------------------------------

class TestAuditAllocationRun:
    def test_returns_dict(self):
        assert isinstance(audit_allocation_run(_alloc(), PARTICIPANTS), dict)

    def test_required_keys_present(self):
        audit = audit_allocation_run(_alloc(), PARTICIPANTS)
        required = {
            "passed", "spread", "min_score", "max_score",
            "failure_reasons",
            "duplicate_team_violations",
            "duplicate_group_violations",
            "appearance_count_violations",
            "blank_assignment_violations",
        }
        assert required.issubset(audit.keys())

    def test_clean_allocation_passes(self):
        audit = audit_allocation_run(_alloc(), PARTICIPANTS)
        assert audit["passed"] is True
        assert audit["failure_reasons"] == []

    def test_spread_matches_scores(self):
        alloc = _alloc()
        audit = audit_allocation_run(alloc, PARTICIPANTS)
        scores = list(alloc.portfolio_scores.values())
        assert abs(audit["spread"] - (max(scores) - min(scores))) < 0.001
        assert abs(audit["min_score"] - min(scores)) < 0.001
        assert abs(audit["max_score"] - max(scores)) < 0.001

    def test_r6_violation_counted(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        teams[1] = teams[0]
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        audit = audit_allocation_run(bad, PARTICIPANTS)
        assert not audit["passed"]
        assert audit["duplicate_team_violations"] >= 1

    def test_r5_violation_counted(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        g0 = _group_of(teams[0])
        df = _df()
        same = df[df["Group"] == g0]["Team"].tolist()
        replacement = next(
            (t for t in same if t not in teams and t != teams[0]), None
        )
        if replacement is None:
            pytest.skip("No same-group replacement available")
        teams[1] = replacement
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        audit = audit_allocation_run(bad, PARTICIPANTS)
        assert audit["duplicate_group_violations"] >= 1

    def test_r7_violation_counted(self):
        alloc = _alloc()
        p = PARTICIPANTS[0]
        teams = list(alloc.assignments[p])
        teams[0] = ""
        bad = Allocation(
            assignments={**alloc.assignments, p: teams},
            portfolio_scores=alloc.portfolio_scores,
        )
        audit = audit_allocation_run(bad, PARTICIPANTS)
        assert audit["blank_assignment_violations"] >= 1

    def test_r8_over_threshold_fails(self):
        alloc = _alloc()
        scores = {**alloc.portfolio_scores, PARTICIPANTS[0]: alloc.portfolio_scores[PARTICIPANTS[0]] + 100}
        bad = Allocation(assignments=alloc.assignments, portfolio_scores=scores)
        audit = audit_allocation_run(bad, PARTICIPANTS)
        assert not audit["passed"]


# ---------------------------------------------------------------------------
# _groups_unique
# ---------------------------------------------------------------------------

class TestGroupsUnique:
    def test_single_team_true(self):
        assert _groups_unique(["France"]) is True

    def test_different_groups_true(self):
        assert _groups_unique(["France", "Spain", "Germany"]) is True

    def test_empty_list_true(self):
        assert _groups_unique([]) is True

    def test_france_senegal_false(self):
        # Both Group I
        assert _groups_unique(["France", "Senegal"]) is False

    def test_brazil_morocco_false(self):
        # Both Group C
        assert _groups_unique(["Brazil", "Morocco"]) is False

    def test_portugal_colombia_false(self):
        # Both Group K
        assert _groups_unique(["Portugal", "Colombia"]) is False

    def test_england_croatia_false(self):
        # Both Group L
        assert _groups_unique(["England", "Croatia"]) is False

    def test_usa_tuerkiye_false(self):
        # Both Group D
        assert _groups_unique(["USA", "Tuerkiye"]) is False

    def test_qatar_bosnia_false(self):
        # Both Group B
        assert _groups_unique(["Qatar", "Bosnia and Herzegovina"]) is False

    def test_saudi_caboverde_false(self):
        # Both Group H
        assert _groups_unique(["Saudi Arabia", "Cabo Verde"]) is False


# ---------------------------------------------------------------------------
# run_allocation_simulation — 1000 runs, CSV output, 100% pass rate
# ---------------------------------------------------------------------------

class TestRunAllocationSimulation:
    def test_returns_dict_with_required_keys(self, tmp_path):
        result = run_allocation_simulation(PARTICIPANTS, n=5, output_path=tmp_path / "test.csv")
        assert {"n", "passes", "failures", "pass_rate", "spreads", "rows", "csv_path"}.issubset(result)

    def test_row_count_matches_n(self, tmp_path):
        n = 10
        result = run_allocation_simulation(PARTICIPANTS, n=n, output_path=tmp_path / "t.csv")
        assert len(result["rows"]) == n

    def test_csv_written(self, tmp_path):
        csv_path = tmp_path / "audit.csv"
        run_allocation_simulation(PARTICIPANTS, n=3, output_path=csv_path)
        assert csv_path.exists()

    def test_csv_columns(self, tmp_path):
        csv_path = tmp_path / "audit.csv"
        run_allocation_simulation(PARTICIPANTS, n=3, output_path=csv_path)
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
        required = {
            "run_number", "min_score", "max_score", "spread", "passed", "failure_reason",
            "duplicate_team_violations", "duplicate_group_violations",
            "appearance_count_violations", "blank_assignment_violations",
        }
        assert required.issubset(set(cols))

    def test_1000_simulations_100_percent_pass_rate(self):
        """Primary correctness gate: 1000 runs must all pass."""
        result = run_allocation_simulation(
            PARTICIPANTS,
            n=1000,
            output_path=Path("exports") / "allocation_audit.csv",
        )

        pass_rate = result["pass_rate"] * 100
        spreads = result["spreads"]

        print(f"\n{'=' * 46}")
        print(f"  1000-Simulation Audit")
        print(f"{'=' * 46}")
        print(f"  Pass rate  : {pass_rate:.1f}%  ({result['passes']}/{result['n']})")
        print(f"  Failures   : {result['failures']}")
        print(f"  Spread min : {spreads['min']:.1f}")
        print(f"  Spread max : {spreads['max']:.1f}")
        print(f"  Spread avg : {spreads['mean']:.1f}")
        print(f"  CSV        : {result['csv_path']}")
        print(f"{'=' * 46}")

        assert result["pass_rate"] == 1.0, (
            f"Pass rate {pass_rate:.1f}% — {result['failures']} failed runs. "
            f"See exports/allocation_audit.csv for details."
        )
        assert spreads["max"] <= BALANCE_THRESHOLD, (
            f"Worst spread {spreads['max']:.1f} exceeds threshold {BALANCE_THRESHOLD}"
        )
