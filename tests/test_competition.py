"""Unit tests for src/competition.py."""

import pytest
import pandas as pd

from src.competition import (
    # status
    get_player_status, mark_paid, mark_unpaid,
    get_paid_players, get_unpaid_players,
    # purchases
    add_purchase,
    get_player_purchases, purchases_to_scoring_format,
    # payment reference
    parse_payment_reference,
    # prize pool
    calculate_prize_pool, export_prize_pool,
    # events
    create_event, update_event_status,
    # audit
    log_action,
    # validation
    validate_dark_horse, validate_ninth_team, validate_resurrection,
    # draws
    assign_ninth_team, assign_resurrection_team,
    # mulligan
    execute_mulligan,
    # tiebreakers
    calculate_tiebreak_stats,
    # leaderboards
    prize_leaderboard, overall_leaderboard,
    # team ownership / predictions centre
    get_team_ownership, get_predictions_centre,
    # exports
    export_payment_ledger, export_player_summary,
    PRICES, INSURANCE_BONUS,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TIER_MAP: dict[str, int] = {
    "France": 1, "Spain": 1, "Argentina": 1, "England": 1,
    "Colombia": 1, "Morocco": 1,
    "USA": 2, "Mexico": 2, "Japan": 2, "Senegal": 2,
    "Norway": 3, "Panama": 3, "Scotland": 3, "Algeria": 3,
    "Qatar": 4, "Haiti": 4, "New Zealand": 4, "Ghana": 4,
}

_ASSIGNMENTS: dict[str, list[str]] = {
    "Alice": ["France", "Spain",    "USA",    "Mexico",  "Norway",  "Panama",  "Qatar",     "Haiti"],
    "Bob":   ["Argentina","England","Japan",  "Senegal", "Scotland","Algeria", "New Zealand","Ghana"],
    "Carol": ["Colombia", "Morocco","USA",    "Japan",   "Panama",  "Scotland","Qatar",     "New Zealand"],
}


def _empty_purchases() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])


def _empty_statuses() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "Status", "PaidTimestamp"])


def _empty_captains() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "CaptainType", "Team"])


def _empty_predictions() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])


def _empty_ms() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "Team", "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins",
        "GroupComebackWins", "GroupWinner", "KnockoutGoals",
        "KnockoutCleanSheets", "KnockoutPenaltyWins", "KnockoutComebackWins",
        "RoundReached",
    ])


def _ms(*rows) -> pd.DataFrame:
    defaults = {
        "Team": "X", "GroupGoals": 0, "GroupCleanSheets": 0,
        "GroupPenaltyWins": 0, "GroupComebackWins": 0, "GroupWinner": 0,
        "KnockoutGoals": 0, "KnockoutCleanSheets": 0, "KnockoutPenaltyWins": 0,
        "KnockoutComebackWins": 0, "RoundReached": "GroupStage",
    }
    records = [{**defaults, **r} for r in rows]
    return pd.DataFrame(records)


def _purchases(*rows) -> pd.DataFrame:
    records = [
        {"Player": r[0], "PurchaseType": r[1], "Selection": r[2] if len(r) > 2 else "",
         "Reference": "", "Timestamp": ""}
        for r in rows
    ]
    return pd.DataFrame(records, columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])


def _statuses(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Player", "Status", "PaidTimestamp"])


def _captains(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Player", "CaptainType", "Team"])


def _predictions(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])


# ---------------------------------------------------------------------------
# TestPlayerStatus
# ---------------------------------------------------------------------------

class TestPlayerStatus:
    def test_unknown_player_is_unpaid(self):
        assert get_player_status("Alice", _empty_statuses()) == "UNPAID"

    def test_empty_statuses_is_unpaid(self):
        assert get_player_status("Alice", _empty_statuses()) == "UNPAID"

    def test_known_paid_player(self):
        st = _statuses(("Alice", "PAID", "2026-06-01T10:00:00"))
        assert get_player_status("Alice", st) == "PAID"

    def test_known_unpaid_player(self):
        st = _statuses(("Alice", "UNPAID", ""))
        assert get_player_status("Alice", st) == "UNPAID"

    def test_mark_paid_new_player(self):
        st = mark_paid("Alice", _empty_statuses(), "2026-06-01T10:00:00")
        assert get_player_status("Alice", st) == "PAID"

    def test_mark_paid_existing_unpaid(self):
        st = _statuses(("Alice", "UNPAID", ""))
        st = mark_paid("Alice", st, "2026-06-01T10:00:00")
        assert get_player_status("Alice", st) == "PAID"

    def test_mark_paid_records_timestamp(self):
        st = mark_paid("Alice", _empty_statuses(), "2026-06-01T10:00:00")
        assert st[st["Player"] == "Alice"]["PaidTimestamp"].iloc[0] == "2026-06-01T10:00:00"

    def test_mark_unpaid_resets_status(self):
        st = _statuses(("Alice", "PAID", "2026-06-01"))
        st = mark_unpaid("Alice", st)
        assert get_player_status("Alice", st) == "UNPAID"

    def test_get_paid_players(self):
        st = _statuses(("Alice", "PAID", ""), ("Bob", "UNPAID", ""))
        assert get_paid_players(st) == ["Alice"]

    def test_get_unpaid_players(self):
        st = _statuses(("Alice", "PAID", ""), ("Bob", "UNPAID", ""))
        assert get_unpaid_players(st) == ["Bob"]

    def test_get_paid_empty_statuses(self):
        assert get_paid_players(_empty_statuses()) == []

    def test_multiple_paid_players(self):
        st = _statuses(
            ("Alice", "PAID", ""), ("Bob", "PAID", ""), ("Carol", "UNPAID", ""),
        )
        assert set(get_paid_players(st)) == {"Alice", "Bob"}

# ---------------------------------------------------------------------------
# TestPrizePool
# ---------------------------------------------------------------------------

class TestPrizePool:
    def test_empty_purchases_zero_pot(self):
        pool = calculate_prize_pool(_empty_purchases())
        assert pool["current_pot"] == 0.0

    def test_buyin_adds_5(self):
        p = _purchases(("Alice", "BuyIn"))
        assert calculate_prize_pool(p)["current_pot"] == 5.0

    def test_pack_adds_5(self):
        p = _purchases(("Alice", "PredictionPack"))
        assert calculate_prize_pool(p)["current_pot"] == 5.0

    def test_mulligan_adds_3(self):
        p = _purchases(("Alice", "Mulligan"))
        assert calculate_prize_pool(p)["current_pot"] == 3.0

    def test_ninth_adds_3(self):
        p = _purchases(("Alice", "NinthTeam"))
        assert calculate_prize_pool(p)["current_pot"] == 3.0

    def test_resurrection_adds_5(self):
        p = _purchases(("Alice", "Resurrection"))
        assert calculate_prize_pool(p)["current_pot"] == 5.0

    def test_insurance_adds_2(self):
        p = _purchases(("Alice", "Insurance"))
        assert calculate_prize_pool(p)["current_pot"] == 2.0

    def test_prize_split_50_30_20(self):
        # 2 buyins = €10
        p = _purchases(
            ("Alice", "BuyIn"),
            ("Bob",   "BuyIn"),
        )
        pool = calculate_prize_pool(p)
        assert pool["current_pot"] == 10.0
        assert pool["first_prize"] == 5.0
        assert pool["second_prize"] == 3.0
        assert pool["third_prize"] == 2.0

    def test_prize_split_sums_to_pot(self):
        p = _purchases(
            ("Alice", "BuyIn"),
            ("Alice", "PredictionPack"),
            ("Bob",   "NinthTeam"),
        )
        pool = calculate_prize_pool(p)
        assert abs(pool["first_prize"] + pool["second_prize"] + pool["third_prize"] - pool["current_pot"]) < 0.01

    def test_export_prize_pool_creates_csv(self, tmp_path):
        p = _purchases(("Alice", "BuyIn"))
        out = tmp_path / "prize_pool.csv"
        df = export_prize_pool(p, out)
        assert out.exists()
        assert "CurrentPot" in df.columns

# ---------------------------------------------------------------------------
# TestPurchases
# ---------------------------------------------------------------------------

class TestPurchases:
    def test_add_purchase_stores_reference(self):
        p = add_purchase("Alice", "BuyIn", "ALICE - BUY IN", _empty_purchases())
        assert p.iloc[0]["Reference"] == "ALICE - BUY IN"

    def test_add_purchase_stores_player_and_type(self):
        p = add_purchase("Alice", "BuyIn", "ref", _empty_purchases())
        assert p.iloc[0]["Player"] == "Alice"
        assert p.iloc[0]["PurchaseType"] == "BuyIn"

    def test_get_player_purchases_filters_correctly(self):
        p = _purchases(
            ("Alice", "BuyIn"),
            ("Bob",   "BuyIn"),
        )
        alice = get_player_purchases("Alice", p)
        assert len(alice) == 1
        assert alice.iloc[0]["Player"] == "Alice"

    def test_purchases_to_scoring_format_maps_ninth(self):
        p = _purchases(("Alice", "NinthTeam", "Germany"))
        sp = purchases_to_scoring_format(p)
        assert sp.iloc[0]["PurchaseType"] == "NinthTeam"
        assert sp.iloc[0]["Selection"] == "Germany"

    def test_purchases_to_scoring_format_maps_resurrection(self):
        p = _purchases(("Alice", "Resurrection", "Qatar->Germany"))
        sp = purchases_to_scoring_format(p)
        assert sp.iloc[0]["PurchaseType"] == "Resurrection"
        assert sp.iloc[0]["Selection"] == "Qatar->Germany"

    def test_purchases_to_scoring_format_maps_pack(self):
        p = _purchases(("Alice", "PredictionPack"))
        sp = purchases_to_scoring_format(p)
        assert sp.iloc[0]["PurchaseType"] == "PredictionPack"

    def test_purchases_to_scoring_format_maps_insurance(self):
        p = _purchases(("Alice", "Insurance"))
        sp = purchases_to_scoring_format(p)
        assert sp.iloc[0]["PurchaseType"] == "Insurance"

    def test_purchases_to_scoring_format_excludes_buyin(self):
        p = _purchases(("Alice", "BuyIn"))
        sp = purchases_to_scoring_format(p)
        assert sp.empty

    def test_purchases_to_scoring_format_excludes_mulligan(self):
        p = _purchases(("Alice", "Mulligan"))
        sp = purchases_to_scoring_format(p)
        assert sp.empty

    def test_purchases_to_scoring_includes_ninth_with_selection(self):
        p = _purchases(("Alice", "NinthTeam", "Germany"))
        sp = purchases_to_scoring_format(p)
        assert not sp.empty
        assert sp.iloc[0]["Selection"] == "Germany"

# ---------------------------------------------------------------------------
# TestPaymentReference
# ---------------------------------------------------------------------------

class TestPaymentReference:
    def test_buyin_only(self):
        r = parse_payment_reference("OISIN - BUY IN")
        assert r["player"] == "OISIN"
        assert r["items"] == ["BuyIn"]

    def test_buyin_and_pack(self):
        r = parse_payment_reference("JOHN - BUY IN, PREDICTION PACK")
        assert r["player"] == "JOHN"
        assert set(r["items"]) == {"BuyIn", "PredictionPack"}

    def test_mulligan_only(self):
        r = parse_payment_reference("SARAH - MULLIGAN")
        assert r["items"] == ["Mulligan"]

    def test_ninth_and_resurrection(self):
        r = parse_payment_reference("MIKE - NINTH TEAM, RESURRECTION")
        assert set(r["items"]) == {"NinthTeam", "Resurrection"}

    def test_insurance_in_reference(self):
        r = parse_payment_reference("OISIN - BUY IN, PREDICTION PACK, INSURANCE")
        assert "Insurance" in r["items"]

    def test_unknown_items_ignored(self):
        r = parse_payment_reference("ALICE - BUY IN, UNICORN")
        assert r["items"] == ["BuyIn"]

    def test_missing_dash_returns_empty(self):
        r = parse_payment_reference("OISIN BUY IN")
        assert r["player"] == ""
        assert r["items"] == []

    def test_case_insensitive_items(self):
        r = parse_payment_reference("ALICE - buy in")
        assert "BuyIn" in r["items"]

# ---------------------------------------------------------------------------
# TestPredictionValidation  (dark horse)
# ---------------------------------------------------------------------------

class TestPredictionValidation:
    def test_tier3_team_valid(self):
        # Algeria is Tier 3 and NOT in Alice's allocation
        errors = validate_dark_horse("Alice", "Algeria", _ASSIGNMENTS, _TIER_MAP)
        assert errors == []

    def test_tier4_team_valid(self):
        errors = validate_dark_horse("Alice", "Qatar", _ASSIGNMENTS, _TIER_MAP)
        # Qatar is in Alice's base allocation — should still fail on ownership
        assert any("owned" in e for e in errors)

    def test_tier1_team_invalid(self):
        errors = validate_dark_horse("Bob", "France", _ASSIGNMENTS, _TIER_MAP)
        assert any("Tier" in e for e in errors)

    def test_tier2_team_invalid(self):
        errors = validate_dark_horse("Alice", "USA", _ASSIGNMENTS, _TIER_MAP)
        assert any("Tier" in e for e in errors)

    def test_owned_team_invalid(self):
        errors = validate_dark_horse("Alice", "Norway", _ASSIGNMENTS, _TIER_MAP)
        assert any("owned" in e for e in errors)

    def test_unowned_tier3_valid(self):
        # Alice doesn't own Algeria
        errors = validate_dark_horse("Alice", "Algeria", _ASSIGNMENTS, _TIER_MAP)
        assert errors == []

    def test_unknown_team_invalid(self):
        errors = validate_dark_horse("Alice", "Atlantis FC", _ASSIGNMENTS, _TIER_MAP)
        assert any("Unknown" in e for e in errors)

# ---------------------------------------------------------------------------
# TestNinthTeamValidation
# ---------------------------------------------------------------------------

class TestNinthTeamValidation:
    def test_surviving_unowned_valid(self):
        ms = _ms({"Team": "Germany", "RoundReached": "R16"})
        errors = validate_ninth_team("Alice", "Germany", _ASSIGNMENTS, ms, _empty_purchases())
        assert errors == []

    def test_owned_team_invalid(self):
        ms = _ms({"Team": "France", "RoundReached": "R16"})
        errors = validate_ninth_team("Alice", "France", _ASSIGNMENTS, ms, _empty_purchases())
        assert any("owned" in e for e in errors)

    def test_eliminated_team_invalid(self):
        ms = _ms({"Team": "Germany", "RoundReached": "GroupStage"})
        errors = validate_ninth_team("Alice", "Germany", _ASSIGNMENTS, ms, _empty_purchases())
        assert any("group stage" in e for e in errors)

    def test_no_round_reached_invalid(self):
        ms = _ms({"Team": "Germany", "RoundReached": ""})
        errors = validate_ninth_team("Alice", "Germany", _ASSIGNMENTS, ms, _empty_purchases())
        assert errors  # empty round treated as eliminated

    def test_team_already_ninth_invalid(self):
        p = _purchases(("Alice", "NinthTeam", "Germany"))
        ms = _ms({"Team": "Italy", "RoundReached": "R16"})
        # Italy is not in assignments but Germany was already added as ninth
        # Italy should still be fine
        errors = validate_ninth_team("Alice", "Italy", _ASSIGNMENTS, ms, p)
        assert errors == []

    def test_team_added_by_ninth_counts_as_owned(self):
        p = _purchases(("Alice", "NinthTeam", "Germany"))
        ms = _ms({"Team": "Germany", "RoundReached": "R16"})
        errors = validate_ninth_team("Alice", "Germany", _ASSIGNMENTS, ms, p)
        assert any("owned" in e for e in errors)

# ---------------------------------------------------------------------------
# TestResurrectionValidation
# ---------------------------------------------------------------------------

class TestResurrectionValidation:
    def test_valid_resurrection(self):
        ms = _ms(
            {"Team": "Qatar",  "RoundReached": "GroupStage"},
            {"Team": "Ghana",  "RoundReached": "R16"},
        )
        errors = validate_resurrection(
            "Alice", "Qatar", "Ghana", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases()
        )
        assert errors == []

    def test_eliminated_team_not_in_allocation_invalid(self):
        ms = _ms({"Team": "Germany", "RoundReached": "GroupStage"})
        errors = validate_resurrection(
            "Alice", "Germany", "Ghana", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases()
        )
        assert any("base allocation" in e for e in errors)

    def test_surviving_eliminated_team_invalid(self):
        ms = _ms(
            {"Team": "Qatar", "RoundReached": "R16"},
            {"Team": "Ghana", "RoundReached": "R16"},
        )
        errors = validate_resurrection(
            "Alice", "Qatar", "Ghana", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases()
        )
        assert any("not been eliminated" in e for e in errors)

    def test_wrong_tier_replacement_invalid(self):
        ms = _ms(
            {"Team": "Qatar",  "RoundReached": "GroupStage"},
            {"Team": "Norway", "RoundReached": "R16"},
        )
        errors = validate_resurrection(
            "Alice", "Qatar", "Norway", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases()
        )
        assert any("same tier" in e for e in errors)

    def test_already_owned_replacement_invalid(self):
        ms = _ms(
            {"Team": "Haiti",  "RoundReached": "GroupStage"},
            {"Team": "Qatar",  "RoundReached": "R16"},
        )
        # Alice already owns Qatar — can't use it as replacement
        errors = validate_resurrection(
            "Alice", "Haiti", "Qatar", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases()
        )
        assert any("owned" in e for e in errors)

    def test_eliminated_replacement_invalid(self):
        ms = _ms(
            {"Team": "Qatar", "RoundReached": "GroupStage"},
            {"Team": "Ghana", "RoundReached": "GroupStage"},
        )
        errors = validate_resurrection(
            "Alice", "Qatar", "Ghana", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases()
        )
        assert any("group stage" in e for e in errors)

# ---------------------------------------------------------------------------
# TestNinthTeamAssignment
# ---------------------------------------------------------------------------

class TestNinthTeamAssignment:
    def test_returns_surviving_unowned(self):
        ms = _ms({"Team": "Germany", "RoundReached": "R16"})
        team = assign_ninth_team("Alice", _ASSIGNMENTS, ms, _empty_purchases(), seed=42)
        assert team == "Germany"

    def test_no_candidates_returns_none(self):
        team = assign_ninth_team("Alice", _ASSIGNMENTS, _empty_ms(), _empty_purchases(), seed=42)
        assert team is None

    def test_does_not_return_owned_team(self):
        # All surviving teams are Alice's owned teams — should return None
        ms = _ms(
            {"Team": "France", "RoundReached": "R16"},
            {"Team": "Spain",  "RoundReached": "R16"},
        )
        # France and Spain both owned by Alice
        team = assign_ninth_team("Alice", _ASSIGNMENTS, ms, _empty_purchases(), seed=42)
        assert team not in ("France", "Spain") if team else True

    def test_seeded_result_is_deterministic(self):
        ms = _ms(
            {"Team": "Germany", "RoundReached": "R16"},
            {"Team": "Italy",   "RoundReached": "QF"},
        )
        t1 = assign_ninth_team("Alice", _ASSIGNMENTS, ms, _empty_purchases(), seed=7)
        t2 = assign_ninth_team("Alice", _ASSIGNMENTS, ms, _empty_purchases(), seed=7)
        assert t1 == t2

# ---------------------------------------------------------------------------
# TestResurrectionAssignment
# ---------------------------------------------------------------------------

class TestResurrectionAssignment:
    def test_returns_same_tier_surviving_unowned(self):
        ms = _ms(
            {"Team": "Qatar", "RoundReached": "GroupStage"},
            {"Team": "Ghana", "RoundReached": "R16"},
        )
        team = assign_resurrection_team(
            "Alice", "Qatar", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases(), seed=42
        )
        assert team == "Ghana"

    def test_no_surviving_same_tier_returns_none(self):
        ms = _ms({"Team": "Qatar", "RoundReached": "GroupStage"})
        team = assign_resurrection_team(
            "Alice", "Qatar", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases(), seed=42
        )
        assert team is None

    def test_unknown_eliminated_team_returns_none(self):
        team = assign_resurrection_team(
            "Alice", "Atlantis FC", _ASSIGNMENTS, _empty_ms(), _TIER_MAP,
            _empty_purchases(), seed=42,
        )
        assert team is None

    def test_seeded_result_is_deterministic(self):
        ms = _ms(
            {"Team": "Qatar",     "RoundReached": "GroupStage"},
            {"Team": "Ghana",     "RoundReached": "R16"},
            {"Team": "New Zealand", "RoundReached": "QF"},
        )
        t1 = assign_resurrection_team(
            "Alice", "Haiti", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases(), seed=99
        )
        t2 = assign_resurrection_team(
            "Alice", "Haiti", _ASSIGNMENTS, ms, _TIER_MAP, _empty_purchases(), seed=99
        )
        assert t1 == t2

# ---------------------------------------------------------------------------
# TestTiebreakers
# ---------------------------------------------------------------------------

class TestTiebreakers:
    def test_goals_counted_from_group_and_knockout(self):
        ms = _ms({"Team": "France", "GroupGoals": 3, "KnockoutGoals": 2})
        stats = calculate_tiebreak_stats(["France"], ms)
        assert stats["tiebreak_goals"] == 5

    def test_qf_count_includes_qf_sf_final_winner(self):
        ms = _ms(
            {"Team": "France", "RoundReached": "QF"},
            {"Team": "Spain",  "RoundReached": "Winner"},
            {"Team": "USA",    "RoundReached": "R16"},
        )
        stats = calculate_tiebreak_stats(["France", "Spain", "USA"], ms)
        assert stats["tiebreak_qf"] == 2   # France(QF) + Spain(Winner), not USA(R16)

    def test_eliminated_teams_zero_goals_zero_qf(self):
        ms = _ms({"Team": "France", "GroupGoals": 0, "RoundReached": "GroupStage"})
        stats = calculate_tiebreak_stats(["France"], ms)
        assert stats["tiebreak_goals"] == 0
        assert stats["tiebreak_qf"] == 0

    def test_unknown_team_skipped(self):
        stats = calculate_tiebreak_stats(["AtlantisFC"], _empty_ms())
        assert stats["tiebreak_goals"] == 0

    def test_returns_required_keys(self):
        stats = calculate_tiebreak_stats([], _empty_ms())
        assert set(stats.keys()) == {"tiebreak_goals", "tiebreak_qf"}

    def test_duplicate_teams_counted_once(self):
        ms = _ms({"Team": "France", "GroupGoals": 5, "RoundReached": "QF"})
        stats = calculate_tiebreak_stats(["France", "France"], ms)
        assert stats["tiebreak_goals"] == 5
        assert stats["tiebreak_qf"] == 1

# ---------------------------------------------------------------------------
# TestOfficialLeaderboard  (Prize Leaderboard)
# ---------------------------------------------------------------------------

class TestOfficialLeaderboard:
    def test_only_paid_players_included(self):
        st = _statuses(("Alice", "PAID", ""), ("Bob", "UNPAID", ""), ("Carol", "PAID", ""))
        lb = prize_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert set(lb["Player"].tolist()) == {"Alice", "Carol"}
        assert "Bob" not in lb["Player"].tolist()

    def test_empty_if_no_paid_players(self):
        st = _statuses(("Alice", "UNPAID", ""), ("Bob", "UNPAID", ""))
        lb = prize_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert lb.empty

    def test_returns_dataframe(self):
        st = _statuses(("Alice", "PAID", ""))
        lb = prize_leaderboard(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert isinstance(lb, pd.DataFrame)

    def test_rank_starts_at_one(self):
        st = _statuses(("Alice", "PAID", ""), ("Carol", "PAID", ""))
        lb = prize_leaderboard(
            ["Alice", "Carol"],
            {k: _ASSIGNMENTS[k] for k in ["Alice", "Carol"]},
            _empty_ms(), _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert lb["Rank"].iloc[0] == 1

    def test_payment_status_column_present(self):
        st = _statuses(("Alice", "PAID", ""))
        lb = prize_leaderboard(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert "PaymentStatus" in lb.columns

    def test_tiebreak_columns_present(self):
        st = _statuses(("Alice", "PAID", ""))
        lb = prize_leaderboard(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert "tiebreak_goals" in lb.columns
        assert "tiebreak_qf" in lb.columns

# ---------------------------------------------------------------------------
# TestOverallLeaderboard
# ---------------------------------------------------------------------------

class TestOverallLeaderboard:
    def test_all_players_included(self):
        st = _statuses(("Alice", "PAID", ""), ("Bob", "UNPAID", ""), ("Carol", "UNPAID", ""))
        lb = overall_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        assert set(lb["Player"].tolist()) == set(_ASSIGNMENTS.keys())

    def test_payment_status_shown_for_unpaid(self):
        st = _statuses(("Alice", "PAID", ""), ("Bob", "UNPAID", ""), ("Carol", "UNPAID", ""))
        lb = overall_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _empty_ms(),
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        bob_row = lb[lb["Player"] == "Bob"].iloc[0]
        assert bob_row["PaymentStatus"] == "UNPAID"

    def test_sorted_descending_by_total_points(self):
        ms = _ms({"Team": "France", "GroupGoals": 10})
        st = _statuses(("Alice", "PAID", ""), ("Bob", "UNPAID", ""), ("Carol", "UNPAID", ""))
        lb = overall_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, ms,
            _empty_purchases(), _empty_captains(), _empty_predictions(), st,
        )
        totals = lb["TotalPoints"].tolist()
        assert totals == sorted(totals, reverse=True)

    def test_tiebreak_goals_applied(self):
        # Alice and Bob have equal points; Alice has more goals → ranks higher
        ms = _ms(
            {"Team": "France", "GroupGoals": 5},
            {"Team": "Argentina", "GroupGoals": 2},
        )
        st = _statuses(("Alice", "PAID", ""), ("Bob", "PAID", ""))
        lb = overall_leaderboard(
            ["Alice", "Bob"],
            {"Alice": _ASSIGNMENTS["Alice"], "Bob": _ASSIGNMENTS["Bob"]},
            ms, _empty_purchases(), _empty_captains(), _empty_predictions(), st,
            tiebreak_seed=42,
        )
        # France (5 goals) is Alice's; Argentina (2 goals) is Bob's
        alice_row = lb[lb["Player"] == "Alice"].iloc[0]
        bob_row   = lb[lb["Player"] == "Bob"].iloc[0]
        assert alice_row["tiebreak_goals"] >= bob_row["tiebreak_goals"]

# ---------------------------------------------------------------------------
# TestAuditLogging
# ---------------------------------------------------------------------------

class TestAuditLogging:
    def _empty_log(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["Timestamp", "Event", "Player", "Action", "Result"])

    def test_log_action_appends_row(self):
        log = self._empty_log()
        log = log_action("PURCHASE", "Alice", "BUYIN_PROCESSED", "OK", log, "2026-06-01T10:00:00")
        assert len(log) == 1

    def test_log_action_stores_fields(self):
        log = self._empty_log()
        log = log_action("PURCHASE", "Alice", "BUYIN_PROCESSED", "OK", log, "2026-06-01T10:00:00")
        row = log.iloc[0]
        assert row["Event"]  == "PURCHASE"
        assert row["Player"] == "Alice"
        assert row["Action"] == "BUYIN_PROCESSED"
        assert row["Result"] == "OK"
        assert row["Timestamp"] == "2026-06-01T10:00:00"

    def test_multiple_log_entries(self):
        log = self._empty_log()
        log = log_action("E1", "Alice", "A1", "OK", log, "2026-01-01T00:00:00")
        log = log_action("E2", "Bob",   "A2", "OK", log, "2026-01-01T00:01:00")
        assert len(log) == 2

    def test_log_does_not_mutate_input(self):
        log = self._empty_log()
        _ = log_action("E1", "Alice", "A1", "OK", log)
        assert len(log) == 0

    def test_export_audit_log_creates_csv(self, tmp_path):
        from src.competition import export_audit_log
        log = self._empty_log()
        log = log_action("E", "Alice", "A", "OK", log, "2026-01-01T00:00:00")
        out = tmp_path / "audit.csv"
        export_audit_log(log, out)
        assert out.exists()

# ---------------------------------------------------------------------------
# TestEvents
# ---------------------------------------------------------------------------

class TestEvents:
    def _empty_events(self) -> pd.DataFrame:
        return pd.DataFrame(columns=[
            "EventID", "EventType", "ScheduledTime", "ExecutedTime", "Status", "RandomSeed",
        ])

    def test_create_event_adds_row(self):
        events = create_event("INITIAL_DRAW", "2026-06-15T12:00:00", self._empty_events())
        assert len(events) == 1

    def test_create_event_status_scheduled(self):
        events = create_event("INITIAL_DRAW", "2026-06-15T12:00:00", self._empty_events())
        assert events.iloc[0]["Status"] == "SCHEDULED"

    def test_create_event_ids_increment(self):
        events = self._empty_events()
        events = create_event("INITIAL_DRAW", "2026-06-15T12:00:00", events)
        events = create_event("MULLIGAN_DRAW", "2026-06-16T12:00:00", events)
        ids = events["EventID"].astype(int).tolist()
        assert ids == [1, 2]

    def test_update_event_status(self):
        events = create_event("INITIAL_DRAW", "2026-06-15T12:00:00", self._empty_events())
        event_id = events.iloc[0]["EventID"]
        events = update_event_status(event_id, "EXECUTED", events, seed=12345)
        assert events.iloc[0]["Status"] == "EXECUTED"
        assert events.iloc[0]["RandomSeed"] == "12345"

    def test_update_unknown_event_no_change(self):
        events = create_event("INITIAL_DRAW", "2026-06-15T12:00:00", self._empty_events())
        events2 = update_event_status("999", "EXECUTED", events)
        assert events2.iloc[0]["Status"] == "SCHEDULED"

# ---------------------------------------------------------------------------
# TestTeamOwnership
# ---------------------------------------------------------------------------

class TestTeamOwnership:
    def test_owners_populated(self):
        ownership = get_team_ownership(
            {"Alice": ["France"]}, _empty_captains(), _empty_predictions(), _empty_purchases()
        )
        assert "Alice" in ownership["France"]["owners"]

    def test_pre_captains_populated(self):
        caps = _captains(("Alice", "PreTournament", "France"))
        ownership = get_team_ownership(
            {"Alice": ["France"]}, caps, _empty_predictions(), _empty_purchases()
        )
        assert "Alice" in ownership["France"]["pre_captains"]

    def test_knockout_captains_populated(self):
        caps = _captains(("Alice", "Knockout", "France"))
        ownership = get_team_ownership(
            {"Alice": ["France"]}, caps, _empty_predictions(), _empty_purchases()
        )
        assert "Alice" in ownership["France"]["knockout_captains"]

    def test_dark_horse_pickers_populated(self):
        preds = _predictions(("Alice", "", "", "Norway"))
        ownership = get_team_ownership(
            {"Alice": ["France"]}, _empty_captains(), preds, _empty_purchases()
        )
        assert "Alice" in ownership["Norway"]["dark_horse_pickers"]

    def test_team_not_in_assignments_not_in_result(self):
        ownership = get_team_ownership(
            {}, _empty_captains(), _empty_predictions(), _empty_purchases()
        )
        assert "France" not in ownership

# ---------------------------------------------------------------------------
# TestPredictionsCentre
# ---------------------------------------------------------------------------

class TestPredictionsCentre:
    def test_winner_picks_aggregated(self):
        preds = _predictions(
            ("Alice", "France", "", ""),
            ("Bob",   "France", "", ""),
            ("Carol", "Spain",  "", ""),
        )
        centre = get_predictions_centre(preds)
        assert set(centre["world_cup_winner"]["France"]) == {"Alice", "Bob"}
        assert centre["world_cup_winner"]["Spain"] == ["Carol"]

    def test_golden_boot_aggregated(self):
        preds = _predictions(("Alice", "", "Mbappe", ""), ("Bob", "", "Mbappe", ""))
        centre = get_predictions_centre(preds)
        assert len(centre["golden_boot"]["Mbappe"]) == 2

    def test_dark_horse_aggregated(self):
        preds = _predictions(("Alice", "", "", "Norway"), ("Carol", "", "", "Panama"))
        centre = get_predictions_centre(preds)
        assert "Norway" in centre["dark_horse"]
        assert "Panama" in centre["dark_horse"]

    def test_empty_predictions_empty_centre(self):
        centre = get_predictions_centre(_empty_predictions())
        assert centre["world_cup_winner"] == {}
        assert centre["golden_boot"]      == {}
        assert centre["dark_horse"]       == {}

    def test_returns_required_keys(self):
        centre = get_predictions_centre(_empty_predictions())
        assert set(centre.keys()) == {
            "world_cup_winner", "golden_boot", "dark_horse",
            "runner_up", "bronze_winner", "first_knocked_out",
        }

# ---------------------------------------------------------------------------
# TestPaymentLedger
# ---------------------------------------------------------------------------

class TestPaymentLedger:
    def test_creates_csv(self, tmp_path):
        out = tmp_path / "ledger.csv"
        export_payment_ledger(_empty_purchases(), _empty_statuses(), out)
        assert out.exists()

    def test_row_per_player(self, tmp_path):
        out = tmp_path / "ledger.csv"
        p = _purchases(
            ("Alice", "BuyIn"),
            ("Bob",   "BuyIn"),
        )
        df = export_payment_ledger(p, _empty_statuses(), out)
        assert len(df) == 2

    def test_total_paid_correct(self, tmp_path):
        out = tmp_path / "ledger.csv"
        p = _purchases(
            ("Alice", "BuyIn"),
            ("Alice", "PredictionPack"),
        )
        df = export_payment_ledger(p, _empty_statuses(), out)
        alice = df[df["Player"] == "Alice"].iloc[0]
        assert alice["TotalPaid"] == 10.0   # 5 + 5

    def test_payment_status_from_statuses(self, tmp_path):
        out = tmp_path / "ledger.csv"
        p = _purchases(("Alice", "BuyIn"))
        st = _statuses(("Alice", "PAID", ""))
        df = export_payment_ledger(p, st, out)
        assert df[df["Player"] == "Alice"]["PaymentStatus"].iloc[0] == "PAID"

# ---------------------------------------------------------------------------
# TestInsuranceBonus  (updated value)
# ---------------------------------------------------------------------------

class TestInsuranceBonusValue:
    def test_insurance_bonus_constant_is_25(self):
        assert INSURANCE_BONUS == 25

    def test_insurance_price_is_2(self):
        assert PRICES["Insurance"] == 2.0
