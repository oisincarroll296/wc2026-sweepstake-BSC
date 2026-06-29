"""Teams — Groups, Standings, Fixtures, and Ownership in one place."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import streamlit as st
import pandas as pd
from datetime import date, timedelta

from dashboard.data import (
    get_teams, get_assignments, get_match_stats, get_fixtures,
    get_match_results, get_team_ownership_data, get_tier_map,
)
from dashboard.config import TIER_COLORS
from dashboard.components.ui import page_header, empty_state, searchable_table

page_header("Teams", "Groups · Standings · Fixtures · Ownership")

teams_df    = get_teams()
assignments = get_assignments()
stats_df    = get_match_stats()
fixtures_df = get_fixtures()
results_df  = get_match_results()
tier_map    = get_tier_map()

TIER_LABELS = {1: "T1", 2: "T2", 3: "T3", 4: "T4"}

# Lookup maps used across tabs
ownership_map: dict[str, list[str]] = {}
for _player, _teams in assignments.items():
    for _t in _teams:
        ownership_map.setdefault(_t, []).append(_player)

goals_map: dict[str, int] = {}
if not stats_df.empty and "GroupGoals" in stats_df.columns:
    for _, _row in stats_df.iterrows():
        goals_map[str(_row["Team"])] = int(float(_row.get("GroupGoals", 0) or 0))

groups: dict[str, list] = {}
for _, _row in teams_df.iterrows():
    g = str(_row.get("Group", "")).strip()
    if g and g.lower() != "nan":
        groups.setdefault(g, []).append(_row)

group_map = dict(zip(teams_df["Team"], teams_df["Group"])) if not teams_df.empty else {}

tab_groups, tab_standings, tab_fixtures, tab_results, tab_ownership = st.tabs([
    "Groups", "Standings", "Fixtures", "Results", "Ownership",
])

# ═══════════════════════════════════════════════════════════════════
# TAB 1 — GROUPS
# ═══════════════════════════════════════════════════════════════════
with tab_groups:
    # Build set of all eliminated teams (group stage + KO losers)
    eliminated_gs: set[str] = set()
    if not stats_df.empty and "RoundReached" in stats_df.columns:
        eliminated_gs = set(
            stats_df[stats_df["RoundReached"] == "GroupStage"]["Team"].tolist()
        )
    # Add teams knocked out in KO rounds
    if not results_df.empty and "match_number" in results_df.columns and not fixtures_df.empty:
        for _, _kr in results_df.iterrows():
            _kmn = int(pd.to_numeric(_kr.get("match_number", 0), errors="coerce") or 0)
            if _kmn < 73 or _kmn == 103:   # skip group stage and 3rd-place
                continue
            _kfix = fixtures_df[fixtures_df["match_number"] == _kmn]
            if _kfix.empty:
                continue
            _kf  = _kfix.iloc[0]
            _kh  = str(_kf["home_team"]); _ka = str(_kf["away_team"])
            _khg = int(float(_kr.get("home_goals", 0) or 0))
            _kag = int(float(_kr.get("away_goals", 0) or 0))
            _kpw = str(_kr.get("penalty_winner", "") or "").strip()
            if _kpw == _kh or (not _kpw and _khg > _kag):
                eliminated_gs.add(_ka)
            elif _kpw == _ka or (not _kpw and _kag > _khg):
                eliminated_gs.add(_kh)

    group_letters = sorted(groups.keys())
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
                for r in sorted(groups[g], key=lambda x: int(x.get("Tier", 4))):
                    team   = str(r["Team"])
                    tier   = int(r.get("Tier", 4))
                    color  = TIER_COLORS.get(tier, "#9CA3AF")
                    label  = TIER_LABELS.get(tier, "T?")
                    owners = ownership_map.get(team, [])
                    goals  = goals_map.get(team, 0)
                    owner_str = ", ".join(owners) if owners else "Unowned"
                    owner_col = "#9CA3AF" if not owners else "#6EE7B7"
                    goals_html = (
                        f'<span style="color:#D4A017;font-size:0.7rem;margin-left:0.3rem">⚽{goals}</span>'
                        if goals > 0 else ""
                    )
                    elim = team in eliminated_gs
                    x_overlay = (
                        '<div style="position:absolute;top:0;left:0;right:0;bottom:0;'
                        'display:flex;align-items:center;justify-content:flex-end;'
                        'padding-right:0.4rem;pointer-events:none">'
                        '<span style="color:#EF4444;font-size:2rem;font-weight:900;'
                        'line-height:1;opacity:0.85">✕</span></div>'
                        if elim else ""
                    )
                    outer_style = "position:relative;opacity:0.55;" if elim else "position:relative;"
                    st.markdown(
                        f'<div style="{outer_style}">'
                        f'<div style="border-left:3px solid {color};padding:0.25rem 0.5rem;'
                        f'margin:0.2rem 0;background:#1E2937;border-radius:0 5px 5px 0">'
                        f'<span style="color:{color};font-size:0.65rem;font-weight:700;'
                        f'background:{color}22;border-radius:3px;padding:0 3px">{label}</span> '
                        f'<span style="color:#F5F5F5;font-size:0.82rem;font-weight:600">{team}</span>'
                        f'{goals_html}'
                        f'<div style="color:{owner_col};font-size:0.7rem;margin-top:0.05rem">'
                        f'{owner_str}</div>'
                        f'</div>'
                        f'{x_overlay}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

# ═══════════════════════════════════════════════════════════════════
# TAB 2 — STANDINGS
# ═══════════════════════════════════════════════════════════════════
with tab_standings:
    _ROUND_RANK = {
        "": -1, "GroupStage": 0, "R32": 1, "R16": 2,
        "QF": 3, "SF": 4, "Final": 5, "Winner": 6,
    }
    _ROUND_LABEL = {
        "": "—", "GroupStage": "Eliminated",
        "R32": "R32", "R16": "R16",
        "QF": "Quarter-Final", "SF": "Semi-Final",
        "Final": "Runner-Up", "Winner": "Champion",
    }
    tier_map_local = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in teams_df.iterrows()}

    if stats_df.empty:
        st.info("Standings will appear once match data is entered.")
    else:
        from src.scoring_engine import calculate_team_points as _ctp_s

        # Build per-team match record (P/W/D/L/GF/GA) from match_results
        _team_rec: dict[str, dict] = {}
        if not results_df.empty and "home_team" in results_df.columns:
            for _, _rr in results_df.iterrows():
                _h = str(_rr.get("home_team", "") or "")
                _a = str(_rr.get("away_team", "") or "")
                _g = str(_rr.get("group", "") or "").strip()
                if not _h or not _a or not _g:
                    continue  # skip knockout matches
                _hg = int(float(_rr.get("home_goals", 0) or 0))
                _ag = int(float(_rr.get("away_goals", 0) or 0))
                for _team, _gf, _ga in [(_h, _hg, _ag), (_a, _ag, _hg)]:
                    if _team not in _team_rec:
                        _team_rec[_team] = {"Played": 0, "Won": 0, "Drew": 0, "Lost": 0, "Scored": 0, "Against": 0}
                    _team_rec[_team]["Played"]  += 1
                    _team_rec[_team]["Scored"]  += _gf
                    _team_rec[_team]["Against"] += _ga
                    if _gf > _ga:
                        _team_rec[_team]["Won"]  += 1
                    elif _gf == _ga:
                        _team_rec[_team]["Drew"] += 1
                    else:
                        _team_rec[_team]["Lost"] += 1

        rows_s = []
        for _, row in stats_df.iterrows():
            team = str(row["Team"])
            grp  = group_map.get(team, "")
            if not grp or grp.lower() == "nan":
                continue
            tier = tier_map_local.get(team, 4)
            rnd  = str(row.get("RoundReached", "") or "").strip()
            bp   = _ctp_s(team, stats_df, tier)
            rec  = _team_rec.get(team, {"Played": 0, "Won": 0, "Drew": 0, "Lost": 0, "Scored": 0, "Against": 0})
            rows_s.append({
                "Group": grp, "Team": team, "_tier": tier,
                "Played":       rec["Played"],
                "Won":          rec["Won"],
                "Drew":         rec["Drew"],
                "Lost":         rec["Lost"],
                "Scored":       rec["Scored"],
                "Against":      rec["Against"],
                "Clean Sheets": int(float(row.get("GroupCleanSheets", 0) or 0)),
                "Swp Pts":      round(bp["total"], 1),
                "GW":           int(float(row.get("GroupWinner", 0) or 0)),
                "RoundReached": rnd,
                "_rr":          _ROUND_RANK.get(rnd, -1),
            })

        stand_df = pd.DataFrame(rows_s)
        th = "color:#6B7280;font-size:0.62rem;font-weight:600;padding:0.2rem 0.4rem;text-align:center;white-space:nowrap"

        for g_letter in sorted(stand_df["Group"].unique()):
            grp_df = (
                stand_df[stand_df["Group"] == g_letter]
                .sort_values(["GW", "_rr", "Won", "Scored"], ascending=[False, False, False, False])
                .reset_index(drop=True)
            )

            rows_html = ""
            for pos, (_, r) in enumerate(grp_df.iterrows(), 1):
                team  = r["Team"]
                tier  = r["_tier"]
                color = TIER_COLORS.get(tier, "#9CA3AF")
                rnd   = r["RoundReached"]

                if rnd in ("QF", "SF", "Final", "Winner"):
                    status_col = "#D4A017"
                elif rnd in ("R32", "R16"):
                    status_col = "#6EE7B7"
                elif rnd == "GroupStage":
                    status_col = "#6B7280"
                else:
                    status_col = "#9CA3AF"

                rnd_label = _ROUND_LABEL.get(rnd, "—")
                gw_badge = (
                    '<span style="background:#D4A01722;color:#D4A017;font-size:0.6rem;'
                    'border-radius:3px;padding:1px 4px;margin-left:4px">★ Group Winner</span>'
                ) if r["GW"] else ""

                owners = ownership_map.get(team, [])
                owners_html = (
                    f'<div style="color:#6EE7B7;font-size:0.62rem;margin-top:1px">{", ".join(owners)}</div>'
                ) if owners else ""

                td = "font-size:0.82rem;text-align:center;padding:0.32rem 0.4rem;"
                played = r["Played"]
                won    = r["Won"]
                drew   = r["Drew"]
                lost   = r["Lost"]
                scored = r["Scored"]
                agst   = r["Against"]
                cs     = r["Clean Sheets"]
                pts    = r["Swp Pts"]

                rows_html += (
                    f'<tr style="border-top:1px solid #2A3A4A">'
                    f'<td style="color:#9CA3AF;font-size:0.78rem;text-align:center;padding:0.32rem 0.4rem;width:1.5rem">{pos}</td>'
                    f'<td style="padding:0.32rem 0.5rem">'
                    f'<div style="display:flex;align-items:center;gap:0.3rem">'
                    f'<span style="color:{color};font-size:0.6rem;font-weight:700;background:{color}22;border-radius:3px;padding:0 3px">T{tier}</span>'
                    f'<span style="color:#F5F5F5;font-weight:600;font-size:0.85rem">{team}</span>'
                    f'{gw_badge}</div>{owners_html}</td>'
                    f'<td style="color:#9CA3AF;{td}">{played}</td>'
                    f'<td style="color:#6EE7B7;{td}">{won}</td>'
                    f'<td style="color:#9CA3AF;{td}">{drew}</td>'
                    f'<td style="color:#F87171;{td}">{lost}</td>'
                    f'<td style="color:#F5F5F5;{td}">{scored}</td>'
                    f'<td style="color:#9CA3AF;{td}">{agst}</td>'
                    f'<td style="color:#06B6D4;{td}">{cs}</td>'
                    f'<td style="color:#D4A017;font-weight:700;font-size:0.88rem;text-align:center;padding:0.32rem 0.4rem">{pts}</td>'
                    f'<td style="color:{status_col};font-size:0.72rem;padding:0.32rem 0.5rem">{rnd_label}</td>'
                    f'</tr>'
                )

            st.markdown(
                f'<div style="margin-bottom:1.4rem;overflow-x:auto">'
                f'<div style="color:#D4A017;font-weight:700;font-size:0.95rem;'
                f'margin:0.8rem 0 0;border-bottom:1px solid #2A3A4A;padding-bottom:0.2rem">'
                f'Group {g_letter}</div>'
                f'<table style="width:100%;border-collapse:collapse">'
                f'<thead><tr style="background:#131D2A">'
                f'<th style="{th};text-align:center">#</th>'
                f'<th style="{th};text-align:left">Team</th>'
                f'<th style="{th}">Played</th>'
                f'<th style="{th}">Won</th>'
                f'<th style="{th}">Drew</th>'
                f'<th style="{th}">Lost</th>'
                f'<th style="{th}">Scored</th>'
                f'<th style="{th}">Against</th>'
                f'<th style="{th}">Clean Sheets</th>'
                f'<th style="{th}">Sweepstake Pts</th>'
                f'<th style="{th};text-align:left">Status</th>'
                f'</tr></thead>'
                f'<tbody style="background:#1E2937">{rows_html}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )

# ═══════════════════════════════════════════════════════════════════
# TAB 3 — FIXTURES
# ═══════════════════════════════════════════════════════════════════
with tab_fixtures:
    if fixtures_df.empty:
        st.info("Fixture data not found.")
    else:
        all_owned = {t for ts in assignments.values() for t in ts} if assignments else set()
        tier_map_local2 = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in teams_df.iterrows()}

        entered_nums: set = set()
        score_lookup: dict[int, tuple[int, int]] = {}
        if not results_df.empty and "match_number" in results_df.columns:
            for _, rr in results_df.iterrows():
                mn_r = int(pd.to_numeric(rr.get("match_number", 0), errors="coerce") or 0)
                if mn_r:
                    entered_nums.add(mn_r)
                    score_lookup[mn_r] = (
                        int(float(rr.get("home_goals", 0) or 0)),
                        int(float(rr.get("away_goals", 0) or 0)),
                    )

        viewer = st.session_state.get("viewer")
        viewer_teams: set = set(assignments.get(viewer, [])) if viewer else set()

        today = date.today()
        col1, col2 = st.columns([2, 1])
        with col1:
            days_ahead = st.slider("Show fixtures for next N days", 1, 30, 14)
        with col2:
            toggle_label = f"Only {viewer}'s matches" if viewer else "Sweepstake matches only"
            owned_only = st.toggle(toggle_label, value=False, disabled=(not viewer and not all_owned))
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

            def _tier_badge(team: str) -> str:
                tier = tier_map_local2.get(team, 0)
                if not tier:
                    return ""
                color = TIER_COLORS.get(tier, "#9CA3AF")
                return (
                    f'<span style="background:{color}33;color:{color};font-size:0.58rem;'
                    f'font-weight:700;border-radius:3px;padding:1px 4px;margin-right:3px">T{tier}</span>'
                )

            completed_count = sum(1 for mn in upcoming["match_number"].dropna().astype(int) if mn in entered_nums)
            st.markdown(
                f'<div style="color:#9CA3AF;font-size:0.8rem;margin-bottom:0.6rem">'
                f'{len(upcoming)} fixtures · {completed_count} completed'
                f'</div>',
                unsafe_allow_html=True,
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
                    home = str(m.get("home_team", ""))
                    away = str(m.get("away_team", ""))
                    grp   = str(m.get("group", "")).strip()
                    venue = str(m.get("venue", "")).strip()
                    ko    = str(m.get("kickoff_time", "")).strip()
                    mn   = int(pd.to_numeric(m["match_number"], errors="coerce") or 0)
                    done = mn in entered_nums
                    home_owners = ", ".join(ownership_map.get(home, []))
                    away_owners = ", ".join(ownership_map.get(away, []))
                    home_owned  = home in all_owned
                    away_owned  = away in all_owned

                    if done and mn in score_lookup:
                        hg, ag = score_lookup[mn]
                        mid_html = (
                            f'<div style="text-align:center;min-width:3.5rem">'
                            f'<span style="color:#6EE7B7;font-size:1rem;font-weight:800">{hg} – {ag}</span>'
                            f'<div style="color:#6EE7B7;font-size:0.58rem">FT</div></div>'
                        )
                    else:
                        mid_html = (
                            f'<div style="text-align:center;min-width:3.5rem">'
                            f'<span style="color:#4B5563;font-size:0.85rem;font-weight:600">vs</span>'
                            f'</div>'
                        )

                    border_style = "border:1px solid #D4A017;" if (home_owned or away_owned) else "border:1px solid #2A3A4A;"
                    home_owner_html = f'<div style="color:#6EE7B7;font-size:0.65rem;margin-top:2px">{home_owners}</div>' if home_owners else '<div style="font-size:0.65rem"> </div>'
                    away_owner_html = f'<div style="color:#6EE7B7;font-size:0.65rem;margin-top:2px">{away_owners}</div>' if away_owners else '<div style="font-size:0.65rem"> </div>'
                    round_label = f"Group {grp}" if grp else "Knockout"
                    venue_short = venue.replace(" Stadium", "").replace("Estadio ", "") if venue else ""
                    ko_label = f" · {ko} GMT" if ko else ""

                    st.markdown(
                        f'<div style="background:#1E2937;border-radius:7px;padding:0.55rem 0.8rem;'
                        f'margin:0.25rem 0;{border_style}">'
                        f'<div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;align-items:center">'
                        f'<span style="color:#6B7280;font-size:0.65rem">{round_label}{ko_label}</span>'
                        f'<span style="color:#4B5563;font-size:0.63rem">{venue_short}</span>'
                        f'</div>'
                        f'<div style="display:flex;align-items:center;gap:0.5rem">'
                        f'<div style="flex:1;text-align:right">'
                        f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:4px">'
                        f'{_tier_badge(home)}'
                        f'<span style="color:{"#D4A017" if home_owned else "#F1F5F9"};font-weight:700;font-size:0.88rem">{home}</span>'
                        f'</div>{home_owner_html}</div>'
                        f'{mid_html}'
                        f'<div style="flex:1;text-align:left">'
                        f'<div style="display:flex;align-items:center;gap:4px">'
                        f'<span style="color:{"#D4A017" if away_owned else "#F1F5F9"};font-weight:700;font-size:0.88rem">{away}</span>'
                        f'{_tier_badge(away)}'
                        f'</div>{away_owner_html}</div>'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

# ═══════════════════════════════════════════════════════════════════
# TAB 4 — RESULTS
# ═══════════════════════════════════════════════════════════════════
with tab_results:
    if results_df.empty or "home_team" not in results_df.columns:
        st.info("No results entered yet.")
    else:
        all_owned_r = {t for ts in assignments.values() for t in ts} if assignments else set()
        tier_map_r  = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in teams_df.iterrows()}

        # Sort most recent first
        res_sorted = results_df.copy()
        if "match_date" in res_sorted.columns:
            res_sorted = res_sorted.sort_values("match_date", ascending=False, na_position="last")
        else:
            res_sorted = res_sorted.sort_values("match_number", ascending=False)

        def _tier_badge_r(team: str) -> str:
            tier = tier_map_r.get(team, 0)
            if not tier:
                return ""
            color = TIER_COLORS.get(tier, "#9CA3AF")
            return (
                f'<span style="background:{color}33;color:{color};font-size:0.58rem;'
                f'font-weight:700;border-radius:3px;padding:1px 4px;margin-right:3px">T{tier}</span>'
            )

        st.markdown(
            f'<div style="color:#9CA3AF;font-size:0.8rem;margin-bottom:0.6rem">'
            f'{len(res_sorted)} result{"s" if len(res_sorted) != 1 else ""} entered'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Group by date
        if "match_date" in res_sorted.columns:
            date_groups = res_sorted.groupby("match_date", sort=False)
            dates_ordered = res_sorted["match_date"].dropna().unique()
        else:
            dates_ordered = []

        def _render_result_card(m: "pd.Series") -> None:
            home = str(m.get("home_team", "—"))
            away = str(m.get("away_team", "—"))
            hg   = int(float(m.get("home_goals", 0) or 0))
            ag   = int(float(m.get("away_goals", 0) or 0))
            grp  = str(m.get("group", "")).strip()
            venue = str(m.get("venue", "")).strip()
            ko   = str(m.get("kickoff_time", "")).strip()
            et   = int(float(m.get("extra_time", 0) or 0))
            pw   = str(m.get("penalty_winner", "")).strip()
            mn   = m.get("match_number", "")

            home_owned = home in all_owned_r
            away_owned = away in all_owned_r
            home_owners = ", ".join(ownership_map.get(home, []))
            away_owners = ", ".join(ownership_map.get(away, []))

            if hg > ag:
                result_tag = f'<span style="color:#6EE7B7;font-size:0.62rem">W</span>'
                home_fw, away_fw = "800", "400"
            elif ag > hg:
                result_tag = f'<span style="color:#6EE7B7;font-size:0.62rem">W</span>'
                home_fw, away_fw = "400", "800"
            else:
                result_tag = f'<span style="color:#9CA3AF;font-size:0.62rem">D</span>'
                home_fw, away_fw = "600", "600"

            suffix = ""
            if pw:
                suffix = f'<div style="color:#F59E0B;font-size:0.6rem;text-align:center">Pens: {pw}</div>'
            elif et:
                suffix = f'<div style="color:#9CA3AF;font-size:0.6rem;text-align:center">AET</div>'

            border_style = "border:1px solid #D4A017;" if (home_owned or away_owned) else "border:1px solid #2A3A4A;"
            round_label  = f"Group {grp}" if grp else "Knockout"
            venue_short  = venue.replace(" Stadium", "").replace("Estadio ", "") if venue else ""
            ko_label     = f" · {ko} GMT" if ko else ""

            home_owner_html = f'<div style="color:#6EE7B7;font-size:0.65rem;margin-top:2px">{home_owners}</div>' if home_owners else '<div style="font-size:0.65rem"> </div>'
            away_owner_html = f'<div style="color:#6EE7B7;font-size:0.65rem;margin-top:2px">{away_owners}</div>' if away_owners else '<div style="font-size:0.65rem"> </div>'

            st.markdown(
                f'<div style="background:#1E2937;border-radius:7px;padding:0.55rem 0.8rem;'
                f'margin:0.25rem 0;{border_style}">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;align-items:center">'
                f'<span style="color:#6B7280;font-size:0.65rem">{round_label}{ko_label}&nbsp;&nbsp;'
                f'<span style="color:#374151">#{mn}</span></span>'
                f'<span style="color:#4B5563;font-size:0.63rem">{venue_short}</span>'
                f'</div>'
                f'<div style="display:flex;align-items:center;gap:0.5rem">'
                f'<div style="flex:1;text-align:right">'
                f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:4px">'
                f'{_tier_badge_r(home)}'
                f'<span style="color:{"#D4A017" if home_owned else "#F1F5F9"};font-weight:{home_fw};font-size:0.88rem">{home}</span>'
                f'</div>{home_owner_html}</div>'
                f'<div style="text-align:center;min-width:4rem">'
                f'<span style="color:#6EE7B7;font-size:1.1rem;font-weight:800">{hg} – {ag}</span>'
                f'<div style="color:#6B7280;font-size:0.58rem">FT</div>'
                f'{suffix}</div>'
                f'<div style="flex:1;text-align:left">'
                f'<div style="display:flex;align-items:center;gap:4px">'
                f'<span style="color:{"#D4A017" if away_owned else "#F1F5F9"};font-weight:{away_fw};font-size:0.88rem">{away}</span>'
                f'{_tier_badge_r(away)}'
                f'</div>{away_owner_html}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        if len(dates_ordered):
            for match_date in dates_ordered:
                day_matches = res_sorted[res_sorted["match_date"] == match_date]
                _ts = pd.Timestamp(match_date)
                try:
                    day_label = f"{_ts.day} {_ts.strftime('%b %Y')}"
                except Exception:
                    day_label = str(match_date)
                st.markdown(
                    f'<div style="color:#D4A017;font-weight:700;font-size:0.88rem;'
                    f'margin:0.9rem 0 0.35rem;border-bottom:1px solid #2A3A4A;padding-bottom:0.15rem">'
                    f'{day_label} · {len(day_matches)} match{"es" if len(day_matches)!=1 else ""}</div>',
                    unsafe_allow_html=True,
                )
                for _, m in day_matches.iterrows():
                    _render_result_card(m)
        else:
            for _, m in res_sorted.iterrows():
                _render_result_card(m)


# ═══════════════════════════════════════════════════════════════════
# TAB 5 — OWNERSHIP
# ═══════════════════════════════════════════════════════════════════
with tab_ownership:
    ownership_data = get_team_ownership_data()
    if not ownership_data:
        empty_state("No draw completed yet.")
    else:
        from src.scoring_engine import calculate_team_points as _ctp

        rows_o = []
        for team, data in sorted(ownership_data.items()):
            tier = tier_map.get(team, 0)
            bp = _ctp(team, stats_df, tier) if not stats_df.empty else {"group_stage": 0.0, "knockout": 0.0, "special": 0.0, "total": 0.0}
            rows_o.append({
                "Team":       team,
                "Tier":       f"T{tier}" if tier else "—",
                "Group":      group_map.get(team, "—"),
                "Owners":     ", ".join(sorted(data["owners"])) or "—",
                "Pre Cap":    ", ".join(sorted(data["pre_captains"])) or "—",
                "KO Cap":     ", ".join(sorted(data["knockout_captains"])) or "—",
                "Dark Horse": ", ".join(sorted(data["dark_horse_pickers"])) or "—",
                "Grp Pts":    f"{bp['group_stage']:.0f}",
                "KO Pts":     f"{bp['knockout']:.0f}",
                "Special":    f"{bp.get('special', 0):.0f}",
                "Total":      f"{bp['total']:.0f}",
            })

        all_df = pd.DataFrame(rows_o)
        tiers = ["All"] + [f"Tier {i}" for i in range(1, 5)]
        tier_filter = st.selectbox("Filter by Tier", tiers, key="ownership_tier_filter")
        if tier_filter != "All":
            t_num = tier_filter[-1]
            filtered = all_df[all_df["Tier"] == f"T{t_num}"]
        else:
            filtered = all_df

        st.caption(
            "**Grp Pts** = goals, clean sheets, bonuses from the group stage. "
            "**KO Pts** = knockout stats + progression bonuses. "
            "**Special** = shirt removals, GK goals, red cards, first eliminated."
        )
        searchable_table(filtered, "Search teams, owners, dark horses…", key="tbl_ownership")

        st.divider()
        st.subheader("Team Detail")
        team_names = sorted(ownership_data.keys())
        selected = st.selectbox("Select Team", team_names, key="team_detail_select")

        if selected:
            data   = ownership_data[selected]
            tier   = tier_map.get(selected, 1)
            grp    = group_map.get(selected, "—")
            bp     = _ctp(selected, stats_df, tier) if not stats_df.empty else {"group_stage": 0, "knockout": 0, "special": 0, "total": 0}

            st.markdown(
                f'<div class="card-gold">'
                f'<h3 style="margin:0;color:#D4A017">{selected}</h3>'
                f'<p style="color:#9CA3AF;margin:0.25rem 0 0">Tier {tier} · Group {grp}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            pc1, pc2, pc3, pc4 = st.columns(4)
            with pc1: st.metric("Group Stage", f"{bp['group_stage']:.0f}")
            with pc2: st.metric("Knockout",    f"{bp['knockout']:.0f}")
            with pc3: st.metric("Special",     f"{bp.get('special', 0):.0f}")
            with pc4: st.metric("Total",       f"{bp['total']:.0f}")

            if data.get("dark_horse_pickers"):
                st.info(
                    f"Dark Horse picked by: **{', '.join(sorted(data['dark_horse_pickers']))}** — "
                    "bonus is scored separately and added to their personal leaderboard total."
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
