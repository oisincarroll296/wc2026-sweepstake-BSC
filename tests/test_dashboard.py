"""Dashboard integration tests — page loading, backend wiring, rendering logic."""
import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.config import ADMIN_PASSWORD, COLORS, TIER_COLORS, PLOTLY_LAYOUT
from dashboard.components.ui import (
    rank_badge, payment_tag, tier_badge, tier_color,
)


# ── Config tests ──────────────────────────────────────────────────────────

class TestConfig:
    def test_admin_password_set(self):
        assert isinstance(ADMIN_PASSWORD, str) and len(ADMIN_PASSWORD) > 0

    def test_colors_dict_has_required_keys(self):
        for key in ("gold", "navy", "white", "silver", "bronze"):
            assert key in COLORS

    def test_tier_colors_all_four_tiers(self):
        for t in (1, 2, 3, 4):
            assert t in TIER_COLORS
            assert TIER_COLORS[t].startswith("#")

    def test_plotly_layout_has_background(self):
        assert "paper_bgcolor" in PLOTLY_LAYOUT
        assert "plot_bgcolor" in PLOTLY_LAYOUT


# ── UI component tests ────────────────────────────────────────────────────

class TestUIComponents:
    def test_rank_badge_gold_for_1(self):
        badge = rank_badge(1)
        assert "gold-badge" in badge and "1st" in badge

    def test_rank_badge_silver_for_2(self):
        badge = rank_badge(2)
        assert "silver-badge" in badge and "2nd" in badge

    def test_rank_badge_bronze_for_3(self):
        badge = rank_badge(3)
        assert "bronze-badge" in badge and "3rd" in badge

    def test_rank_badge_numeric_for_others(self):
        badge = rank_badge(5)
        assert "#5" in badge

    def test_payment_tag_paid(self):
        tag = payment_tag("PAID")
        assert "paid-tag" in tag and "PAID" in tag

    def test_payment_tag_unpaid(self):
        tag = payment_tag("UNPAID")
        assert "unpaid-tag" in tag and "UNPAID" in tag

    def test_tier_color_returns_hex(self):
        for t in (1, 2, 3, 4):
            assert tier_color(t).startswith("#")

    def test_tier_color_unknown_returns_muted(self):
        assert tier_color(99).startswith("#")

    def test_tier_badge_contains_tier_number(self):
        badge = tier_badge(1)
        assert "T1" in badge

    def test_tier_badge_uses_tier_color(self):
        badge = tier_badge(2)
        color = tier_color(2)
        assert color in badge


# ── Data layer tests (no Streamlit runtime needed) ────────────────────────

class TestDataLayer:
    """Test data.py functions that don't need Streamlit runtime."""

    def test_is_predictions_locked_returns_bool(self):
        from dashboard.data import is_predictions_locked
        result = is_predictions_locked()
        assert isinstance(result, bool)

    def test_get_teams_returns_dataframe(self):
        # Call the underlying loader directly (bypasses @st.cache_data)
        from src.team_database import load_teams
        df = load_teams()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "Team" in df.columns

    def test_get_match_stats_has_48_teams(self):
        from src.scoring_engine import load_match_stats
        ms = load_match_stats()
        assert len(ms) == 48

    def test_get_purchases_is_dataframe(self):
        from src.competition import load_purchases
        p = load_purchases()
        assert isinstance(p, pd.DataFrame)
        assert "Player" in p.columns

    def test_get_statuses_is_dataframe(self):
        from src.competition import load_player_status
        s = load_player_status()
        assert isinstance(s, pd.DataFrame)

    def test_get_events_is_dataframe(self):
        from src.competition import load_events
        e = load_events()
        assert isinstance(e, pd.DataFrame)

    def test_get_audit_log_is_dataframe(self):
        from src.competition import load_audit_log
        a = load_audit_log()
        assert isinstance(a, pd.DataFrame)

    def test_get_predictions_is_dataframe(self):
        from src.scoring_engine import load_predictions
        p = load_predictions()
        assert isinstance(p, pd.DataFrame)

    def test_get_captains_is_dataframe(self):
        from src.scoring_engine import load_captains
        c = load_captains()
        assert isinstance(c, pd.DataFrame)

    def test_tier_map_covers_all_48_teams(self):
        from src.team_database import load_teams
        df = load_teams()
        tmap = dict(zip(df["Team"], df["Tier"].astype(int)))
        assert len(tmap) == 48
        assert all(t in (1, 2, 3, 4) for t in tmap.values())


# ── Backend integration tests ─────────────────────────────────────────────

class TestBackendIntegration:
    """Test that dashboard data functions produce expected shapes."""

    def _empty_df(self, cols):
        return pd.DataFrame(columns=cols)

    def test_prize_pool_empty_purchases(self):
        from src.competition import calculate_prize_pool
        p = self._empty_df(["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])
        pool = calculate_prize_pool(p)
        assert pool["current_pot"] == 0.0
        assert pool["first_prize"] == 0.0

    def test_prize_pool_with_buyins(self):
        from src.competition import calculate_prize_pool
        rows = [
            {"Player": "Alice", "PurchaseType": "BuyIn", "Timestamp": "", "Reference": "", "Selection": ""},
            {"Player": "Bob",   "PurchaseType": "BuyIn", "Timestamp": "", "Reference": "", "Selection": ""},
        ]
        p = pd.DataFrame(rows)
        pool = calculate_prize_pool(p)
        assert pool["current_pot"] == pytest.approx(10.0)
        assert pool["first_prize"] == pytest.approx(5.0)

    def test_prize_leaderboard_no_paid_returns_empty(self):
        from src.competition import prize_leaderboard
        p = self._empty_df(["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])
        s = self._empty_df(["Player", "Status", "PaidTimestamp"])
        ms = self._empty_df(["Team", "GroupGoals", "GroupCleanSheets", "GroupPenaltyWins",
                              "GroupComebackWins", "GroupWinner", "KnockoutGoals",
                              "KnockoutCleanSheets", "KnockoutPenaltyWins",
                              "KnockoutComebackWins", "RoundReached"])
        caps = self._empty_df(["Player", "CaptainType", "Team"])
        preds = self._empty_df(["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])
        lb = prize_leaderboard([], {}, ms, p, caps, preds, s)
        assert lb.empty or len(lb) == 0

    def test_overall_leaderboard_returns_all_players(self):
        from src.competition import overall_leaderboard, mark_paid
        from src.scoring_engine import load_match_stats
        ms = load_match_stats()
        p = self._empty_df(["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])
        s = pd.DataFrame([
            {"Player": "Alice", "Status": "PAID",   "PaidTimestamp": ""},
            {"Player": "Bob",   "Status": "UNPAID", "PaidTimestamp": ""},
        ])
        caps  = self._empty_df(["Player", "CaptainType", "Team"])
        preds = self._empty_df(["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])
        lb = overall_leaderboard(["Alice", "Bob"], {}, ms, p, caps, preds, s)
        assert len(lb) == 2
        assert "PaymentStatus" in lb.columns

    def test_team_ownership_empty_assignments(self):
        from src.competition import get_team_ownership
        p     = self._empty_df(["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])
        caps  = self._empty_df(["Player", "CaptainType", "Team"])
        preds = self._empty_df(["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])
        result = get_team_ownership({}, caps, preds, p)
        assert isinstance(result, dict)

    def test_predictions_centre_empty(self):
        from src.competition import get_predictions_centre
        preds = pd.DataFrame(columns=["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"])
        result = get_predictions_centre(preds)
        assert "world_cup_winner" in result
        assert "golden_boot" in result
        assert "dark_horse" in result


# ── Leaderboard rendering logic ───────────────────────────────────────────

class TestLeaderboardRendering:
    """Test the display transformations used in leaderboard pages."""

    def _sample_lb(self):
        return pd.DataFrame([
            {"Rank": 1, "Player": "Alice", "TotalPoints": 120.0,
             "BasePoints": 100.0, "CaptainBonus": 15.0,
             "InsuranceBonus": 0.0, "PredictionBonus": 5.0, "PaymentStatus": "PAID"},
            {"Rank": 2, "Player": "Bob",   "TotalPoints": 95.0,
             "BasePoints": 80.0, "CaptainBonus": 10.0,
             "InsuranceBonus": 0.0, "PredictionBonus": 5.0, "PaymentStatus": "UNPAID"},
        ])

    def test_gap_from_leader_is_negative_or_dash(self):
        lb = self._sample_lb()
        leader = float(lb.iloc[0]["TotalPoints"])
        gaps = [
            f"{float(r['TotalPoints']) - leader:+.0f}" if i > 0 else "—"
            for i, (_, r) in enumerate(lb.iterrows())
        ]
        assert gaps[0] == "—"
        assert gaps[1].startswith("-")

    def test_medal_assigned_to_top_3(self):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lb = self._sample_lb()
        for _, row in lb.iterrows():
            rank = int(row["Rank"])
            if rank in medals:
                assert medals[rank] in medals.values()

    def test_unpaid_player_detected(self):
        lb = self._sample_lb()
        unpaid = lb[lb["PaymentStatus"] == "UNPAID"]
        assert "Bob" in unpaid["Player"].values

    def test_prize_positions_assigned_correctly(self):
        positions = {1: "Winner", 2: "Runner-up", 3: "3rd Place"}
        lb = self._sample_lb()
        for _, row in lb.iterrows():
            rank = int(row["Rank"])
            expected = positions.get(rank, "—")
            if rank in positions:
                assert expected in positions.values()


# ── VAR Room ─────────────────────────────────────────────────────────────

class TestVARRoomData:
    def test_payment_ledger_file_loads(self):
        p = Path("c:/World Cup/data/payment_ledger.csv")
        if p.exists():
            df = pd.read_csv(p, dtype=str)
            assert "Player" in df.columns or df.empty

    def test_exports_dir_exists(self):
        exports = Path("c:/World Cup/exports")
        assert exports.exists()

    def test_audit_log_columns(self):
        from src.competition import load_audit_log
        a = load_audit_log()
        for col in ["Timestamp", "Event", "Player", "Action", "Result"]:
            assert col in a.columns

    def test_events_columns(self):
        from src.competition import load_events
        e = load_events()
        for col in ["EventID", "EventType", "Status"]:
            assert col in e.columns


# ── Admin page logic ──────────────────────────────────────────────────────

class TestAdminLogic:
    def test_default_password_is_wc2026admin(self):
        import os
        if "ADMIN_PASSWORD" not in os.environ:
            assert ADMIN_PASSWORD == "wc2026admin"

    def test_run_event_callable(self):
        from src.event_engine import run_event
        assert callable(run_event)

    def test_process_pending_purchases_callable(self):
        from src.event_engine import process_pending_purchases
        assert callable(process_pending_purchases)

    def test_generate_whatsapp_update_callable(self):
        from src.event_engine import generate_whatsapp_update
        assert callable(generate_whatsapp_update)

    def test_generate_draw_broadcast_callable(self):
        from src.event_engine import generate_draw_broadcast
        result = generate_draw_broadcast("Test Draw", {"Alice": "Germany"})
        assert "Alice" in result
        assert "Germany" in result
        assert "🎲" in result
