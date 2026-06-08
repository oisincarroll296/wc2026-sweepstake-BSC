"""Team Ownership — who owns what across the field."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import (
    get_team_ownership_data, get_match_stats, get_tier_map, get_teams,
)
from dashboard.config import TIER_COLORS
from dashboard.components.ui import page_header, empty_state, searchable_table


page_header("⚽ Team Ownership", "Every team — owners, captains, and dark horse pickers")

ownership = get_team_ownership_data()
match_stats = get_match_stats()
tier_map    = get_tier_map()
teams_df    = get_teams()

if not ownership:
    empty_state("No draw completed yet.")
    st.stop()

# Compute current team points
from src.scoring_engine import calculate_team_points

def _team_pts_breakdown(team: str) -> dict:
    if match_stats.empty:
        return {"group_stage": 0.0, "knockout": 0.0, "total": 0.0}
    tier = tier_map.get(team, 1)
    return calculate_team_points(team, match_stats, tier)

# Summary table
rows = []
group_map = dict(zip(teams_df["Team"], teams_df["Group"])) if not teams_df.empty else {}

for team, data in sorted(ownership.items()):
    tier = tier_map.get(team, 0)
    bp   = _team_pts_breakdown(team)
    rows.append({
        "Team":       team,
        "Tier":       f"T{tier}" if tier else "—",
        "Group":      group_map.get(team, "—"),
        "Owners":     ", ".join(sorted(data["owners"])) or "—",
        "Pre Cap":    ", ".join(sorted(data["pre_captains"])) or "—",
        "KO Cap":     ", ".join(sorted(data["knockout_captains"])) or "—",
        "Dark Horse": ", ".join(sorted(data["dark_horse_pickers"])) or "—",
        "Grp Pts":    f"{bp['group_stage']:.0f}",
        "KO Pts":     f"{bp['knockout']:.0f}",
        "Total":      f"{bp['total']:.0f}",
    })

all_df = pd.DataFrame(rows)

# Filter by tier
tiers = ["All"] + [f"Tier {i}" for i in range(1, 5)]
tier_filter = st.selectbox("Filter by Tier", tiers)
if tier_filter != "All":
    t_num = tier_filter[-1]
    filtered = all_df[all_df["Tier"] == f"T{t_num}"]
else:
    filtered = all_df

st.caption(
    "**Grp Pts** = goals, clean sheets, bonuses from the group stage. "
    "**KO Pts** = knockout stats + progression bonuses (R16 onward). "
    "**Total** = team points only — Dark Horse bonuses go to the picker's leaderboard total, not counted here."
)
searchable_table(filtered, "Search teams, owners, dark horses…")

st.divider()

# ── Team Detail ────────────────────────────────────────────────────────────
st.subheader("🔍 Team Detail")
team_names = sorted(ownership.keys())
selected = st.selectbox("Select Team", team_names, key="team_detail")

if selected:
    data = ownership[selected]
    tier = tier_map.get(selected, 1)
    grp  = group_map.get(selected, "—")
    bp   = _team_pts_breakdown(selected)

    st.markdown(
        f'<div class="card-gold">'
        f'<h3 style="margin:0;color:#D4A017">{selected}</h3>'
        f'<p style="color:#9CA3AF;margin:0.25rem 0 0">Tier {tier} · Group {grp}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.metric("Group Stage Pts", f"{bp['group_stage']:.0f}")
    with pc2:
        st.metric("Knockout Pts", f"{bp['knockout']:.0f}")
    with pc3:
        st.metric("Total Team Pts", f"{bp['total']:.0f}")

    if data.get("dark_horse_pickers"):
        st.info(
            f"Dark Horse picked by: **{', '.join(sorted(data['dark_horse_pickers']))}** — "
            "their dark horse bonus is scored separately and added to their personal leaderboard total."
        )

    dc1, dc2 = st.columns(2)
    with dc1:
        st.markdown("**Owners**")
        for o in sorted(data["owners"]) or ["—"]:
            st.markdown(f"- {o}")
        st.markdown("**Pre-Tournament Captains**")
        for o in sorted(data["pre_captains"]) or ["—"]:
            st.markdown(f"- {o}")
    with dc2:
        st.markdown("**Knockout Captains**")
        for o in sorted(data["knockout_captains"]) or ["—"]:
            st.markdown(f"- {o}")
        st.markdown("**Dark Horse Pickers**")
        for o in sorted(data["dark_horse_pickers"]) or ["—"]:
            st.markdown(f"- {o}")
