"""Tests for src/event_engine.py — admin operations layer."""

import random
from pathlib import Path

import pandas as pd
import pytest

from src.event_engine import (
    Allocation,
    ManualResultsProvider,
    generate_draw_broadcast,
    generate_payment_ledger,
    generate_team_ownership_csv,
    generate_whatsapp_update,
    load_allocation,
    ninth_team_candidates,
    process_pending_purchases,
    resurrection_candidates,
    run_group_stage_close,
    run_mulligan_draw,
    run_ninth_team_draw,
    run_resurrection_draw,
    export_random_seeds,
    save_allocation,
    update_results,
    lock_predictions,
    lock_buyins,
)
from src.competition import (
    add_purchase,
    create_event,
    load_audit_log,
    load_events,
    load_player_status,
    update_event_status,
)

# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------

_ALICE = "Alice"
_BOB   = "Bob"
_CAROL = "Carol"

# Alice: groups A(SouthAfrica), B(Switzerland), C(Scotland), D(USA), G(NewZealand), I(France), J(Algeria), L(England)
_ALICE_TEAMS = [
    "France", "England",         # T1: I, L
    "USA", "Switzerland",        # T2: D, B
    "Algeria", "Scotland",       # T3: J, C
    "New Zealand", "South Africa",  # T4: G, A
]

# Bob: groups B(Qatar), C(Haiti), D(Paraguay), E(Germany), F(Japan), G(Belgium), H(Uruguay), K(Congodr)
_BOB_TEAMS = [
    "Germany", "Belgium",        # T1: E, G
    "Japan", "Uruguay",          # T2: F, H
    "Congo DR", "Paraguay",      # T3: K, D
    "Qatar", "Haiti",            # T4: B, C
]

# Carol: groups A(Mexico), E(CoteIvoire), F(Sweden), H(Spain), I(Iraq), J(Austria), K(Portugal), L(Ghana)
_CAROL_TEAMS = [
    "Spain", "Portugal",         # T1: H, K
    "Mexico", "Austria",         # T2: A, J
    "Cote d Ivoire", "Sweden",   # T3: E, F
    "Iraq", "Ghana",             # T4: I, L
]

_ASSIGNMENTS = {
    _ALICE: _ALICE_TEAMS,
    _BOB:   _BOB_TEAMS,
    _CAROL: _CAROL_TEAMS,
}

_STAT_COLS = [
    "Team", "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins",
    "GroupComebackWins", "GroupWinner", "KnockoutGoals",
    "KnockoutCleanSheets", "KnockoutPenaltyWins",
    "KnockoutComebackWins", "RoundReached",
]


def _stat(team: str, round_reached: str = "GroupStage", gw: int = 0,
          gg: int = 0, gcs: int = 0) -> dict:
    return {
        "Team": team, "RoundReached": round_reached,
        "GroupWinner": gw, "GroupGoals": gg, "GroupCleanSheets": gcs,
        "GroupPenaltyWins": 0, "GroupComebackWins": 0,
        "KnockoutGoals": 0, "KnockoutCleanSheets": 0,
        "KnockoutPenaltyWins": 0, "KnockoutComebackWins": 0,
    }


def _make_stats(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=_STAT_COLS)


def _base_match_stats() -> pd.DataFrame:
    return _make_stats(
        _stat("France",       "R16", gw=1, gg=5),
        _stat("Germany",      "QF",  gw=1, gg=6),   # Group E — valid 9th for Alice
        _stat("England",      "R16", gw=0, gg=3),
        _stat("Spain",        "SF",  gw=1, gg=7),
        _stat("Iraq",         "R16", gw=0, gg=2),   # T4 Group I — valid resurrection for Bob
        _stat("Saudi Arabia", "R16", gw=0, gg=1),   # T4 Group H — not in Alice's groups after removing SouthAfrica
        _stat("South Africa", "GroupStage"),          # Alice's T4 — eliminated
        _stat("Qatar",        "GroupStage"),          # Bob's T4 — eliminated
    )


def _empty_purchases() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])


def _empty_statuses() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "Status", "PaidTimestamp"])


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=["EventID", "EventType", "ScheduledTime", "ExecutedTime", "Status", "RandomSeed"])


def _gs_closed_events() -> pd.DataFrame:
    """Events DataFrame with GROUP_STAGE_CLOSE already executed — required by resurrection draw."""
    return pd.DataFrame([{
        "EventID": "evt-gs-close", "EventType": "GROUP_STAGE_CLOSE",
        "ScheduledTime": "2026-06-26T00:00:00+00:00",
        "ExecutedTime":  "2026-06-26T00:01:00+00:00",
        "Status": "EXECUTED", "RandomSeed": "",
    }])


def _empty_audit() -> pd.DataFrame:
    return pd.DataFrame(columns=["Timestamp", "Event", "Player", "Action", "Result"])


def _purch(player, ptype, ref="REF", selection="") -> dict:
    return {
        "Player": player, "PurchaseType": ptype,
        "Timestamp": "2026-01-01T00:00:00+00:00", "Reference": ref,
        "Selection": selection,
    }


# ---------------------------------------------------------------------------
# 1. Ninth Team Candidates
# ---------------------------------------------------------------------------

class TestNinthTeamCandidates:
    def test_no_survivors_returns_empty(self):
        ms = _make_stats(
            _stat("France", "GroupStage"),
            _stat("Germany", "GroupStage"),
        )
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, _empty_purchases())
        assert result == []

    def test_empty_stats_returns_empty(self):
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, pd.DataFrame(columns=_STAT_COLS), _empty_purchases())
        assert result == []

    def test_surviving_in_owned_group_excluded(self):
        # France (I) survives — but Alice owns group I, so invalid
        ms = _make_stats(_stat("France", "R16", gw=1))
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, _empty_purchases())
        assert "France" not in result

    def test_surviving_in_non_owned_group_included(self):
        # Germany (E) survives — Alice does not own group E
        ms = _make_stats(_stat("Germany", "QF", gw=1))
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, _empty_purchases())
        assert "Germany" in result

    def test_owned_team_excluded(self):
        # England (L) — Alice owns it
        ms = _make_stats(_stat("England", "R16"))
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, _empty_purchases())
        assert "England" not in result

    def test_result_sorted_alphabetically(self):
        ms = _make_stats(
            _stat("Spain",    "SF", gw=1),   # H — not Alice's
            _stat("Germany",  "QF", gw=1),   # E — not Alice's
        )
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, _empty_purchases())
        assert result == sorted(result)

    def test_all_tiers_eligible(self):
        ms = _make_stats(
            _stat("Germany",      "QF"),  # T1 E
            _stat("Saudi Arabia", "R16"), # T4 H
        )
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, _empty_purchases())
        assert "Germany" in result
        assert "Saudi Arabia" in result

    def test_processed_ninth_team_excluded_from_selection(self):
        # If Alice already has Germany as a ninth team, Germany should not appear again
        purch = pd.DataFrame([
            _purch(_ALICE, "NinthTeam", selection="Germany"),
        ])
        ms = _make_stats(_stat("Germany", "QF"), _stat("Spain", "SF"))
        result = ninth_team_candidates(_ALICE, _ASSIGNMENTS, ms, purch)
        assert "Germany" not in result
        assert "Spain" in result


# ---------------------------------------------------------------------------
# 2. Resurrection Candidates
# ---------------------------------------------------------------------------

class TestResurrectionCandidates:
    def _tmap(self) -> dict:
        from src.team_database import load_teams
        df = load_teams()
        return dict(zip(df["Team"], df["Tier"].astype(int)))

    def test_empty_stats_returns_empty(self):
        result = resurrection_candidates(
            _ALICE, "South Africa", _ASSIGNMENTS,
            pd.DataFrame(columns=_STAT_COLS), _empty_purchases(), self._tmap()
        )
        assert result == []

    def test_different_tier_excluded(self):
        ms = _make_stats(_stat("Germany", "QF"))  # T1, not T4
        result = resurrection_candidates(
            _ALICE, "South Africa", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert "Germany" not in result

    def test_same_tier_valid_group_included(self):
        # Saudi Arabia (T4, H) — not in Alice's remaining groups after removing South Africa
        ms = _make_stats(_stat("Saudi Arabia", "R16"))
        result = resurrection_candidates(
            _ALICE, "South Africa", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert "Saudi Arabia" in result

    def test_same_group_as_owned_excluded(self):
        # New Zealand (T4, G) — Alice owns group G
        ms = _make_stats(_stat("New Zealand", "R16"))
        result = resurrection_candidates(
            _ALICE, "South Africa", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert "New Zealand" not in result

    def test_owned_team_excluded(self):
        # South Africa itself (even if somehow "surviving") must be excluded
        ms = _make_stats(_stat("South Africa", "R16"))
        result = resurrection_candidates(
            _ALICE, "South Africa", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert "South Africa" not in result

    def test_result_sorted(self):
        ms = _make_stats(
            _stat("Saudi Arabia", "R16"),
            _stat("Cabo Verde",   "R16"),
        )
        result = resurrection_candidates(
            _ALICE, "South Africa", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert result == sorted(result)

    def test_bob_t4_resurrection(self):
        # Bob replaces Qatar (T4, B). Bob's remaining groups: E,G,F,H,K,D,C
        # Iraq (T4, I) → I not in Bob's remaining groups → valid
        ms = _make_stats(_stat("Iraq", "R16"))
        result = resurrection_candidates(
            _BOB, "Qatar", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert "Iraq" in result

    def test_invalid_group_excluded_for_bob(self):
        # Uzbekistan (T4, K) — Bob owns K (Congo DR) → invalid
        ms = _make_stats(_stat("Uzbekistan", "R16"))
        result = resurrection_candidates(
            _BOB, "Qatar", _ASSIGNMENTS, ms, _empty_purchases(), self._tmap()
        )
        assert "Uzbekistan" not in result


# ---------------------------------------------------------------------------
# 3. Process Pending Purchases
# ---------------------------------------------------------------------------

class TestProcessPendingPurchases:
    def test_empty_purchases_returns_empty(self):
        upurch, ust, msgs = process_pending_purchases(_empty_purchases(), _empty_statuses())
        assert upurch.empty

    def test_buyin_marks_player_paid(self):
        purch = pd.DataFrame([_purch(_ALICE, "BuyIn")])
        st    = pd.DataFrame([{"Player": _ALICE, "Status": "UNPAID", "PaidTimestamp": ""}])
        upurch, ust, msgs = process_pending_purchases(purch, st)
        assert ust.loc[ust["Player"] == _ALICE, "Status"].iloc[0] == "PAID"
        assert any(_ALICE in m for m in msgs)

    def test_non_buyin_does_not_change_status(self):
        purch = pd.DataFrame([_purch(_ALICE, "PredictionPack")])
        st    = pd.DataFrame([{"Player": _ALICE, "Status": "UNPAID", "PaidTimestamp": ""}])
        _, ust, _ = process_pending_purchases(purch, st)
        assert ust.loc[ust["Player"] == _ALICE, "Status"].iloc[0] == "UNPAID"

    def test_returns_purchases_unchanged(self):
        purch = pd.DataFrame([_purch(_ALICE, "BuyIn")])
        upurch, _, _ = process_pending_purchases(purch, _empty_statuses())
        assert len(upurch) == 1


# ---------------------------------------------------------------------------
# 4. Mulligan Draw
# ---------------------------------------------------------------------------

class TestMulliganDraw:
    def _base_allocation(self) -> Allocation:
        from src.allocation_engine import calculate_portfolio_strength
        return Allocation(
            assignments=dict(_ASSIGNMENTS),
            portfolio_scores={p: calculate_portfolio_strength(t) for p, t in _ASSIGNMENTS.items()},
        )

    def test_no_pending_mulligan_no_changes(self):
        alloc  = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), _empty_purchases(), _empty_events(), _empty_audit(), seed=42)
        assert result["results"] == {}
        assert result["errors"] == {}

    def test_pending_mulligan_gives_new_teams(self):
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        alloc = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), _empty_audit(), seed=42)
        assert _ALICE in result["results"] or _ALICE in result["errors"]

    def test_purchase_marked_processed_on_success(self):
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        alloc = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), _empty_audit(), seed=42)
        if _ALICE in result["results"]:
            assert any(result["updated_audit_log"]["Action"] == "MULLIGAN_EXECUTED")

    def test_event_created_and_executed(self):
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        alloc = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), _empty_audit(), seed=42)
        uevents = result["updated_events"]
        assert any(uevents["EventType"] == "MULLIGAN_DRAW")
        executed = uevents[uevents["EventType"] == "MULLIGAN_DRAW"]
        assert executed.iloc[-1]["Status"] == "EXECUTED"

    def test_audit_log_updated(self):
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        alloc = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), _empty_audit(), seed=42)
        ulog = result["updated_audit_log"]
        assert any(ulog["Event"] == "MULLIGAN_DRAW")

    def test_seed_returned(self):
        alloc  = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), _empty_purchases(), _empty_events(), _empty_audit(), seed=999)
        assert result["seed"] == 999

    def test_broadcast_text_returned(self):
        alloc  = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), _empty_purchases(), _empty_events(), _empty_audit(), seed=42)
        assert isinstance(result["broadcast"], str)
        assert "Mulligan" in result["broadcast"]

    def test_reproducible_with_same_seed(self):
        alloc = self._base_allocation()
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        r1 = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), _empty_audit(), seed=77)
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        r2 = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), _empty_audit(), seed=77)
        if _ALICE in r1["results"] and _ALICE in r2["results"]:
            assert sorted(r1["results"][_ALICE]["new"]) == sorted(r2["results"][_ALICE]["new"])

    def test_already_drawn_mulligan_ignored(self):
        # If MULLIGAN_EXECUTED is already in audit_log for Alice, her Mulligan is already done
        purch = pd.DataFrame([_purch(_ALICE, "Mulligan")])
        audit = pd.DataFrame([{
            "Timestamp": "2026-01-01T00:00:00+00:00", "Event": "MULLIGAN_DRAW",
            "Player": _ALICE, "Action": "MULLIGAN_EXECUTED", "Result": "42",
        }])
        alloc = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), purch, _empty_events(), audit, seed=42)
        assert result["results"] == {}

    def test_updated_allocation_returned(self):
        alloc  = self._base_allocation()
        result = run_mulligan_draw(alloc, list(_ASSIGNMENTS), _empty_purchases(), _empty_events(), _empty_audit(), seed=42)
        assert isinstance(result["updated_allocation"], Allocation)


# ---------------------------------------------------------------------------
# 5. Ninth Team Draw
# ---------------------------------------------------------------------------

class TestNinthTeamDraw:
    def test_no_pending_ninth_no_changes(self):
        ms = _base_match_stats()
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, _empty_purchases(), _empty_events(), _empty_audit(), seed=42)
        assert result["results"] == {}

    def test_valid_candidate_assigned(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "QF", gw=1))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        assert _ALICE in result["results"]
        assert result["results"][_ALICE] == "Germany"

    def test_selection_written_to_purchase(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "QF", gw=1))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        row = result["updated_purchases"][
            (result["updated_purchases"]["Player"] == _ALICE) &
            (result["updated_purchases"]["PurchaseType"] == "NinthTeam")
        ]
        assert row.iloc[0]["Selection"] == "Germany"

    def test_purchase_selection_written_on_success(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "QF", gw=1))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        row = result["updated_purchases"][
            (result["updated_purchases"]["Player"] == _ALICE) &
            (result["updated_purchases"]["PurchaseType"] == "NinthTeam")
        ]
        assert row.iloc[0]["Selection"] != ""

    def test_audit_log_entry_added(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "QF", gw=1))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        assert any(result["updated_audit_log"]["Event"] == "NINTH_TEAM_DRAW")

    def test_event_created(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "QF", gw=1))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        assert any(result["updated_events"]["EventType"] == "NINTH_TEAM_DRAW")

    def test_error_when_no_candidates(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "GroupStage"))  # eliminated
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        assert _ALICE in result["errors"]
        assert _ALICE not in result["results"]

    def test_already_drawn_ninth_skipped(self):
        # Selection already populated means already drawn — should be skipped
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam", selection="Germany")])
        ms = _make_stats(_stat("Germany", "QF"))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        assert result["results"] == {}

    def test_reproducible_same_seed(self):
        purch1 = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        purch2 = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _base_match_stats()
        r1 = run_ninth_team_draw(_ASSIGNMENTS, ms, purch1, _empty_events(), _empty_audit(), seed=123)
        r2 = run_ninth_team_draw(_ASSIGNMENTS, ms, purch2, _empty_events(), _empty_audit(), seed=123)
        if _ALICE in r1["results"] and _ALICE in r2["results"]:
            assert r1["results"][_ALICE] == r2["results"][_ALICE]

    def test_broadcast_text_contains_player(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        ms = _make_stats(_stat("Germany", "QF"))
        result = run_ninth_team_draw(_ASSIGNMENTS, ms, purch, _empty_events(), _empty_audit(), seed=42)
        if _ALICE in result["results"]:
            assert _ALICE in result["broadcast"]


# ---------------------------------------------------------------------------
# 6. Resurrection Draw
# ---------------------------------------------------------------------------

class TestResurrectionDraw:
    def _tmap(self) -> dict:
        from src.team_database import load_teams
        df = load_teams()
        return dict(zip(df["Team"], df["Tier"].astype(int)))

    def test_no_pending_resurrection_no_changes(self):
        ms = _base_match_stats()
        result = run_resurrection_draw(_ASSIGNMENTS, ms, _empty_purchases(), _gs_closed_events(), _empty_audit(), seed=42)
        assert result["results"] == {}

    def test_valid_replacement_assigned(self):
        # Bob resurrects Qatar (T4,B); Iraq (T4,I) is the valid candidate
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        ms = _make_stats(_stat("Qatar", "GroupStage"), _stat("Iraq", "R16"))
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        assert _BOB in result["results"]
        assert result["results"][_BOB]["replacement"] == "Iraq"

    def test_selection_format_elim_to_replacement(self):
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        ms = _make_stats(_stat("Qatar", "GroupStage"), _stat("Iraq", "R16"))
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        upurch = result["updated_purchases"]
        row = upurch[(upurch["Player"] == _BOB) & (upurch["PurchaseType"] == "Resurrection")]
        assert "Qatar->Iraq" == row.iloc[0]["Selection"]

    def test_purchase_selection_written_on_success(self):
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        ms = _make_stats(_stat("Qatar", "GroupStage"), _stat("Iraq", "R16"))
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        row = result["updated_purchases"][
            (result["updated_purchases"]["Player"] == _BOB) &
            (result["updated_purchases"]["PurchaseType"] == "Resurrection")
        ]
        assert "->" in row.iloc[0]["Selection"]

    def test_error_when_no_selection_set(self):
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="")])
        ms = _base_match_stats()
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        assert _BOB in result["errors"]

    def test_error_when_no_candidates(self):
        # No surviving T4 team available
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        ms = _make_stats(_stat("Qatar", "GroupStage"))  # no valid candidates
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        assert _BOB in result["errors"]

    def test_event_created_and_executed(self):
        ms = _base_match_stats()
        result = run_resurrection_draw(_ASSIGNMENTS, ms, _empty_purchases(), _gs_closed_events(), _empty_audit(), seed=42)
        assert any(result["updated_events"]["EventType"] == "RESURRECTION_DRAW")
        executed = result["updated_events"][result["updated_events"]["EventType"] == "RESURRECTION_DRAW"]
        assert executed.iloc[-1]["Status"] == "EXECUTED"

    def test_audit_log_updated_on_success(self):
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        ms = _make_stats(_stat("Qatar", "GroupStage"), _stat("Iraq", "R16"))
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        if _BOB in result["results"]:
            assert any(result["updated_audit_log"]["Action"] == "RESURRECTION_ASSIGNED")

    def test_reproducible_same_seed(self):
        ms = _make_stats(
            _stat("Qatar", "GroupStage"),
            _stat("Iraq",  "R16"),
            _stat("South Africa", "GroupStage"),
        )
        purch1 = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        purch2 = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        r1 = run_resurrection_draw(_ASSIGNMENTS, ms, purch1, _gs_closed_events(), _empty_audit(), seed=55)
        r2 = run_resurrection_draw(_ASSIGNMENTS, ms, purch2, _gs_closed_events(), _empty_audit(), seed=55)
        if _BOB in r1["results"] and _BOB in r2["results"]:
            assert r1["results"][_BOB]["replacement"] == r2["results"][_BOB]["replacement"]

    def test_broadcast_contains_result(self):
        purch = pd.DataFrame([_purch(_BOB, "Resurrection", selection="Qatar")])
        ms = _make_stats(_stat("Qatar", "GroupStage"), _stat("Iraq", "R16"))
        result = run_resurrection_draw(_ASSIGNMENTS, ms, purch, _gs_closed_events(), _empty_audit(), seed=42)
        if _BOB in result["results"]:
            assert _BOB in result["broadcast"]


# ---------------------------------------------------------------------------
# 7. Group Stage Close
# ---------------------------------------------------------------------------

class TestGroupStageClose:
    def test_survivors_identified(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        assert "France" in result["surviving_teams"]
        assert "Germany" in result["surviving_teams"]

    def test_eliminated_identified(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        assert "South Africa" in result["eliminated_teams"]
        assert "Qatar" in result["eliminated_teams"]

    def test_group_winners_identified(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        assert "France" in result["group_winners"]
        assert "Germany" in result["group_winners"]
        assert "England" not in result["group_winners"]

    def test_ninth_team_draw_event_created(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        assert any(result["updated_events"]["EventType"] == "NINTH_TEAM_DRAW")

    def test_resurrection_draw_event_created(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        assert any(result["updated_events"]["EventType"] == "RESURRECTION_DRAW")

    def test_events_are_scheduled_not_executed(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        for etype in ["NINTH_TEAM_DRAW", "RESURRECTION_DRAW"]:
            rows = result["updated_events"][result["updated_events"]["EventType"] == etype]
            assert rows.iloc[-1]["Status"] == "SCHEDULED"

    def test_audit_log_entry_added(self):
        ms = _base_match_stats()
        result = run_group_stage_close(ms, _empty_events(), _empty_audit())
        assert any(result["updated_audit_log"]["Event"] == "GROUP_STAGE_CLOSE")

    def test_empty_stats_returns_empty_lists(self):
        result = run_group_stage_close(
            pd.DataFrame(columns=_STAT_COLS), _empty_events(), _empty_audit()
        )
        assert result["surviving_teams"] == []
        assert result["eliminated_teams"] == []
        assert result["group_winners"] == []


# ---------------------------------------------------------------------------
# 8. Locking
# ---------------------------------------------------------------------------

class TestLocking:
    def test_lock_predictions_creates_event(self):
        uevents, _ = lock_predictions(_empty_events(), _empty_audit(), "2026-06-15T12:00:00+00:00")
        assert any(uevents["EventType"] == "PREDICTION_LOCK")

    def test_lock_predictions_event_executed(self):
        uevents, _ = lock_predictions(_empty_events(), _empty_audit(), "2026-06-15T12:00:00+00:00")
        row = uevents[uevents["EventType"] == "PREDICTION_LOCK"]
        assert row.iloc[-1]["Status"] == "EXECUTED"

    def test_lock_predictions_audit_log_updated(self):
        _, ulog = lock_predictions(_empty_events(), _empty_audit(), "2026-06-15T12:00:00+00:00")
        assert any(ulog["Event"] == "PREDICTION_LOCK")

    def test_lock_buyins_creates_event(self):
        _, uevents, _ = lock_buyins(_empty_statuses(), _empty_events(), _empty_audit(), "2026-06-28T19:00:00+00:00")
        assert any(uevents["EventType"] == "BUYIN_LOCK")

    def test_lock_buyins_event_executed(self):
        _, uevents, _ = lock_buyins(_empty_statuses(), _empty_events(), _empty_audit(), "2026-06-28T19:00:00+00:00")
        row = uevents[uevents["EventType"] == "BUYIN_LOCK"]
        assert row.iloc[-1]["Status"] == "EXECUTED"

    def test_lock_buyins_audit_log_updated(self):
        _, _, ulog = lock_buyins(_empty_statuses(), _empty_events(), _empty_audit(), "2026-06-28T19:00:00+00:00")
        assert any(ulog["Event"] == "BUYIN_LOCK")


# ---------------------------------------------------------------------------
# 9. Results Provider
# ---------------------------------------------------------------------------

class TestResultsProvider:
    def _ms(self) -> pd.DataFrame:
        return _make_stats(
            _stat("France", "R16", gw=1, gg=5),
            _stat("Germany", "GroupStage"),
        )

    def test_update_results_updates_known_team(self):
        ms = self._ms()
        updated = update_results("France", {"RoundReached": "QF", "KnockoutGoals": 2}, ms)
        row = updated[updated["Team"] == "France"].iloc[0]
        assert row["RoundReached"] == "QF"
        assert row["KnockoutGoals"] == 2

    def test_update_results_adds_unknown_team(self):
        ms = self._ms()
        updated = update_results("Atlantis", {"RoundReached": "Final"}, ms)
        assert "Atlantis" in updated["Team"].values

    def test_update_results_does_not_mutate_input(self):
        ms = self._ms()
        _ = update_results("France", {"GroupGoals": 99}, ms)
        assert ms[ms["Team"] == "France"].iloc[0]["GroupGoals"] == 5

    def test_manual_provider_update_returns_new_provider(self):
        prov = ManualResultsProvider(self._ms())
        prov2 = prov.update("France", {"KnockoutGoals": 3})
        assert isinstance(prov2, ManualResultsProvider)
        assert prov2 is not prov

    def test_manual_provider_chaining(self):
        prov = ManualResultsProvider(self._ms())
        final = prov.update("France", {"KnockoutGoals": 3}).update("Germany", {"RoundReached": "QF"})
        stats = final.get_stats()
        assert stats[stats["Team"] == "Germany"].iloc[0]["RoundReached"] == "QF"
        assert stats[stats["Team"] == "France"].iloc[0]["KnockoutGoals"] == 3

    def test_manual_provider_get_stats_returns_copy(self):
        prov = ManualResultsProvider(self._ms())
        s1 = prov.get_stats()
        s2 = prov.get_stats()
        assert s1 is not s2


# ---------------------------------------------------------------------------
# 10. WhatsApp Update
# ---------------------------------------------------------------------------

class TestWhatsAppUpdate:
    def _empty_lb(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["Rank", "Player", "TotalPoints", "PaymentStatus"])

    def _sample_lb(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"Rank": 1, "Player": _ALICE, "TotalPoints": 120, "PaymentStatus": "PAID"},
            {"Rank": 2, "Player": _BOB,   "TotalPoints": 110, "PaymentStatus": "PAID"},
        ])

    def _prize_pool(self) -> dict:
        return {"current_pot": 100.0, "first_prize": 50.0, "second_prize": 30.0, "third_prize": 20.0}

    def test_returns_nonempty_string(self):
        text = generate_whatsapp_update(self._empty_lb(), self._empty_lb(), self._prize_pool(), _empty_events(), _base_match_stats())
        assert isinstance(text, str) and len(text) > 0

    def test_prize_pool_values_present(self):
        text = generate_whatsapp_update(self._empty_lb(), self._empty_lb(), self._prize_pool(), _empty_events(), _base_match_stats())
        assert "100.00" in text
        assert "50.00" in text

    def test_player_names_in_leaderboard(self):
        lb = self._sample_lb()
        text = generate_whatsapp_update(lb, lb, self._prize_pool(), _empty_events(), _base_match_stats())
        assert _ALICE in text
        assert _BOB in text

    def test_handles_empty_leaderboards(self):
        text = generate_whatsapp_update(self._empty_lb(), self._empty_lb(), self._prize_pool(), _empty_events(), _base_match_stats())
        assert isinstance(text, str)

    def test_next_event_shown_when_scheduled(self):
        events = create_event("NINTH_TEAM_DRAW", "2026-07-01T12:00:00+00:00", _empty_events())
        text = generate_whatsapp_update(self._empty_lb(), self._empty_lb(), self._prize_pool(), events, _base_match_stats())
        assert "NINTH_TEAM_DRAW" in text

    def test_top_team_shown_when_stats_present(self):
        ms = _make_stats(
            _stat("Germany", "QF", gw=1, gg=8),
            _stat("France",  "R16", gw=1, gg=3),
        )
        text = generate_whatsapp_update(
            self._empty_lb(), self._empty_lb(), self._prize_pool(), _empty_events(), ms
        )
        assert "Germany" in text


# ---------------------------------------------------------------------------
# 11. Draw Broadcast
# ---------------------------------------------------------------------------

class TestDrawBroadcast:
    def test_contains_dice_emoji(self):
        text = generate_draw_broadcast("Ninth Team Draw", {_ALICE: "Germany"})
        assert "🎲" in text

    def test_contains_draw_type(self):
        text = generate_draw_broadcast("Resurrection Draw", {})
        assert "Resurrection Draw" in text

    def test_contains_player_name(self):
        text = generate_draw_broadcast("Ninth Team Draw", {_ALICE: "Germany"})
        assert _ALICE in text

    def test_contains_team_name(self):
        text = generate_draw_broadcast("Ninth Team Draw", {_ALICE: "Germany"})
        assert "Germany" in text

    def test_empty_results_handled(self):
        text = generate_draw_broadcast("Mulligan Draw", {})
        assert isinstance(text, str)
        assert "No draws" in text


# ---------------------------------------------------------------------------
# 12. Payment Ledger
# ---------------------------------------------------------------------------

class TestPaymentLedger:
    def test_required_columns_present(self):
        purch = pd.DataFrame([_purch(_ALICE, "BuyIn")])
        df = generate_payment_ledger(purch)
        for col in ["Player", "Purchase", "Amount", "Reference", "Timestamp"]:
            assert col in df.columns

    def test_buyin_amount_correct(self):
        purch = pd.DataFrame([_purch(_ALICE, "BuyIn")])
        df = generate_payment_ledger(purch)
        assert df.iloc[0]["Amount"] == 5.0

    def test_ninth_amount_correct(self):
        purch = pd.DataFrame([_purch(_ALICE, "NinthTeam")])
        df = generate_payment_ledger(purch)
        assert df.iloc[0]["Amount"] == 3.0

    def test_resurrection_amount_correct(self):
        purch = pd.DataFrame([_purch(_ALICE, "Resurrection")])
        df = generate_payment_ledger(purch)
        assert df.iloc[0]["Amount"] == 5.0

    def test_insurance_amount_correct(self):
        purch = pd.DataFrame([_purch(_ALICE, "Insurance")])
        df = generate_payment_ledger(purch)
        assert df.iloc[0]["Amount"] == 2.0

    def test_amount_column_present(self):
        purch = pd.DataFrame([_purch(_ALICE, "BuyIn"), _purch(_BOB, "PredictionPack")])
        df = generate_payment_ledger(purch)
        assert "Amount" in df.columns

    def test_one_row_per_purchase(self):
        purch = pd.DataFrame([
            _purch(_ALICE, "BuyIn"),
            _purch(_ALICE, "PredictionPack"),
            _purch(_BOB,   "BuyIn"),
        ])
        df = generate_payment_ledger(purch)
        assert len(df) == 3

    def test_empty_purchases_returns_empty_with_columns(self):
        df = generate_payment_ledger(_empty_purchases())
        assert df.empty
        for col in ["Player", "Purchase", "Amount", "Reference", "Timestamp"]:
            assert col in df.columns


# ---------------------------------------------------------------------------
# 13. Random Seeds Export
# ---------------------------------------------------------------------------

class TestRandomSeedsExport:
    def test_empty_events_returns_empty_with_columns(self):
        df = export_random_seeds(_empty_events())
        assert df.empty
        for col in ["EventID", "EventType", "RandomSeed"]:
            assert col in df.columns

    def test_only_seeded_events_included(self):
        events = _empty_events()
        events = create_event("INITIAL_DRAW", "2026-06-01T12:00:00+00:00", events)
        eid = events.iloc[-1]["EventID"]
        events = update_event_status(eid, "EXECUTED", events, seed=12345)
        events = create_event("MULLIGAN_DRAW", "2026-06-02T12:00:00+00:00", events)
        df = export_random_seeds(events)
        assert len(df) == 1
        assert str(df.iloc[0]["RandomSeed"]) == "12345"

    def test_correct_columns(self):
        df = export_random_seeds(_empty_events())
        assert list(df.columns) == ["EventID", "EventType", "RandomSeed"]

    def test_seed_values_match_events(self):
        events = _empty_events()
        events = create_event("NINTH_TEAM_DRAW", "2026-06-28T12:00:00+00:00", events)
        eid = events.iloc[-1]["EventID"]
        events = update_event_status(eid, "EXECUTED", events, seed=99999)
        df = export_random_seeds(events)
        assert str(df.iloc[0]["EventType"]) == "NINTH_TEAM_DRAW"


# ---------------------------------------------------------------------------
# 14. Allocation Persistence
# ---------------------------------------------------------------------------

class TestAllocationPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        from src.allocation_engine import calculate_portfolio_strength
        alloc = Allocation(
            assignments=dict(_ASSIGNMENTS),
            portfolio_scores={p: calculate_portfolio_strength(t) for p, t in _ASSIGNMENTS.items()},
        )
        path = tmp_path / "allocation.csv"
        save_allocation(alloc, path)
        loaded = load_allocation(path)
        assert set(loaded.assignments.keys()) == {_ALICE, _BOB, _CAROL}
        assert sorted(loaded.assignments[_ALICE]) == sorted(_ALICE_TEAMS)

    def test_missing_file_returns_empty(self, tmp_path):
        loaded = load_allocation(tmp_path / "nonexistent.csv")
        assert loaded.assignments == {}
        assert loaded.portfolio_scores == {}

    def test_save_creates_file(self, tmp_path):
        from src.allocation_engine import calculate_portfolio_strength
        alloc = Allocation(assignments={_ALICE: _ALICE_TEAMS},
                           portfolio_scores={_ALICE: calculate_portfolio_strength(_ALICE_TEAMS)})
        path = tmp_path / "allocation.csv"
        save_allocation(alloc, path)
        assert path.exists()

    def test_portfolio_scores_computed_on_load(self, tmp_path):
        from src.allocation_engine import calculate_portfolio_strength
        alloc = Allocation(assignments={_ALICE: _ALICE_TEAMS},
                           portfolio_scores={_ALICE: 0.0})  # wrong score intentionally
        path = tmp_path / "allocation.csv"
        save_allocation(alloc, path)
        loaded = load_allocation(path)
        expected = calculate_portfolio_strength(_ALICE_TEAMS)
        assert loaded.portfolio_scores[_ALICE] == pytest.approx(expected)

    def test_empty_allocation_roundtrip(self, tmp_path):
        alloc = Allocation(assignments={}, portfolio_scores={})
        path = tmp_path / "allocation.csv"
        save_allocation(alloc, path)
        loaded = load_allocation(path)
        assert loaded.assignments == {}
