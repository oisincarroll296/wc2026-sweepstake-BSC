"""Tournament Bracket — group draw + full knockout bracket with match cards."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

from datetime import datetime

import streamlit as st

from dashboard.data import (
    get_match_stats, get_assignments, get_tier_map, get_teams,
    get_fixtures, get_match_results,
)
from dashboard.config import TIER_COLORS
from dashboard.components.ui import page_header, empty_state

page_header("🏟️ Tournament Bracket", "Group draw · Full knockout bracket")

match_stats  = get_match_stats()
assignments  = get_assignments()
tier_map     = get_tier_map()
teams_df     = get_teams()
fixtures_df  = get_fixtures()
results_df   = get_match_results()

# ── Shared lookups ─────────────────────────────────────────────────────────────
_owner_map: dict[str, list[str]] = {}
for player, teams_list in assignments.items():
    for team in teams_list:
        _owner_map.setdefault(team, []).append(player)

TIER_LABELS = {1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4"}

# Tier colour legend
_leg = st.columns(4)
for i, (tier, label) in enumerate(TIER_LABELS.items()):
    clr = TIER_COLORS.get(tier, "#9CA3AF")
    with _leg[i]:
        st.markdown(
            f'<span style="background:{clr};color:#fff;border-radius:4px;'
            f'padding:3px 10px;font-size:0.75rem;font-weight:700">{label}</span>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Knockout data structures ───────────────────────────────────────────────────
fixtures_by_num: dict[int, dict] = {
    int(r["match_number"]): r.to_dict()
    for _, r in fixtures_df.iterrows()
}
ko_fixtures: dict[int, dict] = {
    mn: f for mn, f in fixtures_by_num.items() if mn >= 73
}

# Build winner / loser / score maps from results
winner_of: dict[int, str] = {}
loser_of:  dict[int, str] = {}
result_scores: dict[int, tuple] = {}   # mn -> (hg, ag, penalty_winner_or_None)

for _, res in results_df.iterrows():
    mn = int(res["match_number"])
    if mn < 73:
        continue
    fix = ko_fixtures.get(mn)
    if fix is None:
        continue
    home = str(fix["home_team"])
    away = str(fix["away_team"])
    hg   = int(res["home_goals"])
    ag   = int(res["away_goals"])
    pw   = res.get("penalty_winner", "")
    pw   = str(pw) if pw and str(pw) not in ("nan", "None", "") else None

    result_scores[mn] = (hg, ag, pw)

    if pw == home:
        winner_of[mn], loser_of[mn] = home, away
    elif pw == away:
        winner_of[mn], loser_of[mn] = away, home
    elif hg > ag:
        winner_of[mn], loser_of[mn] = home, away
    elif ag > hg:
        winner_of[mn], loser_of[mn] = away, home


def _resolve(ref: str) -> tuple[str | None, str]:
    """Return (actual_team_or_None, display_label).

    actual_team is non-None only when the team name is fully resolved.
    display_label is e.g. 'Germany', 'W74', 'L101'.
    """
    ref = str(ref or "").strip()
    if not ref or ref in ("nan", "None"):
        return None, "TBD"
    if ref.startswith("Winner match "):
        mn = int(ref.split()[-1])
        if mn in winner_of:
            t = winner_of[mn]
            return t, t
        return None, f"W{mn}"
    if ref.startswith("Runner-up match "):
        mn = int(ref.split()[-1])
        if mn in loser_of:
            t = loser_of[mn]
            return t, t
        return None, f"L{mn}"
    return ref, ref  # already a real team name


def _fmt_date(date_str: str) -> str:
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        day = d.strftime("%d").lstrip("0") or "0"
        return f"{day} {d.strftime('%b')}"
    except Exception:
        return str(date_str)


def _team_slot(team: str | None, label: str, won: bool, played: bool) -> str:
    if team:
        tier   = tier_map.get(team, 1)
        bg     = TIER_COLORS.get(tier, "#1E2937")
        owners = _owner_map.get(team, [])
        owner_txt = " · ".join(owners) if owners else "—"
        op = "1" if (not played or won) else "0.35"
        return (
            f'<div style="background:{bg}22;border-left:3px solid {bg};border-radius:4px;'
            f'padding:0.3rem 0.55rem;margin:0.12rem 0;opacity:{op}">'
            f'<div style="color:#F1F5F9;font-weight:700;font-size:0.8rem">{team}</div>'
            f'<div style="color:#94A3B8;font-size:0.58rem">{owner_txt}</div>'
            f'</div>'
        )
    return (
        f'<div style="background:#111827;border-left:3px solid #374151;border-radius:4px;'
        f'padding:0.3rem 0.55rem;margin:0.12rem 0">'
        f'<div style="color:#4B5563;font-size:0.8rem">{label}</div>'
        f'</div>'
    )


def _match_card(mn: int) -> str:
    fix = ko_fixtures.get(mn)
    if fix is None:
        return ""

    home_team, home_label = _resolve(str(fix["home_team"]))
    away_team, away_label = _resolve(str(fix["away_team"]))
    date_label = _fmt_date(str(fix.get("match_date", "")))

    played = mn in result_scores
    home_won = away_won = False
    mid_html = '<div style="text-align:center;color:#374151;font-size:0.68rem;margin:0.12rem 0">vs</div>'

    if played:
        hg, ag, pw = result_scores[mn]
        home_won = winner_of.get(mn) == home_team
        away_won = winner_of.get(mn) == away_team
        score_label = f"{hg} – {ag}"
        suffix = " <span style='font-size:0.58rem;color:#94A3B8'>(pens)</span>" if pw else ""
        mid_html = (
            f'<div style="text-align:center;color:#D4A017;font-weight:700;'
            f'font-size:0.82rem;margin:0.12rem 0">{score_label}{suffix}</div>'
        )

    return (
        f'<div style="border:1px solid #1E3A5F;border-radius:6px;padding:0.5rem 0.6rem;'
        f'background:#0D1B2A;margin-bottom:0.45rem">'
        f'<div style="color:#4B5563;font-size:0.6rem;margin-bottom:0.28rem">'
        f'Match {mn} &nbsp;·&nbsp; {date_label}</div>'
        f'{_team_slot(home_team, home_label, home_won, played)}'
        f'{mid_html}'
        f'{_team_slot(away_team, away_label, away_won, played)}'
        f'</div>'
    )


def _team_card(team: str, compact: bool = False) -> str:
    tier   = tier_map.get(team, 1)
    bg     = TIER_COLORS.get(tier, "#1E2937")
    owners = _owner_map.get(team, [])
    owner_txt = "  ·  ".join(owners) if owners else "—"
    pad = "0.3rem 0.6rem" if compact else "0.4rem 0.7rem"
    return (
        f'<div style="background:{bg}22;border-left:4px solid {bg};border-radius:4px;'
        f'padding:{pad};margin-bottom:0.3rem">'
        f'<div style="color:#F1F5F9;font-weight:700;font-size:{"0.82rem" if compact else "0.9rem"}">{team}</div>'
        f'<div style="color:#94A3B8;font-size:0.62rem;margin-top:1px">{owner_txt}</div>'
        f'</div>'
    )


def _elim_wrap(card_html: str) -> str:
    return (
        '<div style="position:relative;opacity:0.55">'
        f'{card_html}'
        '<div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;'
        'align-items:center;justify-content:flex-end;padding-right:0.5rem;pointer-events:none">'
        '<span style="color:#EF4444;font-size:2rem;font-weight:900;line-height:1;opacity:0.9">X</span>'
        '</div>'
        '</div>'
    )


# ── Check whether group stage is done ─────────────────────────────────────────
_group_stage_done = False
if not match_stats.empty:
    elim_count = (match_stats["RoundReached"] == "GroupStage").sum()
    _group_stage_done = elim_count >= 16

_any_ko = bool(ko_fixtures) and _group_stage_done

# ── Bracket structure: (label, match_numbers, columns) ────────────────────────
KO_STRUCTURE = [
    ("Round of 32",       list(range(73, 89)),   4),
    ("Round of 16",       list(range(89, 97)),   4),
    ("Quarter-Finals",    list(range(97, 101)),  4),
    ("Semi-Finals",       list(range(101, 103)), 2),
    ("3rd Place Playoff", [103],                 1),
    ("Final",             [104],                 1),
]

tab_group, tab_ko = st.tabs(["Group Stage Draw", "Knockout Bracket"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GROUP STAGE DRAW
# ══════════════════════════════════════════════════════════════════════════════
with tab_group:
    if teams_df.empty:
        empty_state("No team data available.")
    else:
        groups: dict[str, list] = {}
        for _, row in teams_df.iterrows():
            g = str(row.get("Group", "")).strip()
            if g and g.lower() not in ("nan", ""):
                groups.setdefault(g, []).append(row)

        if not groups:
            empty_state("Group assignments not available yet.")
        else:
            group_letters = sorted(groups.keys())
            for row_start in range(0, len(group_letters), 3):
                cols = st.columns(3)
                for ci, g in enumerate(group_letters[row_start:row_start + 3]):
                    with cols[ci]:
                        st.markdown(
                            f'<div style="color:#D4A017;font-weight:700;font-size:0.95rem;'
                            f'border-bottom:1px solid #2A3A4A;padding-bottom:0.2rem;'
                            f'margin-bottom:0.4rem">Group {g}</div>',
                            unsafe_allow_html=True,
                        )
                        team_rows = sorted(groups[g], key=lambda r: int(r.get("Tier", 4)))
                        for r in team_rows:
                            team = str(r["Team"])
                            rnd = ""
                            if not match_stats.empty:
                                ms_row = match_stats[match_stats["Team"] == team]
                                if not ms_row.empty:
                                    rnd = str(ms_row.iloc[0].get("RoundReached", "") or "").strip()
                            card = _team_card(team, compact=True)
                            if rnd == "GroupStage":
                                card = _elim_wrap(card)
                            st.markdown(card, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — KNOCKOUT BRACKET
# ══════════════════════════════════════════════════════════════════════════════
with tab_ko:
    if not _any_ko:
        st.info("Knockout bracket will populate once the group stage is complete.")
    else:
        for round_label, match_nums, n_cols in KO_STRUCTURE:
            st.markdown(f"### {round_label}")

            if n_cols == 1:
                _, mid_col, _ = st.columns([1, 2, 1])
                with mid_col:
                    st.markdown(_match_card(match_nums[0]), unsafe_allow_html=True)
            else:
                rows = [match_nums[i : i + n_cols] for i in range(0, len(match_nums), n_cols)]
                for row_mns in rows:
                    cols = st.columns(n_cols)
                    for ci, mn in enumerate(row_mns):
                        with cols[ci]:
                            st.markdown(_match_card(mn), unsafe_allow_html=True)

            st.markdown("")
