"""Groups — group stage overview: teams, ownership, standings, fixtures."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import date, timedelta

from dashboard.data import get_teams, get_assignments, get_match_stats, get_fixtures, get_match_results
from dashboard.components.ui import page_header

_ROOT = Path(__file__).parent.parent.parent

TIER_COLORS = {1: "#105AAC", 2: "#15803D", 3: "#A16207", 4: "#B91C1C"}
TIER_LABELS = {1: "T1", 2: "T2", 3: "T3", 4: "T4"}


page_header("Groups", "Group stage — teams, ownership, and fixtures")

teams_df    = get_teams()
assignments = get_assignments()
stats_df    = get_match_stats()
fixtures_df = get_fixtures()
results_df  = get_match_results()

# ── Build lookup maps ───────────────────────────────────────────────────────
ownership: dict[str, list[str]] = {}
for player, teams in assignments.items():
    for team in teams:
        ownership.setdefault(team, []).append(player)

goals_map: dict[str, int] = {}
if not stats_df.empty and "GroupGoals" in stats_df.columns:
    for _, row in stats_df.iterrows():
        goals_map[str(row["Team"])] = int(float(row.get("GroupGoals", 0) or 0))

# ── Build group → team list ─────────────────────────────────────────────────
groups: dict[str, list] = {}
for _, row in teams_df.iterrows():
    g = str(row.get("Group", "")).strip()
    if g and g.lower() != "nan":
        groups.setdefault(g, []).append(row)

tab_groups, tab_standings, tab_fixtures = st.tabs(["Groups", "Standings", "Fixtures"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GROUPS
# ══════════════════════════════════════════════════════════════════════════════
with tab_groups:
    group_letters = sorted(groups.keys())

    # 3 columns of groups
    for row_start in range(0, len(group_letters), 3):
        cols = st.columns(3)
        for i, g in enumerate(group_letters[row_start:row_start + 3]):
            with cols[i]:
                st.markdown(
                    f'<div style="color:#D4A017;font-weight:700;font-size:1rem;'
                    f'border-bottom:1px solid #2A3A4A;padding-bottom:0.2rem;margin-bottom:0.4rem">'
                    f'Group {g}</div>',
                    unsafe_allow_html=True,
                )
                team_rows = sorted(groups[g], key=lambda r: int(r.get("Tier", 4)))
                for r in team_rows:
                    team  = str(r["Team"])
                    tier  = int(r.get("Tier", 4))
                    color = TIER_COLORS.get(tier, "#9CA3AF")
                    label = TIER_LABELS.get(tier, "T?")
                    owners = ownership.get(team, [])
                    goals  = goals_map.get(team, 0)
                    owner_str = ", ".join(owners) if owners else "Unowned"
                    owner_col = "#9CA3AF" if not owners else "#6EE7B7"
                    goals_html = (
                        f'<span style="color:#D4A017;font-size:0.7rem;margin-left:0.3rem">⚽{goals}</span>'
                        if goals > 0 else ""
                    )
                    st.markdown(
                        f'<div style="border-left:3px solid {color};padding:0.25rem 0.5rem;'
                        f'margin:0.2rem 0;background:#1E2937;border-radius:0 5px 5px 0">'
                        f'<span style="color:{color};font-size:0.65rem;font-weight:700;'
                        f'background:{color}22;border-radius:3px;padding:0 3px">{label}</span> '
                        f'<span style="color:#F5F5F5;font-size:0.82rem;font-weight:600">{team}</span>'
                        f'{goals_html}'
                        f'<div style="color:{owner_col};font-size:0.7rem;margin-top:0.05rem">'
                        f'{owner_str}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — STANDINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_standings:
    _ROUND_RANK = {"": -1, "GroupStage": 0, "R16": 1, "QF": 2, "SF": 3, "Final": 4, "Winner": 5}
    _ROUND_LABEL = {
        "": "—", "GroupStage": "Group Stage",
        "R16": "Reached R16", "QF": "Reached QF",
        "SF": "Semi-Final", "Final": "Runner-Up", "Winner": "Champion",
    }

    grp_map = {
        str(r["Team"]): str(r.get("Group", "")).strip()
        for _, r in teams_df.iterrows()
    }
    tier_map_local = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in teams_df.iterrows()}

    if stats_df.empty:
        st.info("Group standings will appear here once match data is available.")
    else:
        rows_s = []
        for _, row in stats_df.iterrows():
            team = str(row["Team"])
            grp  = grp_map.get(team, "")
            if not grp or grp.lower() == "nan":
                continue
            rnd  = str(row.get("RoundReached", "") or "").strip()
            gw   = int(float(row.get("GroupWinner", 0) or 0))
            gf   = int(float(row.get("GroupGoals", 0) or 0))
            gcs  = int(float(row.get("GroupCleanSheets", 0) or 0))
            rows_s.append({
                "Group": grp, "Team": team,
                "GF": gf, "CS": gcs, "GW": gw,
                "RoundReached": rnd,
                "_rr": _ROUND_RANK.get(rnd, -1),
                "_tier": tier_map_local.get(team, 4),
            })

        stand_df = pd.DataFrame(rows_s)
        for g_letter in sorted(stand_df["Group"].unique()):
            grp_df = (
                stand_df[stand_df["Group"] == g_letter]
                .sort_values(["GW", "_rr", "GF"], ascending=[False, False, False])
                .reset_index(drop=True)
            )
            st.markdown(
                f'<div style="color:#D4A017;font-weight:700;font-size:0.95rem;'
                f'margin:1rem 0 0.3rem;border-bottom:1px solid #2A3A4A;padding-bottom:0.15rem">'
                f'Group {g_letter}</div>',
                unsafe_allow_html=True,
            )
            for pos, (_, r) in enumerate(grp_df.iterrows(), 1):
                team  = r["Team"]
                tier  = r["_tier"]
                color = TIER_COLORS.get(tier, "#9CA3AF")
                rnd   = r["RoundReached"]
                rnd_label = _ROUND_LABEL.get(rnd, rnd)
                gw_badge  = (
                    '<span style="background:#D4A01722;color:#D4A017;font-size:0.62rem;'
                    'border-radius:3px;padding:1px 4px;margin-left:0.3rem">Group Winner</span>'
                    if r["GW"] else ""
                )
                pos_col = "#D4A017" if pos == 1 else ("#6EE7B7" if pos == 2 else "#9CA3AF")
                rnd_col = "#6EE7B7" if rnd and rnd != "GroupStage" else "#6B7280"
                owners = ownership.get(team, [])
                owner_html = (
                    f'<span style="color:#6EE7B7;font-size:0.65rem"> · {", ".join(owners)}</span>'
                    if owners else ""
                )
                st.markdown(
                    f'<div style="background:#1E2937;border-left:3px solid {color};'
                    f'border-radius:0 6px 6px 0;padding:0.3rem 0.6rem;margin:0.15rem 0;'
                    f'display:flex;justify-content:space-between;align-items:center">'
                    f'<div style="display:flex;align-items:center;gap:0.4rem">'
                    f'<span style="color:{pos_col};font-weight:700;font-size:0.8rem;min-width:1rem">{pos}</span>'
                    f'<span style="color:{color};font-size:0.62rem;font-weight:700;'
                    f'background:{color}22;border-radius:3px;padding:0 3px">T{tier}</span>'
                    f'<span style="color:#F5F5F5;font-weight:600;font-size:0.85rem">{team}</span>'
                    f'{gw_badge}{owner_html}'
                    f'</div>'
                    f'<div style="text-align:right">'
                    f'<span style="color:#D4A017;font-size:0.75rem;margin-right:0.6rem">⚽ {r["GF"]}  🧤 {r["CS"]}</span>'
                    f'<span style="color:{rnd_col};font-size:0.72rem">{rnd_label}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FIXTURES
# ══════════════════════════════════════════════════════════════════════════════
with tab_fixtures:
    if fixtures_df.empty:
        st.info("Fixture data not found.")
    else:
        all_owned = {t for ts in assignments.values() for t in ts} if assignments else set()
        tier_map_local = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in teams_df.iterrows()}

        # Entered match numbers → score lookup
        entered_nums: set = set()
        score_lookup: dict[int, tuple[int, int]] = {}
        if not results_df.empty and "match_number" in results_df.columns:
            for _, rr in results_df.iterrows():
                mn_r = int(pd.to_numeric(rr.get("match_number", 0), errors="coerce") or 0)
                if mn_r:
                    entered_nums.add(mn_r)
                    hg = int(float(rr.get("home_goals", 0) or 0))
                    ag = int(float(rr.get("away_goals", 0) or 0))
                    score_lookup[mn_r] = (hg, ag)

        viewer = st.session_state.get("viewer")
        viewer_teams: set = set(assignments.get(viewer, [])) if viewer else set()

        today = date.today()
        col1, col2 = st.columns([2, 1])
        with col1:
            days_ahead = st.slider("Show fixtures for next N days", 1, 30, 14)
        with col2:
            toggle_label = (
                f"Only {viewer}'s matches" if viewer else "Sweepstake matches only"
            )
            owned_only = st.toggle(
                toggle_label, value=False,
                disabled=(not viewer and not all_owned),
            )
        if owned_only and not viewer:
            st.caption("Select your name in the sidebar to filter to your teams.")

        cutoff = today + timedelta(days=days_ahead)
        mask = (
            fixtures_df["match_date"].notna()
            & (fixtures_df["match_date"] >= today)
            & (fixtures_df["match_date"] <= cutoff)
        )
        upcoming = fixtures_df[mask].copy()

        if upcoming.empty:
            st.info("No fixtures in the selected range.")
        else:
            filter_teams = viewer_teams if viewer else all_owned
            if owned_only and filter_teams:
                relevant = upcoming[
                    upcoming["home_team"].isin(filter_teams) | upcoming["away_team"].isin(filter_teams)
                ]
                upcoming = relevant if not relevant.empty else upcoming

            # Summary line
            sweepstake_count = int(
                upcoming["home_team"].isin(all_owned).sum() +
                upcoming[~upcoming["home_team"].isin(all_owned)]["away_team"].isin(all_owned).sum()
            ) if all_owned else 0
            total_count = len(upcoming)
            completed_count = sum(1 for mn in upcoming["match_number"].dropna().astype(int) if mn in entered_nums)
            st.markdown(
                f'<div style="color:#9CA3AF;font-size:0.8rem;margin-bottom:0.6rem">'
                f'{total_count} fixtures · {completed_count} completed · '
                f'{sweepstake_count} with sweepstake teams'
                f'</div>',
                unsafe_allow_html=True,
            )

            def _tier_badge(team: str) -> str:
                tier = tier_map_local.get(team, 0)
                if not tier:
                    return ""
                color = TIER_COLORS.get(tier, "#9CA3AF")
                return (
                    f'<span style="background:{color}33;color:{color};font-size:0.58rem;'
                    f'font-weight:700;border-radius:3px;padding:1px 4px;margin-right:3px">T{tier}</span>'
                )

            for match_date in sorted(upcoming["match_date"].unique()):
                day_matches = upcoming[upcoming["match_date"] == match_date]
                _ts = pd.Timestamp(match_date)
                is_today = match_date == today
                day_label = ("Today · " if is_today else "") + f"{_ts.day} {_ts.strftime('%b %Y')}"
                st.markdown(
                    f'<div style="color:#D4A017;font-weight:700;font-size:0.88rem;'
                    f'margin:0.9rem 0 0.35rem;border-bottom:1px solid #2A3A4A;padding-bottom:0.15rem">'
                    f'{day_label}</div>',
                    unsafe_allow_html=True,
                )
                for _, m in day_matches.iterrows():
                    home  = str(m.get("home_team", ""))
                    away  = str(m.get("away_team", ""))
                    grp   = str(m.get("group", "")).strip()
                    venue = str(m.get("venue", "")).strip()
                    mn    = int(pd.to_numeric(m["match_number"], errors="coerce") or 0)
                    done  = mn in entered_nums

                    home_owned = home in all_owned
                    away_owned = away in all_owned
                    home_owners = ", ".join(ownership.get(home, []))
                    away_owners = ", ".join(ownership.get(away, []))

                    # Score or VS
                    if done and mn in score_lookup:
                        hg, ag = score_lookup[mn]
                        mid_html = (
                            f'<div style="text-align:center;min-width:3.5rem">'
                            f'<span style="color:#6EE7B7;font-size:1rem;font-weight:800">'
                            f'{hg} – {ag}</span>'
                            f'<div style="color:#6EE7B7;font-size:0.58rem">FT</div>'
                            f'</div>'
                        )
                    else:
                        mid_html = (
                            f'<div style="text-align:center;min-width:3.5rem">'
                            f'<span style="color:#4B5563;font-size:0.85rem;font-weight:600">vs</span>'
                            f'</div>'
                        )

                    border_style = "border:1px solid #D4A017;" if (home_owned or away_owned) else "border:1px solid #2A3A4A;"
                    home_name_col = "#D4A017" if home_owned else "#F1F5F9"
                    away_name_col = "#D4A017" if away_owned else "#F1F5F9"

                    round_label = f"Group {grp}" if grp else "Knockout"
                    venue_short = venue.replace(" Stadium", "").replace("Estadio ", "") if venue else ""

                    home_owner_html = (
                        f'<div style="color:#6EE7B7;font-size:0.65rem;margin-top:2px">{home_owners}</div>'
                        if home_owners else '<div style="font-size:0.65rem"> </div>'
                    )
                    away_owner_html = (
                        f'<div style="color:#6EE7B7;font-size:0.65rem;margin-top:2px">{away_owners}</div>'
                        if away_owners else '<div style="font-size:0.65rem"> </div>'
                    )

                    st.markdown(
                        f'<div style="background:#1E2937;border-radius:7px;padding:0.55rem 0.8rem;'
                        f'margin:0.25rem 0;{border_style}">'
                        # top row: round label + venue
                        f'<div style="display:flex;justify-content:space-between;'
                        f'margin-bottom:0.35rem;align-items:center">'
                        f'<span style="color:#6B7280;font-size:0.65rem">{round_label}</span>'
                        f'<span style="color:#4B5563;font-size:0.63rem">{venue_short}</span>'
                        f'</div>'
                        # match row: home | score | away
                        f'<div style="display:flex;align-items:center;gap:0.5rem">'
                        # home side
                        f'<div style="flex:1;text-align:right">'
                        f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:4px">'
                        f'{_tier_badge(home)}'
                        f'<span style="color:{home_name_col};font-weight:700;font-size:0.88rem">{home}</span>'
                        f'</div>'
                        f'{home_owner_html}'
                        f'</div>'
                        # score / vs
                        f'{mid_html}'
                        # away side
                        f'<div style="flex:1;text-align:left">'
                        f'<div style="display:flex;align-items:center;gap:4px">'
                        f'<span style="color:{away_name_col};font-weight:700;font-size:0.88rem">{away}</span>'
                        f'{_tier_badge(away)}'
                        f'</div>'
                        f'{away_owner_html}'
                        f'</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
