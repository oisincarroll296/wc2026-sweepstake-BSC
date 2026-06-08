"""Unit tests for src/scoring_engine.py."""

import pytest
import pandas as pd

from src.scoring_engine import (
    calculate_team_points,
    calculate_captain_bonus,
    calculate_insurance_bonus,
    calculate_prediction_points,
    calculate_player_points,
    calculate_leaderboard,
    get_effective_teams,
    validate_captains,
    validate_purchases,
    generate_player_summary,
    PROGRESSION_BONUSES,
    DARK_HORSE_BONUSES,
    INSURANCE_BONUS,
    PREDICTION_WINNER_BONUS,
    PREDICTION_GOLDEN_BOOT_BONUS,
)

# ---------------------------------------------------------------------------
# Test-data helpers
# ---------------------------------------------------------------------------

def _ms(*rows) -> pd.DataFrame:
    """Build a match_stats DataFrame from keyword-dict rows."""
    defaults = {
        "Team": "X", "GroupGoals": 0, "GroupCleanSheets": 0,
        "GroupPenaltyWins": 0, "GroupComebackWins": 0, "GroupWinner": 0,
        "KnockoutGoals": 0, "KnockoutCleanSheets": 0, "KnockoutPenaltyWins": 0,
        "KnockoutComebackWins": 0, "RoundReached": "GroupStage",
    }
    records = []
    for row in rows:
        r = dict(defaults)
        r.update(row)
        records.append(r)
    return pd.DataFrame(records)


def _purchases(*rows) -> pd.DataFrame:
    """Build purchases DataFrame from (Player, PurchaseType, Selection, Timestamp) tuples."""
    if not rows:
        return pd.DataFrame(columns=["Player", "PurchaseType", "Selection", "Timestamp"])
    return pd.DataFrame(rows, columns=["Player", "PurchaseType", "Selection", "Timestamp"])


def _predictions(*rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])
    return pd.DataFrame(rows, columns=["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])


def _captains(*rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["Player", "CaptainType", "Team"])
    return pd.DataFrame(rows, columns=["Player", "CaptainType", "Team"])


# Minimal tier map for unit tests — avoids loading the real CSV
_TIER_MAP: dict[str, int] = {
    "France":    1, "Spain":   1, "Argentina": 1, "England": 1,
    "Colombia":  1, "Morocco": 1,
    "USA":       2, "Mexico":  2, "Japan":     2,
    "Norway":    3, "Panama":  3, "Scotland":  3,
    "Qatar":     4, "Haiti":   4, "NewZealand": 4,
}

# Standard assignment for 3-player tests
_ASSIGNMENTS: dict[str, list[str]] = {
    "Alice": ["France", "Spain", "USA", "Mexico", "Norway", "Panama", "Qatar", "Haiti"],
    "Bob":   ["Argentina", "England", "Japan", "Mexico", "Scotland", "Norway", "Qatar", "NewZealand"],
    "Carol": ["Colombia", "Morocco", "USA", "Japan", "Panama", "Scotland", "Haiti", "NewZealand"],
}

_EMPTY_PURCHASES  = _purchases()
_EMPTY_PREDICTIONS = _predictions()
_EMPTY_CAPTAINS   = _captains()
_EMPTY_MS         = pd.DataFrame(columns=[
    "Team", "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins",
    "GroupComebackWins", "GroupWinner", "KnockoutGoals",
    "KnockoutCleanSheets", "KnockoutPenaltyWins", "KnockoutComebackWins",
    "RoundReached",
])

# ---------------------------------------------------------------------------
# TestCalculateTeamPoints
# ---------------------------------------------------------------------------

class TestCalculateTeamPoints:
    def test_no_stats_returns_zeros(self):
        result = calculate_team_points("France", _EMPTY_MS, 1)
        assert result["total"] == 0.0
        assert result["group_stage"] == 0.0
        assert result["knockout"] == 0.0

    def test_team_not_in_stats_returns_zeros(self):
        ms = _ms({"Team": "Spain", "GroupGoals": 3})
        result = calculate_team_points("France", ms, 1)
        assert result["total"] == 0.0

    def test_group_goal_worth_1(self):
        ms = _ms({"Team": "France", "GroupGoals": 3})
        assert calculate_team_points("France", ms, 1)["group_stage"] == 3.0

    def test_group_clean_sheet_worth_2(self):
        ms = _ms({"Team": "France", "GroupCleanSheets": 2})
        assert calculate_team_points("France", ms, 1)["group_stage"] == 4.0

    def test_group_penalty_win_worth_3(self):
        ms = _ms({"Team": "France", "GroupPenaltyWins": 1})
        assert calculate_team_points("France", ms, 1)["group_stage"] == 3.0

    def test_group_comeback_win_worth_3(self):
        ms = _ms({"Team": "France", "GroupComebackWins": 2})
        assert calculate_team_points("France", ms, 1)["group_stage"] == 6.0

    def test_group_winner_worth_3(self):
        ms = _ms({"Team": "France", "GroupWinner": 1})
        assert calculate_team_points("France", ms, 1)["group_stage"] == 3.0

    def test_knockout_goal_worth_1(self):
        ms = _ms({"Team": "France", "KnockoutGoals": 5, "RoundReached": "R16"})
        result = calculate_team_points("France", ms, 1)
        assert result["knockout"] >= 5.0

    def test_knockout_clean_sheet_worth_2(self):
        ms = _ms({"Team": "France", "KnockoutCleanSheets": 2, "RoundReached": "R16"})
        result = calculate_team_points("France", ms, 1)
        assert result["knockout"] >= 4.0

    def test_progression_t1_r16(self):
        ms = _ms({"Team": "France", "RoundReached": "R16"})
        result = calculate_team_points("France", ms, 1)
        assert result["knockout"] == 2.0

    def test_progression_t1_qf_cumulative(self):
        ms = _ms({"Team": "France", "RoundReached": "QF"})
        result = calculate_team_points("France", ms, 1)
        # R16=2 + QF=4 = 6
        assert result["knockout"] == 6.0

    def test_progression_t1_sf(self):
        ms = _ms({"Team": "France", "RoundReached": "SF"})
        result = calculate_team_points("France", ms, 1)
        # R16=2 + QF=4 + SF=8 = 14
        assert result["knockout"] == 14.0

    def test_progression_t1_final(self):
        ms = _ms({"Team": "France", "RoundReached": "Final"})
        result = calculate_team_points("France", ms, 1)
        # 2+4+8+12 = 26
        assert result["knockout"] == 26.0

    def test_progression_t1_winner(self):
        ms = _ms({"Team": "France", "RoundReached": "Winner"})
        result = calculate_team_points("France", ms, 1)
        # 2+4+8+12+20 = 46
        assert result["knockout"] == 46.0

    def test_progression_t2_r16(self):
        ms = _ms({"Team": "USA", "RoundReached": "R16"})
        assert calculate_team_points("USA", ms, 2)["knockout"] == 4.0

    def test_progression_t3_winner(self):
        ms = _ms({"Team": "Norway", "RoundReached": "Winner"})
        result = calculate_team_points("Norway", ms, 3)
        # 8+15+20+32+46 = 121
        assert result["knockout"] == 121.0

    def test_progression_t4_winner(self):
        ms = _ms({"Team": "Qatar", "RoundReached": "Winner"})
        result = calculate_team_points("Qatar", ms, 4)
        # 12+25+30+45+65 = 177
        assert result["knockout"] == 177.0

    def test_group_stage_only_no_progression(self):
        ms = _ms({"Team": "France", "GroupGoals": 2, "RoundReached": "GroupStage"})
        result = calculate_team_points("France", ms, 1)
        assert result["knockout"] == 0.0
        assert result["group_stage"] == 2.0

    def test_empty_round_reached_no_progression(self):
        ms = _ms({"Team": "France", "GroupGoals": 1, "RoundReached": ""})
        result = calculate_team_points("France", ms, 1)
        assert result["knockout"] == 0.0

    def test_combined_full_scenario(self):
        # France: 3 GS goals, 1 GS clean sheet, group winner, reaches SF
        # 2 KO goals, 1 KO clean sheet
        ms = _ms({
            "Team": "France",
            "GroupGoals": 3, "GroupCleanSheets": 1, "GroupWinner": 1,
            "KnockoutGoals": 2, "KnockoutCleanSheets": 1,
            "RoundReached": "SF",
        })
        result = calculate_team_points("France", ms, 1)
        # GS: 3*1 + 1*2 + 3 = 8
        assert result["group_stage"] == 8.0
        # KO: 2*1 + 1*2 + 14(R16+QF+SF) = 18
        assert result["knockout"] == 18.0
        assert result["total"] == 26.0

    def test_breakdown_has_correct_keys(self):
        ms = _ms({
            "Team": "France",
            "GroupGoals": 1, "GroupCleanSheets": 1, "GroupWinner": 1,
            "KnockoutGoals": 1, "RoundReached": "R16",
        })
        result = calculate_team_points("France", ms, 1)
        bd = result["breakdown"]
        assert "GroupGoals" in bd
        assert "GroupCleanSheets" in bd
        assert "GroupWinner" in bd
        assert "KnockoutGoals" in bd
        assert "Progression_R16" in bd

    def test_returns_dict_with_required_keys(self):
        result = calculate_team_points("X", _EMPTY_MS, 1)
        assert set(result.keys()) == {"group_stage", "knockout", "total", "breakdown"}

# ---------------------------------------------------------------------------
# TestGetEffectiveTeams
# ---------------------------------------------------------------------------

class TestGetEffectiveTeams:
    def test_no_purchases_base_only(self):
        eff = get_effective_teams("Alice", _ASSIGNMENTS, _EMPTY_PURCHASES)
        assert eff["group_stage"] == _ASSIGNMENTS["Alice"]
        assert eff["knockout"]    == _ASSIGNMENTS["Alice"]

    def test_ninth_team_added_to_knockout_only(self):
        purchases = _purchases(("Alice", "NinthTeam", "Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert "Germany" in eff["knockout"]
        assert "Germany" not in eff["group_stage"]

    def test_ninth_team_increases_knockout_count_to_9(self):
        purchases = _purchases(("Alice", "NinthTeam", "Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert len(eff["knockout"]) == 9
        assert len(eff["group_stage"]) == 8

    def test_resurrection_replaces_in_knockout_only(self):
        purchases = _purchases(("Alice", "Resurrection", "Qatar->Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert "Qatar" not in eff["knockout"]
        assert "Germany" in eff["knockout"]
        assert "Qatar" in eff["group_stage"]   # group stage unchanged

    def test_resurrection_keeps_count_at_8(self):
        purchases = _purchases(("Alice", "Resurrection", "Haiti->Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert len(eff["knockout"]) == 8

    def test_unknown_player_returns_empty(self):
        eff = get_effective_teams("Nobody", _ASSIGNMENTS, _EMPTY_PURCHASES)
        assert eff["group_stage"] == []
        assert eff["knockout"]    == []

    def test_both_ninth_and_resurrection(self):
        purchases = _purchases(
            ("Alice", "NinthTeam", "Germany", ""),
            ("Alice", "Resurrection", "Qatar->Italy", ""),
        )
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert len(eff["knockout"]) == 9
        assert "Germany" in eff["knockout"]
        assert "Italy" in eff["knockout"]
        assert "Qatar" not in eff["knockout"]
        assert "Qatar" in eff["group_stage"]

# ---------------------------------------------------------------------------
# TestCalculateCaptainBonus
# ---------------------------------------------------------------------------

class TestCalculateCaptainBonus:
    def _team_pts(self, gs: float, ko: float) -> dict:
        return {"group_stage": gs, "knockout": ko, "total": gs + ko, "breakdown": {}}

    def test_no_captains_zero_bonus(self):
        eff = {"group_stage": ["France"], "knockout": ["France"]}
        result = calculate_captain_bonus("Alice", {}, _EMPTY_CAPTAINS, eff)
        assert result["total"] == 0.0

    def test_pre_tournament_captain_half_total(self):
        # France earns 20 total (8 GS + 12 KO)
        team_pts = {"France": self._team_pts(8.0, 12.0)}
        caps = _captains(("Alice", "PreTournament", "France"))
        eff = {"group_stage": ["France"], "knockout": ["France"]}
        result = calculate_captain_bonus("Alice", team_pts, caps, eff)
        assert result["pre_tournament_bonus"] == pytest.approx(10.0)  # 0.5 * 20
        assert result["pre_tournament_captain"] == "France"

    def test_knockout_captain_half_knockout_only(self):
        # Spain earns 5 GS + 15 KO = 20 total
        team_pts = {"Spain": self._team_pts(5.0, 15.0)}
        caps = _captains(("Alice", "Knockout", "Spain"))
        eff = {"group_stage": ["Spain"], "knockout": ["Spain"]}
        result = calculate_captain_bonus("Alice", team_pts, caps, eff)
        assert result["knockout_bonus"] == pytest.approx(7.5)   # 0.5 * 15
        assert result["knockout_captain"] == "Spain"

    def test_both_captains_different_teams(self):
        team_pts = {
            "France": self._team_pts(8.0, 12.0),
            "Spain":  self._team_pts(5.0, 15.0),
        }
        caps = _captains(
            ("Alice", "PreTournament", "France"),
            ("Alice", "Knockout", "Spain"),
        )
        eff = {"group_stage": ["France", "Spain"], "knockout": ["France", "Spain"]}
        result = calculate_captain_bonus("Alice", team_pts, caps, eff)
        # PreTournament: 0.5 * 20 = 10
        # Knockout: 0.5 * 15 = 7.5
        assert result["total"] == pytest.approx(17.5)

    def test_captain_not_in_roster_gives_zero(self):
        team_pts = {"Germany": self._team_pts(10.0, 10.0)}
        caps = _captains(("Alice", "PreTournament", "Germany"))
        eff = {"group_stage": ["France"], "knockout": ["France"]}  # Germany not owned
        result = calculate_captain_bonus("Alice", team_pts, caps, eff)
        assert result["pre_tournament_bonus"] == 0.0

    def test_zero_team_points_zero_bonus(self):
        team_pts = {"France": self._team_pts(0.0, 0.0)}
        caps = _captains(("Alice", "PreTournament", "France"))
        eff = {"group_stage": ["France"], "knockout": ["France"]}
        result = calculate_captain_bonus("Alice", team_pts, caps, eff)
        assert result["total"] == 0.0

    def test_ninth_team_can_be_knockout_captain(self):
        # Germany is the ninth team — only in knockout roster
        team_pts = {"Germany": self._team_pts(0.0, 20.0)}
        caps = _captains(("Alice", "Knockout", "Germany"))
        eff = {
            "group_stage": ["France", "Spain"],
            "knockout": ["France", "Spain", "Germany"],
        }
        result = calculate_captain_bonus("Alice", team_pts, caps, eff)
        assert result["knockout_bonus"] == pytest.approx(10.0)  # 0.5 * 20

    def test_result_keys_present(self):
        eff = {"group_stage": [], "knockout": []}
        result = calculate_captain_bonus("Alice", {}, _EMPTY_CAPTAINS, eff)
        expected_keys = {
            "pre_tournament_captain", "pre_tournament_bonus",
            "knockout_captain", "knockout_bonus", "total",
        }
        assert set(result.keys()) == expected_keys

# ---------------------------------------------------------------------------
# TestCalculateInsuranceBonus
# ---------------------------------------------------------------------------

class TestCalculateInsuranceBonus:
    def test_no_purchase_no_bonus(self):
        ms = _ms({"Team": "France", "RoundReached": "GroupStage"})
        assert calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, ms, _EMPTY_PURCHASES, _TIER_MAP
        ) == 0.0

    def test_has_insurance_t1_eliminated_gives_25(self):
        purchases = _purchases(("Alice", "Insurance", "", ""))
        # France (T1) eliminated in group stage → +25
        ms = _ms({"Team": "France", "RoundReached": "GroupStage"})
        result = calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, ms, purchases, _TIER_MAP
        )
        assert result == float(INSURANCE_BONUS)  # 25

    def test_has_insurance_t1_advances_no_bonus(self):
        purchases = _purchases(("Alice", "Insurance", "", ""))
        ms = _ms({"Team": "France", "RoundReached": "R16"})
        assert calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, ms, purchases, _TIER_MAP
        ) == 0.0

    def test_both_t1_eliminated_gives_double_bonus(self):
        purchases = _purchases(("Alice", "Insurance", "", ""))
        # Alice's T1 teams: France and Spain — both eliminated → +50
        ms = _ms(
            {"Team": "France", "RoundReached": "GroupStage"},
            {"Team": "Spain",  "RoundReached": "GroupStage"},
        )
        result = calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, ms, purchases, _TIER_MAP
        )
        assert result == float(INSURANCE_BONUS * 2)  # 50

    def test_no_insurance_t1_eliminated_still_zero(self):
        # different player — no insurance purchase
        ms = _ms({"Team": "France", "RoundReached": "GroupStage"})
        assert calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, ms, _EMPTY_PURCHASES, _TIER_MAP
        ) == 0.0

    def test_insurance_with_no_match_stats_no_bonus(self):
        purchases = _purchases(("Alice", "Insurance", "", ""))
        assert calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, _EMPTY_MS, purchases, _TIER_MAP
        ) == 0.0

    def test_t2_team_elimination_no_insurance_bonus(self):
        purchases = _purchases(("Alice", "Insurance", "", ""))
        # USA is T2 — insurance only covers T1 failures
        ms = _ms({"Team": "USA", "RoundReached": "GroupStage"})
        assert calculate_insurance_bonus(
            "Alice", _ASSIGNMENTS, ms, purchases, _TIER_MAP
        ) == 0.0

# ---------------------------------------------------------------------------
# TestCalculatePredictionPoints
# ---------------------------------------------------------------------------

class TestCalculatePredictionPoints:
    def test_correct_winner_30_pts(self):
        preds = _predictions(("Alice", "France", "", ""))
        results = {"world_cup_winner": "France", "golden_boot_winner": "", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["winner_bonus"] == float(PREDICTION_WINNER_BONUS)
        assert result["total"] == float(PREDICTION_WINNER_BONUS)

    def test_wrong_winner_zero_pts(self):
        preds = _predictions(("Alice", "Spain", "", ""))
        results = {"world_cup_winner": "France", "golden_boot_winner": "", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["winner_bonus"] == 0.0

    def test_correct_golden_boot_25_pts(self):
        preds = _predictions(("Alice", "", "Erling Haaland", ""))
        results = {"world_cup_winner": "", "golden_boot_winner": "Erling Haaland", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["golden_boot_bonus"] == float(PREDICTION_GOLDEN_BOOT_BONUS)

    def test_wrong_golden_boot_zero_pts(self):
        preds = _predictions(("Alice", "", "Messi", ""))
        results = {"world_cup_winner": "", "golden_boot_winner": "Mbappe", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["golden_boot_bonus"] == 0.0

    def test_dark_horse_reaches_qf_15_pts(self):
        preds = _predictions(("Alice", "", "", "Panama"))
        results = {"world_cup_winner": "", "golden_boot_winner": "", "dark_horse_rounds": {"Panama": "QF"}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["dark_horse_bonus"] == 15.0

    def test_dark_horse_reaches_sf_cumulative(self):
        preds = _predictions(("Alice", "", "", "Panama"))
        results = {"world_cup_winner": "", "golden_boot_winner": "", "dark_horse_rounds": {"Panama": "SF"}}
        result = calculate_prediction_points("Alice", preds, results)
        # QF=15 + SF=30 = 45
        assert result["dark_horse_bonus"] == 45.0

    def test_dark_horse_reaches_final(self):
        preds = _predictions(("Alice", "", "", "Panama"))
        results = {"world_cup_winner": "", "golden_boot_winner": "", "dark_horse_rounds": {"Panama": "Final"}}
        result = calculate_prediction_points("Alice", preds, results)
        # 15+30+40 = 85
        assert result["dark_horse_bonus"] == 85.0

    def test_dark_horse_wins_tournament(self):
        preds = _predictions(("Alice", "", "", "Panama"))
        results = {"world_cup_winner": "", "golden_boot_winner": "", "dark_horse_rounds": {"Panama": "Winner"}}
        result = calculate_prediction_points("Alice", preds, results)
        # 15+30+40+50 = 135
        assert result["dark_horse_bonus"] == 135.0

    def test_dark_horse_eliminated_groups_zero(self):
        preds = _predictions(("Alice", "", "", "Panama"))
        results = {"world_cup_winner": "", "golden_boot_winner": "", "dark_horse_rounds": {"Panama": "GroupStage"}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["dark_horse_bonus"] == 0.0

    def test_dark_horse_not_in_rounds_map_zero(self):
        preds = _predictions(("Alice", "", "", "Panama"))
        results = {"world_cup_winner": "", "golden_boot_winner": "", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["dark_horse_bonus"] == 0.0

    def test_all_correct_adds_up(self):
        preds = _predictions(("Alice", "France", "Mbappe", "Panama"))
        results = {
            "world_cup_winner": "France",
            "golden_boot_winner": "Mbappe",
            "dark_horse_rounds": {"Panama": "SF"},
        }
        result = calculate_prediction_points("Alice", preds, results)
        # 30 + 25 + 45 = 100
        assert result["total"] == 100.0

    def test_player_not_in_predictions_zero(self):
        preds = _predictions(("Bob", "France", "", ""))
        results = {"world_cup_winner": "France", "golden_boot_winner": "", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", preds, results)
        assert result["total"] == 0.0

    def test_empty_predictions_zero(self):
        results = {"world_cup_winner": "France", "golden_boot_winner": "", "dark_horse_rounds": {}}
        result = calculate_prediction_points("Alice", _EMPTY_PREDICTIONS, results)
        assert result["total"] == 0.0

    def test_no_tournament_results_zero(self):
        preds = _predictions(("Alice", "France", "", ""))
        result = calculate_prediction_points("Alice", preds, {})
        assert result["total"] == 0.0

    def test_result_keys_present(self):
        result = calculate_prediction_points("Alice", _EMPTY_PREDICTIONS, {})
        expected = {
            "world_cup_winner", "golden_boot", "dark_horse",
            "winner_bonus", "golden_boot_bonus", "dark_horse_bonus", "total",
        }
        assert set(result.keys()) == expected

# ---------------------------------------------------------------------------
# TestNinthTeam
# ---------------------------------------------------------------------------

class TestNinthTeam:
    def test_ninth_team_in_knockout_roster(self):
        purchases = _purchases(("Alice", "NinthTeam", "Germany", ""))
        ms = _ms(
            {"Team": "Germany", "KnockoutGoals": 4, "RoundReached": "SF"},
        )
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map={**_TIER_MAP, "Germany": 1},
        )
        assert "Germany" in result["knockout_teams"]

    def test_ninth_team_knockout_points_count(self):
        purchases = _purchases(("Alice", "NinthTeam", "Germany", ""))
        # Germany: 4 KO goals + R16 progression
        ms = _ms({"Team": "Germany", "KnockoutGoals": 4, "RoundReached": "R16"})
        tm = {**_TIER_MAP, "Germany": 1}
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map=tm,
        )
        # 4 goals * 1 + R16 T1 = 4 + 2 = 6
        germany_pts = result["team_points"]["Germany"]
        assert germany_pts["knockout"] == 6.0

    def test_ninth_team_group_stage_not_counted(self):
        purchases = _purchases(("Alice", "NinthTeam", "Germany", ""))
        ms = _ms({"Team": "Germany", "GroupGoals": 5, "RoundReached": "GroupStage"})
        tm = {**_TIER_MAP, "Germany": 1}
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map=tm,
        )
        # Germany only in knockout roster — group stage points not included in gs_total
        assert "Germany" not in result["group_stage_teams"]
        germany_pts = result["team_points"].get("Germany", {})
        # group_stage computed, but not summed into player's gs_total
        assert "Germany" in result["knockout_teams"]

    def test_base_8_teams_without_purchase(self):
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, _EMPTY_MS, _EMPTY_PURCHASES,
            _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
        )
        assert len(result["group_stage_teams"]) == 8
        assert len(result["knockout_teams"]) == 8

# ---------------------------------------------------------------------------
# TestResurrection
# ---------------------------------------------------------------------------

class TestResurrection:
    def test_eliminated_team_replaced_in_knockout(self):
        purchases = _purchases(("Alice", "Resurrection", "Qatar->Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert "Qatar" not in eff["knockout"]
        assert "Germany" in eff["knockout"]

    def test_eliminated_team_still_in_group_stage(self):
        purchases = _purchases(("Alice", "Resurrection", "Qatar->Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert "Qatar" in eff["group_stage"]

    def test_group_stage_points_from_original_team(self):
        purchases = _purchases(("Alice", "Resurrection", "Qatar->Germany", ""))
        ms = _ms(
            {"Team": "Qatar", "GroupGoals": 3, "RoundReached": "GroupStage"},
            {"Team": "Germany", "KnockoutGoals": 2, "RoundReached": "R16"},
        )
        tm = {**_TIER_MAP, "Germany": 1}
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map=tm,
        )
        # Qatar's 3 GS goals should be in the total
        assert result["team_points"]["Qatar"]["group_stage"] == 3.0

    def test_replacement_knockout_points_count(self):
        purchases = _purchases(("Alice", "Resurrection", "Qatar->Germany", ""))
        ms = _ms(
            {"Team": "Qatar", "GroupGoals": 3, "RoundReached": "GroupStage"},
            {"Team": "Germany", "KnockoutGoals": 2, "RoundReached": "R16"},
        )
        tm = {**_TIER_MAP, "Germany": 1}
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map=tm,
        )
        # Germany: 2 KO goals + T1 R16 = 4
        germany_ko = result["team_points"]["Germany"]["knockout"]
        assert germany_ko == 4.0
        assert "Germany" in result["knockout_teams"]

    def test_resurrection_does_not_change_roster_size(self):
        purchases = _purchases(("Alice", "Resurrection", "Haiti->Germany", ""))
        eff = get_effective_teams("Alice", _ASSIGNMENTS, purchases)
        assert len(eff["knockout"]) == 8

# ---------------------------------------------------------------------------
# TestCalculatePlayerPoints
# ---------------------------------------------------------------------------

class TestCalculatePlayerPoints:
    def test_result_keys_present(self):
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, _EMPTY_MS, _EMPTY_PURCHASES,
            _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
        )
        expected = {
            "player", "group_stage_teams", "knockout_teams", "team_points",
            "group_stage_points", "knockout_points", "base_total",
            "captain", "insurance_bonus", "predictions", "grand_total",
        }
        assert set(result.keys()) == expected

    def test_zero_stats_zero_total(self):
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, _EMPTY_MS, _EMPTY_PURCHASES,
            _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
        )
        assert result["grand_total"] == 0.0

    def test_grand_total_includes_all_bonuses(self):
        ms = _ms({"Team": "France", "GroupGoals": 2})
        purchases = _purchases(("Alice", "Insurance", "", ""))
        # Insurance irrelevant here (no elimination), just check formula
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map=_TIER_MAP,
        )
        expected = (
            result["base_total"]
            + result["captain"]["total"]
            + result["insurance_bonus"]
            + result["predictions"]["total"]
        )
        assert result["grand_total"] == pytest.approx(expected)

    def test_player_with_no_assignments_zero_total(self):
        result = calculate_player_points(
            "Nobody", _ASSIGNMENTS, _EMPTY_MS, _EMPTY_PURCHASES,
            _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
        )
        assert result["grand_total"] == 0.0

    def test_captain_bonus_included_in_grand_total(self):
        ms = _ms({"Team": "France", "GroupGoals": 4, "RoundReached": "Winner"})
        caps = _captains(("Alice", "PreTournament", "France"))
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, _EMPTY_PURCHASES, caps,
            _EMPTY_PREDICTIONS, tier_map=_TIER_MAP,
        )
        france_total = result["team_points"]["France"]["total"]
        expected_bonus = 0.5 * france_total
        assert result["captain"]["pre_tournament_bonus"] == pytest.approx(expected_bonus)
        assert result["grand_total"] > result["base_total"]

    def test_insurance_bonus_included_in_grand_total(self):
        ms = _ms({"Team": "France", "RoundReached": "GroupStage"})
        purchases = _purchases(("Alice", "Insurance", "", ""))
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, purchases, _EMPTY_CAPTAINS,
            _EMPTY_PREDICTIONS, tier_map=_TIER_MAP,
        )
        assert result["insurance_bonus"] == float(INSURANCE_BONUS)
        assert result["grand_total"] == result["base_total"] + float(INSURANCE_BONUS)

    def test_prediction_bonus_included_in_grand_total(self):
        ms = _ms({"Team": "France", "RoundReached": "GroupStage"})
        preds = _predictions(("Alice", "France", "", ""))
        tr = {"world_cup_winner": "France", "golden_boot_winner": "", "dark_horse_rounds": {}}
        result = calculate_player_points(
            "Alice", _ASSIGNMENTS, ms, _EMPTY_PURCHASES, _EMPTY_CAPTAINS,
            preds, tr, _TIER_MAP,
        )
        assert result["predictions"]["winner_bonus"] == float(PREDICTION_WINNER_BONUS)
        assert result["grand_total"] == result["base_total"] + float(PREDICTION_WINNER_BONUS)

# ---------------------------------------------------------------------------
# TestCalculateLeaderboard
# ---------------------------------------------------------------------------

class TestCalculateLeaderboard:
    def _make_leaderboard(self, ms=None):
        ms = ms or _EMPTY_MS
        return calculate_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, ms,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
        )

    def test_returns_dataframe(self):
        assert isinstance(self._make_leaderboard(), pd.DataFrame)

    def test_has_required_columns(self):
        lb = self._make_leaderboard()
        expected = {"Rank", "Player", "BasePoints", "CaptainBonus",
                    "InsuranceBonus", "PredictionBonus", "TotalPoints"}
        assert expected.issubset(set(lb.columns))

    def test_row_count_equals_participants(self):
        lb = self._make_leaderboard()
        assert len(lb) == len(_ASSIGNMENTS)

    def test_rank_starts_at_one(self):
        lb = self._make_leaderboard()
        assert lb["Rank"].iloc[0] == 1

    def test_rank_is_sequential(self):
        lb = self._make_leaderboard()
        assert lb["Rank"].tolist() == list(range(1, len(lb) + 1))

    def test_sorted_descending_by_total(self):
        ms = _ms(
            {"Team": "France", "GroupGoals": 10},
            {"Team": "Argentina", "GroupGoals": 1},
        )
        lb = calculate_leaderboard(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, ms,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
        )
        totals = lb["TotalPoints"].tolist()
        assert totals == sorted(totals, reverse=True)

    def test_all_players_present(self):
        lb = self._make_leaderboard()
        assert set(lb["Player"].tolist()) == set(_ASSIGNMENTS.keys())

    def test_zero_stats_all_zero_totals(self):
        lb = self._make_leaderboard()
        assert (lb["TotalPoints"] == 0.0).all()

    def test_dark_horse_rounds_auto_built_from_match_stats(self):
        ms = _ms({"Team": "Panama", "RoundReached": "SF"})
        preds = _predictions(("Alice", "", "", "Panama"))
        lb = calculate_leaderboard(
            ["Alice"], {"Alice": ["France", "Spain", "USA", "Mexico",
                                  "Norway", "Panama", "Qatar", "Haiti"]},
            ms, _EMPTY_PURCHASES, _EMPTY_CAPTAINS, preds,
        )
        # Alice's dark horse Panama reached SF → 15+30=45 pts
        alice_row = lb[lb["Player"] == "Alice"].iloc[0]
        assert alice_row["PredictionBonus"] == 45.0

# ---------------------------------------------------------------------------
# TestValidateCaptains
# ---------------------------------------------------------------------------

class TestValidateCaptains:
    def test_valid_different_teams_no_errors(self):
        caps = _captains(
            ("Alice", "PreTournament", "France"),
            ("Alice", "Knockout", "Spain"),
        )
        assert validate_captains("Alice", caps) == []

    def test_same_team_both_slots_is_error(self):
        caps = _captains(
            ("Alice", "PreTournament", "France"),
            ("Alice", "Knockout", "France"),
        )
        errors = validate_captains("Alice", caps)
        assert len(errors) == 1
        assert "France" in errors[0]

    def test_multiple_pre_tournament_captains_is_error(self):
        caps = _captains(
            ("Alice", "PreTournament", "France"),
            ("Alice", "PreTournament", "Spain"),
        )
        errors = validate_captains("Alice", caps)
        assert any("PreTournament" in e for e in errors)

    def test_multiple_knockout_captains_is_error(self):
        caps = _captains(
            ("Alice", "Knockout", "France"),
            ("Alice", "Knockout", "Spain"),
        )
        errors = validate_captains("Alice", caps)
        assert any("Knockout" in e for e in errors)

    def test_no_captains_no_errors(self):
        assert validate_captains("Alice", _EMPTY_CAPTAINS) == []

    def test_player_not_in_captains_no_errors(self):
        caps = _captains(("Bob", "PreTournament", "France"))
        assert validate_captains("Alice", caps) == []

    def test_returns_list(self):
        assert isinstance(validate_captains("Alice", _EMPTY_CAPTAINS), list)

# ---------------------------------------------------------------------------
# TestValidatePurchases
# ---------------------------------------------------------------------------

class TestValidatePurchases:
    def test_valid_purchases_no_errors(self):
        p = _purchases(
            ("Alice", "Insurance", "", ""),
            ("Alice", "NinthTeam", "Germany", ""),
        )
        assert validate_purchases("Alice", p) == []

    def test_duplicate_insurance_error(self):
        p = _purchases(
            ("Alice", "Insurance", "", ""),
            ("Alice", "Insurance", "", ""),
        )
        errors = validate_purchases("Alice", p)
        assert any("Insurance" in e for e in errors)

    def test_duplicate_ninth_team_error(self):
        p = _purchases(
            ("Alice", "NinthTeam", "France", ""),
            ("Alice", "NinthTeam", "Spain", ""),
        )
        errors = validate_purchases("Alice", p)
        assert any("NinthTeam" in e for e in errors)

    def test_duplicate_resurrection_error(self):
        p = _purchases(
            ("Alice", "Resurrection", "Qatar->Germany", ""),
            ("Alice", "Resurrection", "Haiti->Italy", ""),
        )
        errors = validate_purchases("Alice", p)
        assert any("Resurrection" in e for e in errors)

    def test_unknown_purchase_type_error(self):
        p = _purchases(("Alice", "FreeTeam", "", ""))
        errors = validate_purchases("Alice", p)
        assert any("FreeTeam" in e for e in errors)

    def test_empty_purchases_no_errors(self):
        assert validate_purchases("Alice", _EMPTY_PURCHASES) == []

    def test_other_player_purchases_not_checked(self):
        # Alice has 2 Insurance rows; Bob has none — only Alice reported
        p = _purchases(
            ("Alice", "Insurance", "", ""),
            ("Alice", "Insurance", "", ""),
        )
        assert validate_purchases("Bob", p) == []

# ---------------------------------------------------------------------------
# TestGeneratePlayerSummary
# ---------------------------------------------------------------------------

class TestGeneratePlayerSummary:
    def test_returns_dataframe(self, tmp_path):
        out = tmp_path / "summary.csv"
        result = generate_player_summary(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _EMPTY_MS,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        assert isinstance(result, pd.DataFrame)

    def test_creates_csv_file(self, tmp_path):
        out = tmp_path / "summary.csv"
        generate_player_summary(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _EMPTY_MS,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        assert out.exists()

    def test_row_count_equals_participants(self, tmp_path):
        out = tmp_path / "summary.csv"
        df = generate_player_summary(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _EMPTY_MS,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        assert len(df) == len(_ASSIGNMENTS)

    def test_required_columns_present(self, tmp_path):
        out = tmp_path / "summary.csv"
        df = generate_player_summary(
            list(_ASSIGNMENTS.keys()), _ASSIGNMENTS, _EMPTY_MS,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        expected = {
            "Player", "TeamsOwned", "PreTournamentCaptain", "KnockoutCaptain",
            "WorldCupWinnerPick", "GoldenBootPick", "DarkHorsePick",
            "InsuranceStatus", "NinthTeam", "ResurrectionTeam",
            "BasePoints", "CaptainBonus", "InsuranceBonus",
            "PredictionBonus", "TotalPoints",
        }
        assert expected.issubset(set(df.columns))

    def test_insurance_status_shows_yes(self, tmp_path):
        out = tmp_path / "summary.csv"
        purchases = _purchases(("Alice", "Insurance", "", ""))
        df = generate_player_summary(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, _EMPTY_MS,
            purchases, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        assert df[df["Player"] == "Alice"]["InsuranceStatus"].iloc[0] == "Yes"

    def test_ninth_team_recorded(self, tmp_path):
        out = tmp_path / "summary.csv"
        purchases = _purchases(("Alice", "NinthTeam", "Germany", ""))
        df = generate_player_summary(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, _EMPTY_MS,
            purchases, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        assert df[df["Player"] == "Alice"]["NinthTeam"].iloc[0] == "Germany"

    def test_resurrection_team_recorded(self, tmp_path):
        out = tmp_path / "summary.csv"
        purchases = _purchases(("Alice", "Resurrection", "Qatar->Germany", ""))
        df = generate_player_summary(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, _EMPTY_MS,
            purchases, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        assert df[df["Player"] == "Alice"]["ResurrectionTeam"].iloc[0] == "Germany"

    def test_total_points_in_csv_matches_calculate(self, tmp_path):
        out = tmp_path / "summary.csv"
        ms = _ms({"Team": "France", "GroupGoals": 3, "RoundReached": "Winner"})
        df = generate_player_summary(
            ["Alice"], {"Alice": _ASSIGNMENTS["Alice"]}, ms,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            output_path=out,
        )
        direct = calculate_player_points(
            "Alice", {"Alice": _ASSIGNMENTS["Alice"]}, ms,
            _EMPTY_PURCHASES, _EMPTY_CAPTAINS, _EMPTY_PREDICTIONS,
            tier_map=_TIER_MAP,
        )
        assert df.iloc[0]["TotalPoints"] == pytest.approx(direct["grand_total"])
