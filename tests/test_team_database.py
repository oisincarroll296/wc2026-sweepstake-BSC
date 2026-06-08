"""Unit tests for src/team_database.py."""

import pytest
import pandas as pd

from src.team_database import load_teams, get_team, get_tier, get_group, get_strength


# ---------------------------------------------------------------------------
# load_teams
# ---------------------------------------------------------------------------

class TestLoadTeams:
    def test_returns_dataframe(self):
        assert isinstance(load_teams(), pd.DataFrame)

    def test_48_teams(self):
        assert len(load_teams()) == 48

    def test_12_per_tier(self):
        df = load_teams()
        for tier in (1, 2, 3, 4):
            count = int((df["Tier"] == tier).sum())
            assert count == 12, f"Tier {tier}: expected 12, got {count}"

    def test_no_duplicate_teams(self):
        df = load_teams()
        assert not df["Team"].duplicated().any()

    def test_required_columns(self):
        required = {"Team", "FIFARank", "Group", "Participations", "Tier", "StrengthScore"}
        assert required.issubset(set(load_teams().columns))

    def test_strength_equals_101_minus_rank(self):
        df = load_teams()
        assert (df["StrengthScore"] == 101 - df["FIFARank"]).all()

    def test_tiers_ordered_by_rank(self):
        df = load_teams()
        for lower, upper in ((1, 2), (2, 3), (3, 4)):
            max_lower = df[df["Tier"] == lower]["FIFARank"].max()
            min_upper = df[df["Tier"] == upper]["FIFARank"].min()
            assert max_lower < min_upper, (
                f"Tier {lower} max rank {max_lower} >= Tier {upper} min rank {min_upper}"
            )

    def test_returns_cached_object(self):
        assert load_teams() is load_teams()

    def test_all_groups_valid(self):
        valid_groups = set("ABCDEFGHIJKL")
        df = load_teams()
        assert set(df["Group"].unique()).issubset(valid_groups)

    def test_all_tiers_valid(self):
        df = load_teams()
        assert set(df["Tier"].unique()) == {1, 2, 3, 4}


# ---------------------------------------------------------------------------
# get_team
# ---------------------------------------------------------------------------

class TestGetTeam:
    def test_france_rank_1(self):
        row = get_team("France")
        assert row["FIFARank"] == 1

    def test_france_tier_1(self):
        assert get_team("France")["Tier"] == 1

    def test_france_strength_100(self):
        assert get_team("France")["StrengthScore"] == 100

    def test_new_zealand_rank_85(self):
        row = get_team("New Zealand")
        assert row["FIFARank"] == 85

    def test_new_zealand_tier_4(self):
        assert get_team("New Zealand")["Tier"] == 4

    def test_colombia_tier_1(self):
        # Rank 13, position 12 in sorted list → Tier 1
        row = get_team("Colombia")
        assert row["Tier"] == 1

    def test_senegal_tier_2(self):
        # Rank 14, position 13 → Tier 2
        assert get_team("Senegal")["Tier"] == 2

    def test_unknown_team_raises_key_error(self):
        with pytest.raises(KeyError):
            get_team("Atlantis FC")

    def test_case_sensitive(self):
        with pytest.raises(KeyError):
            get_team("france")

    def test_returns_series(self):
        assert isinstance(get_team("Germany"), pd.Series)


# ---------------------------------------------------------------------------
# get_tier
# ---------------------------------------------------------------------------

class TestGetTier:
    def test_each_tier_has_12_teams(self):
        for tier in (1, 2, 3, 4):
            assert len(get_tier(tier)) == 12

    def test_tier_1_contains_france(self):
        assert "France" in get_tier(1)["Team"].values

    def test_tier_4_contains_new_zealand(self):
        assert "New Zealand" in get_tier(4)["Team"].values

    def test_sorted_by_fifa_rank(self):
        for tier in (1, 2, 3, 4):
            ranks = get_tier(tier)["FIFARank"].tolist()
            assert ranks == sorted(ranks), f"Tier {tier} not sorted by FIFARank"

    def test_returns_dataframe(self):
        assert isinstance(get_tier(1), pd.DataFrame)

    def test_invalid_tier_zero(self):
        with pytest.raises(ValueError):
            get_tier(0)

    def test_invalid_tier_five(self):
        with pytest.raises(ValueError):
            get_tier(5)

    def test_invalid_tier_negative(self):
        with pytest.raises(ValueError):
            get_tier(-1)


# ---------------------------------------------------------------------------
# get_group
# ---------------------------------------------------------------------------

class TestGetGroup:
    def test_each_group_has_4_teams(self):
        for group in "ABCDEFGHIJKL":
            result = get_group(group)
            assert len(result) == 4, f"Group {group}: expected 4, got {len(result)}"

    def test_lowercase_normalised(self):
        upper = get_group("A")["Team"].tolist()
        lower = get_group("a")["Team"].tolist()
        assert upper == lower

    def test_sorted_by_fifa_rank(self):
        for group in "ABCDEFGHIJKL":
            ranks = get_group(group)["FIFARank"].tolist()
            assert ranks == sorted(ranks), f"Group {group} not sorted"

    def test_unknown_group_raises_key_error(self):
        with pytest.raises(KeyError):
            get_group("Z")

    def test_returns_dataframe(self):
        assert isinstance(get_group("A"), pd.DataFrame)


# ---------------------------------------------------------------------------
# get_strength
# ---------------------------------------------------------------------------

class TestGetStrength:
    def test_france_100(self):
        assert get_strength("France") == 100

    def test_spain_99(self):
        assert get_strength("Spain") == 99

    def test_new_zealand_16(self):
        assert get_strength("New Zealand") == 16

    def test_colombia_88(self):
        # Rank 13 → 101 - 13 = 88
        assert get_strength("Colombia") == 88

    def test_returns_int(self):
        assert isinstance(get_strength("Germany"), int)

    def test_unknown_team_raises_key_error(self):
        with pytest.raises(KeyError):
            get_strength("Atlantis FC")

    def test_matches_csv_value(self):
        df = load_teams()
        for _, row in df.iterrows():
            assert get_strength(row["Team"]) == row["StrengthScore"]
