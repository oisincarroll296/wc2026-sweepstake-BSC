"""Tournament Bracket — group draw + knockout survivors coloured by tier."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from dashboard.data import get_match_stats, get_assignments, get_tier_map, get_teams
from dashboard.config import TIER_COLORS
from dashboard.components.ui import page_header, empty_state

page_header("🏟️ Tournament Bracket", "Group draw · Knockout survivors coloured by tier")

match_stats = get_match_stats()
assignments = get_assignments()
tier_map    = get_tier_map()
teams_df    = get_teams()

# Map team → all owners
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

KO_ROUNDS = ["R16", "QF", "SF", "Final", "Winner"]
ROUND_LABELS = {
    "R16":    "Round of 16",
    "QF":     "Quarter-Finals",
    "SF":     "Semi-Finals",
    "Final":  "Final",
    "Winner": "Winner 🏆",
}


def _team_card(team: str, compact: bool = False) -> str:
    tier  = tier_map.get(team, 1)
    bg    = TIER_COLORS.get(tier, "#1E2937")
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


# ── Check for knockout data ────────────────────────────────────────────────────
_by_round: dict[str, list[str]] = {r: [] for r in KO_ROUNDS}
if not match_stats.empty:
    for _, row in match_stats.iterrows():
        team = str(row.get("Team", ""))
        rnd  = str(row.get("RoundReached", "") or "").strip()
        if rnd in KO_ROUNDS:
            _by_round[rnd].append(team)

_any_ko = any(_by_round[r] for r in KO_ROUNDS)

tab_group, tab_ko = st.tabs(["Group Stage Draw", "Knockout Bracket"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GROUP STAGE DRAW
# ══════════════════════════════════════════════════════════════════════════════
with tab_group:
    if teams_df.empty:
        empty_state("No team data available.")
    else:
        # Build group → teams map
        groups: dict[str, list] = {}
        for _, row in teams_df.iterrows():
            g = str(row.get("Group", "")).strip()
            if g and g.lower() not in ("nan", ""):
                groups.setdefault(g, []).append(row)

        if not groups:
            empty_state("Group assignments not available yet.")
        else:
            group_letters = sorted(groups.keys())
            # Show 3 groups per row
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
                            # Show RoundReached badge if available
                            rnd = ""
                            if not match_stats.empty:
                                ms_row = match_stats[match_stats["Team"] == team]
                                if not ms_row.empty:
                                    rnd = str(ms_row.iloc[0].get("RoundReached", "") or "").strip()
                            elim = rnd == "GroupStage"
                            opacity = "opacity:0.45;" if elim else ""
                            card = _team_card(team, compact=True)
                            # Wrap with opacity for eliminated teams
                            if elim:
                                card = card.replace(
                                    'margin-bottom:0.3rem"',
                                    f'margin-bottom:0.3rem;{opacity}"',
                                )
                            st.markdown(card, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — KNOCKOUT BRACKET
# ══════════════════════════════════════════════════════════════════════════════
with tab_ko:
    if not _any_ko:
        st.info("Knockout bracket will populate once the group stage is complete.")
    else:
        for rnd in reversed(KO_ROUNDS):
            teams_in_round = _by_round[rnd]
            if not teams_in_round:
                continue
            label = ROUND_LABELS.get(rnd, rnd)
            st.markdown(f"### {label}")
            n_cols = min(len(teams_in_round), 4)
            cols   = st.columns(n_cols) if n_cols > 1 else [st.container()]
            for i, team in enumerate(sorted(teams_in_round)):
                with cols[i % n_cols]:
                    st.markdown(_team_card(team), unsafe_allow_html=True)
            st.markdown("")
