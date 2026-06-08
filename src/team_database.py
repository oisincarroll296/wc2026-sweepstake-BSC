"""Team database for World Cup 2026 Sweepstake."""

import pandas as pd
from pathlib import Path

_CSV_PATH = Path(__file__).parent.parent / "data" / "teams.csv"
_EXPECTED_TEAMS = 48
_TIERS = (1, 2, 3, 4)
_TEAMS_PER_TIER = 12

_df: pd.DataFrame | None = None


def load_teams() -> pd.DataFrame:
    """Load the team database, validate it, and return it as a DataFrame.

    Cached after first load. Columns: Team, FIFARank, Group,
    Participations, Tier, StrengthScore.
    """
    global _df
    if _df is None:
        df = pd.read_csv(_CSV_PATH)
        _validate(df)
        _df = df
    return _df


def _validate(df: pd.DataFrame) -> None:
    if len(df) != _EXPECTED_TEAMS:
        raise ValueError(f"Expected {_EXPECTED_TEAMS} teams, got {len(df)}")

    dupes = df.loc[df["Team"].duplicated(keep=False), "Team"].unique().tolist()
    if dupes:
        raise ValueError(f"Duplicate team names: {dupes}")

    for tier in _TIERS:
        count = int((df["Tier"] == tier).sum())
        if count != _TEAMS_PER_TIER:
            raise ValueError(
                f"Tier {tier} has {count} teams, expected {_TEAMS_PER_TIER}"
            )


def get_team(name: str) -> pd.Series:
    """Return the row for a named team.

    Raises KeyError if the team does not exist.
    """
    df = load_teams()
    matches = df[df["Team"] == name]
    if matches.empty:
        raise KeyError(f"Team not found: {name!r}")
    return matches.iloc[0]


def get_tier(tier: int) -> pd.DataFrame:
    """Return all teams in *tier* (1–4), sorted by FIFARank ascending."""
    if tier not in _TIERS:
        raise ValueError(f"Tier must be one of {_TIERS}, got {tier!r}")
    df = load_teams()
    return (
        df[df["Tier"] == tier]
        .sort_values("FIFARank")
        .reset_index(drop=True)
    )


def get_group(group: str) -> pd.DataFrame:
    """Return all teams in *group* (A–L), sorted by FIFARank ascending.

    Accepts lower- or upper-case group letters.
    Raises KeyError if the group has no teams.
    """
    key = group.upper()
    df = load_teams()
    result = (
        df[df["Group"] == key]
        .sort_values("FIFARank")
        .reset_index(drop=True)
    )
    if result.empty:
        raise KeyError(f"Group not found: {group!r}")
    return result


def get_strength(name: str) -> int:
    """Return the StrengthScore (101 − FIFARank) for a named team."""
    return int(get_team(name)["StrengthScore"])
