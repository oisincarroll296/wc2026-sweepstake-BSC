"""Analytics — interactive charts using Plotly."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from dashboard.data import (
    get_overall_leaderboard, get_prize_pool, get_match_stats,
    get_tier_map, get_team_ownership_data, get_predictions_centre_data,
    get_captains, get_purchases, get_statuses, is_predictions_locked,
    get_remaining_potential, get_remaining_potential_detail,
    get_r16_potential,
    get_goals_conceded_map, get_score_history,
    get_assignments, get_insurance_overview,
)
from dashboard.config import PLOTLY_LAYOUT, TIER_COLORS, COLORS
from dashboard.components.ui import page_header, empty_state


page_header("📊 Analytics", "Interactive charts — all data live from the tournament")

lb = get_overall_leaderboard()
match_stats = get_match_stats()
tier_map    = get_tier_map()

# ── 1. Leaderboard Bar Chart ───────────────────────────────────────────────
st.subheader("🏆 Current Standings")
if lb.empty:
    empty_state("No scores yet.")
else:
    colors = []
    for i, row in lb.iterrows():
        if row.get("PaymentStatus") == "UNPAID":
            colors.append(COLORS["muted"])
        elif i == 0:
            colors.append(COLORS["gold"])
        elif i == 1:
            colors.append(COLORS["silver"])
        elif i == 2:
            colors.append(COLORS["bronze"])
        else:
            colors.append("#4A6FA5")

    fig = go.Figure(go.Bar(
        x=lb["Player"].tolist(),
        y=lb["TotalPoints"].astype(float).tolist(),
        marker_color=colors,
        hovertemplate="%{x}: %{y:.0f} pts<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT, title="Total Points by Player", height=350)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── 2. Points Breakdown Stacked Bar ───────────────────────────────────────
if not lb.empty:
    _breakdown_def = [
        ("GroupStagePoints", "Group Stage",  "#4A9A7A"),
        ("KnockoutPoints",   "Knockout",     "#105AAC"),
        ("CaptainBonus",     "Captains",     COLORS["gold"]),
        ("PredictionBonus",  "Predictions",  "#6A5ACD"),
    ]
    _avail_bd = [(col, lbl, clr) for col, lbl, clr in _breakdown_def if col in lb.columns]
    if _avail_bd:
        st.subheader("📐 Points Breakdown")
        fig2 = go.Figure()
        for col, lbl, clr in _avail_bd:
            fig2.add_trace(go.Bar(
                name=lbl,
                x=lb["Player"].tolist(),
                y=lb[col].astype(float).tolist(),
                marker_color=clr,
            ))
        fig2.update_layout(**PLOTLY_LAYOUT, barmode="stack", height=350, title="Points Breakdown by Source")
        st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── 3. Top Scoring Teams + Goals Conceded ─────────────────────────────────
col_ts, col_gc = st.columns(2)

with col_ts:
    st.subheader("⚽ Top Scoring Teams")
    if match_stats.empty:
        empty_state("No match data yet.")
    else:
        from src.scoring_engine import calculate_team_points
        team_pts = []
        for _, row in match_stats.iterrows():
            team = str(row["Team"])
            tier = tier_map.get(team, 1)
            pts  = calculate_team_points(team, match_stats, tier)["total"]
            if pts > 0:
                team_pts.append({"Team": team, "Points": pts, "Tier": tier})

        if team_pts:
            tdf = pd.DataFrame(team_pts).sort_values("Points", ascending=False).head(15)
            fig3 = go.Figure(go.Bar(
                x=tdf["Team"].tolist(),
                y=tdf["Points"].tolist(),
                marker_color=[TIER_COLORS.get(t, "#9CA3AF") for t in tdf["Tier"].tolist()],
                hovertemplate="%{x}: %{y:.0f} pts<extra></extra>",
            ))
            _t3_layout = {**PLOTLY_LAYOUT}
            _t3_layout.update(title="Top 15 Scoring Teams", height=350)
            fig3.update_layout(**_t3_layout)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            empty_state("No team points yet.")

with col_gc:
    st.subheader("🧤 Goals Conceded by Team")
    _gc_map = get_goals_conceded_map()
    if _gc_map:
        _gc_sorted = sorted(_gc_map.items(), key=lambda x: x[1], reverse=True)[:15]
        _gc_teams  = [x[0] for x in _gc_sorted]
        _gc_vals   = [x[1] for x in _gc_sorted]
        _gc_colors = [TIER_COLORS.get(tier_map.get(t, 1), "#9CA3AF") for t in _gc_teams]
        fig_gc = go.Figure(go.Bar(
            x=_gc_teams, y=_gc_vals, marker_color=_gc_colors,
            hovertemplate="%{x}: %{y} GA<extra></extra>",
        ))
        _gc_layout = {**PLOTLY_LAYOUT}
        _gc_layout.update(title="Most Goals Conceded (top 15)", height=350)
        fig_gc.update_layout(**_gc_layout)
        st.plotly_chart(fig_gc, use_container_width=True)
    else:
        empty_state("Goals conceded calculated from match results — none entered yet.")

st.divider()

# ── 4. Team Ownership — per-player tier grid ──────────────────────────────
st.subheader("🗂️ Team Ownership by Tier")
_assignments = get_assignments()
if _assignments:
    _TIER_LABELS = {1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4"}
    _TIER_BG     = {1: "#10307a", 2: "#1a6940", 3: "#7a5a10", 4: "#8b1c1c"}
    _TIER_FG     = {1: "#c8d9ff", 2: "#bbf7d0", 3: "#fef08a", 4: "#fecaca"}

    def _team_chip(team: str, tier: int) -> str:
        bg = _TIER_BG.get(tier, "#1e293b")
        fg = _TIER_FG.get(tier, "#f1f5f9")
        return (
            f'<span style="background:{bg};color:{fg};border-radius:5px;'
            f'padding:2px 8px;font-size:0.78rem;white-space:nowrap;'
            f'display:inline-block;margin:2px 3px 2px 0">{team}</span>'
        )

    html_rows = ['<table style="width:100%;border-collapse:separate;border-spacing:0 4px">']
    for player in sorted(_assignments.keys()):
        teams = _assignments[player]
        by_tier: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: []}
        for t in teams:
            by_tier[tier_map.get(t, 1)].append(t)
        chips = "".join(
            _team_chip(t, tier)
            for tier in [1, 2, 3, 4]
            for t in sorted(by_tier[tier])
        )
        html_rows.append(
            f'<tr>'
            f'<td style="color:#D4A017;font-weight:700;font-size:0.88rem;'
            f'white-space:nowrap;padding:4px 12px 4px 0;vertical-align:middle;width:90px">{player}</td>'
            f'<td style="padding:2px 0">{chips}</td>'
            f'</tr>'
        )
    html_rows.append("</table>")

    # Legend
    legend = "".join(
        f'<span style="background:{_TIER_BG[t]};color:{_TIER_FG[t]};border-radius:4px;'
        f'padding:2px 8px;font-size:0.75rem;margin-right:6px">{_TIER_LABELS[t]}</span>'
        for t in [1, 2, 3, 4]
    )
    st.markdown(
        f'<div style="background:#0d1b2a;border:1px solid #2a3a4a;border-radius:10px;'
        f'padding:14px 16px">'
        f'<div style="margin-bottom:8px">{legend}</div>'
        f'{"".join(html_rows)}'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    empty_state("Draw not completed yet.")

st.divider()

# ── 4b. Ownership count + dark horse ─────────────────────────────────────
col_own, col_pop = st.columns(2)
with col_own:
    st.subheader("👥 Ownership Count")
    own = get_team_ownership_data()
    if own:
        owned_counts = [(t, len(d["owners"])) for t, d in own.items() if d["owners"]]
        owned_counts.sort(key=lambda x: -x[1])
        odf = pd.DataFrame(owned_counts[:15], columns=["Team", "Owners"])
        fig4 = go.Figure(go.Bar(
            x=odf["Team"].tolist(), y=odf["Owners"].tolist(),
            marker_color=COLORS["gold"],
            hovertemplate="%{x}: %{y} owners<extra></extra>",
        ))
        fig4.update_layout(**PLOTLY_LAYOUT, height=300, title="Teams by Owner Count")
        st.plotly_chart(fig4, use_container_width=True)
    else:
        empty_state()

with col_pop:
    st.subheader("🌟 Dark Horse Picks")
    if is_predictions_locked():
        preds = get_predictions_centre_data()
        dh = preds.get("dark_horse", {})
        if dh:
            dh_list = [(k, len(v)) for k, v in dh.items()]
            dh_list.sort(key=lambda x: -x[1])
            fig5 = go.Figure(go.Bar(
                x=[x[0] for x in dh_list],
                y=[x[1] for x in dh_list],
                marker_color=COLORS["t3"],
                hovertemplate="%{x}: %{y} pick(s)<extra></extra>",
            ))
            fig5.update_layout(**PLOTLY_LAYOUT, height=300, title="Dark Horse Picks")
            st.plotly_chart(fig5, use_container_width=True)
        else:
            empty_state("No dark horse picks.")
    else:
        st.markdown('<div class="lock-banner">🔒 Dark horse picks hidden until prediction lock</div>', unsafe_allow_html=True)

st.divider()

# ── 5. Prize Pool Growth ──────────────────────────────────────────────────
st.subheader("💰 Prize Pool Contribution by Type")
from src.competition import PRICES, load_purchases as _load_purchases
p = _load_purchases()  # read directly — avoids cold-start cache miss
if not p.empty:
    breakdown = {}
    for ptype, price in PRICES.items():
        cnt = int((p["PurchaseType"] == ptype).sum())
        if cnt:
            breakdown[ptype] = cnt * price

    if breakdown:
        fig6 = go.Figure(go.Pie(
            labels=list(breakdown.keys()),
            values=list(breakdown.values()),
            marker_colors=[COLORS["gold"], "#4A9A7A", "#A67C00", "#6A5ACD", "#B91C1C", "#15803D"],
            hole=0.45,
            hovertemplate="%{label}: €%{value:.2f}<extra></extra>",
        ))
        fig6.update_layout(**PLOTLY_LAYOUT, height=320, title="Prize Pool Composition")
        st.plotly_chart(fig6, use_container_width=True)
    else:
        empty_state("No processed purchases yet.")
else:
    empty_state("No purchase data.")

# ── 6. Points Over Time (line chart) ─────────────────────────────────────
st.divider()
st.subheader("📈 Points Over Time")

_ROOT = Path(__file__).parent.parent.parent
_hist_path = _ROOT / "data" / "score_history.csv"

_MILESTONE_DATES = {
    "2026-06-11": "MD1",
    "2026-06-18": "MD2",
    "2026-06-25": "MD3",
    "2026-07-01": "R32/R16",
    "2026-07-09": "QF",
    "2026-07-14": "SF",
    "2026-07-19": "Final",
}

def _fmt_date(d: str) -> str:
    dt = pd.to_datetime(d)
    return dt.strftime("%b %d").replace(" 0", " ")

if _hist_path.exists():
    try:
        _hist = pd.read_csv(_hist_path)
        _hist["Date"] = _hist["Date"].astype(str)
        _players_hist = sorted(_hist["Player"].unique())

        # Forward-fill so every calendar day has a data point (no gaps for rest days)
        _all_dates = sorted(_hist["Date"].unique())
        _full_dates = (
            pd.date_range(_all_dates[0], _all_dates[-1], freq="D")
            .strftime("%Y-%m-%d").tolist()
        )
        _filled = []
        for _p in _players_hist:
            _pd0 = _hist[_hist["Player"] == _p][["Date", "Points"]].set_index("Date")
            _pd0 = _pd0.reindex(_full_dates).ffill().reset_index()
            _pd0.columns = ["Date", "Points"]
            _pd0["Player"] = _p
            _filled.append(_pd0)
        _hist = pd.concat(_filled, ignore_index=True)

        # Map each raw date → display label ("Jun 11", "Jun 12", …)
        _date_label = {d: _fmt_date(d) for d in _full_dates}

        # Use Plotly qualitative palette — enough colours for 13 players
        _palette = px.colors.qualitative.Light24
        _fig_line = go.Figure()

        for _idx, _pl in enumerate(_players_hist):
            _pdata = _hist[_hist["Player"] == _pl].sort_values("Date")
            _x_labels = [_date_label.get(d, d) for d in _pdata["Date"].tolist()]
            _fig_line.add_trace(go.Scatter(
                x=_x_labels,
                y=_pdata["Points"].tolist(),
                mode="lines+markers",
                name=_pl,
                line=dict(color=_palette[_idx % len(_palette)], width=2),
                marker=dict(size=6),
                hovertemplate=f"<b>{_pl}</b><br>%{{x}}: %{{y:.0f}} pts<extra></extra>",
            ))

        _line_layout = {**PLOTLY_LAYOUT}
        _line_layout.update(
            title="Cumulative Points Over Time",
            height=420,
            xaxis_title="Date",
            yaxis_title="Points",
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11), x=1.01, y=1),
        )
        _fig_line.update_layout(**_line_layout)
        st.plotly_chart(_fig_line, use_container_width=True)
        _ms_visible = {_fmt_date(d): lbl for d, lbl in _MILESTONE_DATES.items() if _fmt_date(d) in _date_label.values()}
        _ms_caption = "  ·  ".join(f"{lbl}: {d}" for d, lbl in _ms_visible.items()) if _ms_visible else ""
        st.caption(f"Cumulative points per player, updated daily.{('  |  ' + _ms_caption) if _ms_caption else ''}")

        # ── Rank trajectory ───────────────────────────────────────────────
        st.subheader("📉 Rank Over Time")
        _rank_rows = []
        for _d in sorted(_hist["Date"].unique()):
            _snap = _hist[_hist["Date"] == _d].copy()
            _snap = _snap.sort_values("Points", ascending=False).reset_index(drop=True)
            for _r, _row in _snap.iterrows():
                _rank_rows.append({
                    "Date": _d,
                    "Label": _date_label.get(_d, _d),
                    "Player": _row["Player"],
                    "Rank": _r + 1,
                })
        _rank_df = pd.DataFrame(_rank_rows) if _rank_rows else pd.DataFrame(columns=["Date", "Label", "Player", "Rank"])
        if not _rank_df.empty:
            _fig_rank = go.Figure()
            for _idx, _pl in enumerate(sorted(_rank_df["Player"].unique())):
                _pd2 = _rank_df[_rank_df["Player"] == _pl].sort_values("Date")
                _fig_rank.add_trace(go.Scatter(
                    x=_pd2["Label"].tolist(),
                    y=_pd2["Rank"].tolist(),
                    mode="lines+markers",
                    name=_pl,
                    line=dict(color=_palette[_idx % len(_palette)], width=2),
                    marker=dict(size=6),
                    hovertemplate=f"<b>{_pl}</b><br>%{{x}}: rank %{{y}}<extra></extra>",
                ))
            _rank_layout = {**PLOTLY_LAYOUT}
            _rank_layout.update(
                title="Rank Position Over Time (lower = better)",
                height=420,
                xaxis_title="Date",
                yaxis_title="Position",
                yaxis=dict(autorange="reversed", dtick=1, gridcolor="#2A3A4A"),
                legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11), x=1.01, y=1),
            )
            _fig_rank.update_layout(**_rank_layout)
            st.plotly_chart(_fig_rank, use_container_width=True)
            st.caption("Inverted axis — 1st place sits at the top. Shows who is climbing and who is falling.")
        else:
            st.info("Rank history will appear after multiple score snapshots are recorded.")
    except Exception as _e:
        st.info(f"Points history not available: {_e}")
else:
    st.info("No score history yet. History will appear after match results are entered.")

# ── 7. Weekly Form (biggest points jump this gameweek) ────────────────────
st.divider()
st.subheader("🔥 Weekly Form")
_score_hist = get_score_history()
if _score_hist.empty:
    empty_state("No score history yet — appears after match results are entered.")
else:
    _hist_dates = sorted(_score_hist["Date"].unique())
    if len(_hist_dates) >= 2:
        _latest_gw  = _hist_dates[-1]
        _prev_gw    = _hist_dates[-2]
        _latest_pts = _score_hist[_score_hist["Date"] == _latest_gw].set_index("Player")["Points"]
        _prev_pts   = _score_hist[_score_hist["Date"] == _prev_gw].set_index("Player")["Points"]
        _form_rows  = []
        for pl in _latest_pts.index:
            gained = float(_latest_pts[pl]) - float(_prev_pts.get(pl, 0))
            _form_rows.append({"Player": pl, "Gained": gained})
        _form_df = pd.DataFrame(_form_rows).sort_values("Gained", ascending=False)
        _form_colors = [COLORS["gold"] if r["Gained"] == _form_df["Gained"].max()
                        else "#4A6FA5" if r["Gained"] >= 0 else "#B91C1C"
                        for _, r in _form_df.iterrows()]
        fig_form = go.Figure(go.Bar(
            x=_form_df["Player"].tolist(),
            y=_form_df["Gained"].tolist(),
            marker_color=_form_colors,
            hovertemplate="%{x}: %{y:+.0f} pts this gameweek<extra></extra>",
        ))
        _form_layout = {**PLOTLY_LAYOUT}
        _form_layout.update(
            title=f"Points Gained — {_MILESTONE_DATES.get(_latest_gw, _fmt_date(_latest_gw) if _latest_gw else '')}",
            height=320,
            yaxis_title="Points Gained",
        )
        fig_form.update_layout(**_form_layout)
        st.plotly_chart(fig_form, use_container_width=True)
        _best = _form_df.iloc[0]
        st.caption(f"🔥 Top form this gameweek: **{_best['Player']}** (+{_best['Gained']:.0f} pts)")
    else:
        st.info("Need at least 2 gameweeks of data to show form. More data coming as results are entered.")

st.divider()

# ── 8. Remaining Potential ─────────────────────────────────────────────────
st.subheader("🎯 Remaining Potential")
_pot_detail = get_remaining_potential_detail()

if _pot_detail:
    # Sort players by max possible total descending
    _pot_players = sorted(
        _pot_detail.keys(),
        key=lambda p: -_pot_detail[p]["max_possible_total"],
    )
    _current_scores = [_pot_detail[p]["current_score"] for p in _pot_players]
    _max_potentials = [_pot_detail[p]["max_potential"] for p in _pot_players]

    # Stacked bar: current score (solid) + max potential (semi-transparent)
    _fig_pot = go.Figure()
    _fig_pot.add_trace(go.Bar(
        name="Current Score",
        x=_pot_players,
        y=_current_scores,
        marker_color=COLORS["gold"],
        hovertemplate="%{x}: %{y:.0f} pts current<extra></extra>",
    ))
    _fig_pot.add_trace(go.Bar(
        name="Max Remaining",
        x=_pot_players,
        y=_max_potentials,
        marker_color="rgba(74,111,165,0.55)",
        hovertemplate="%{x}: +%{y:.0f} pts max remaining<extra></extra>",
    ))
    _pot_layout = {**PLOTLY_LAYOUT}
    _pot_layout.update(
        barmode="stack",
        title="Current Score + Max Possible Remaining (progression bonuses only)",
        height=360,
        yaxis_title="Points",
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11), orientation="h", y=-0.15),
    )
    _fig_pot.update_layout(**_pot_layout)
    st.plotly_chart(_fig_pot, use_container_width=True)
    st.caption(
        "Gold = current points. Blue = maximum remaining if every surviving team wins the tournament. "
        "Minimum remaining is 0 — any alive team can be knocked out next game."
    )

st.divider()

# ── 8b. R16 Potential ─────────────────────────────────────────────────────
st.subheader("🎯 Points if All Surviving Teams Reach R16")
st.caption(
    "Shows each player's current score (gold) plus the additional progression points "
    "they would earn if every one of their surviving teams made it to the Round of 16."
)
_r16_data = get_r16_potential()
if _r16_data:
    _r16_players = sorted(_r16_data.keys(), key=lambda p: -_r16_data[p]["r16_total"])
    _r16_current = [_r16_data[p]["current_score"] for p in _r16_players]
    _r16_extra   = [_r16_data[p]["r16_additional"] for p in _r16_players]
    _r16_totals  = [_r16_data[p]["r16_total"] for p in _r16_players]

    _fig_r16 = go.Figure()
    _fig_r16.add_trace(go.Bar(
        name="Current Score",
        x=_r16_players,
        y=_r16_current,
        marker_color=COLORS["gold"],
        hovertemplate="%{x}: %{y:.0f} pts current<extra></extra>",
    ))
    _fig_r16.add_trace(go.Bar(
        name="R16 Progression Bonus",
        x=_r16_players,
        y=_r16_extra,
        marker_color="rgba(34,211,238,0.6)",
        hovertemplate="%{x}: +%{y:.0f} pts if all reach R16<extra></extra>",
    ))
    _r16_layout = {**PLOTLY_LAYOUT}
    _r16_layout.update(
        barmode="stack",
        title="Current Score + R16 Potential (progression bonuses only)",
        height=360,
        yaxis_title="Points",
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11), orientation="h", y=-0.15),
    )
    _fig_r16.update_layout(**_r16_layout)
    st.plotly_chart(_fig_r16, use_container_width=True)

    # Table summary
    _r16_rows = [
        {
            "Player": p,
            "Current": f"{_r16_data[p]['current_score']:.0f}",
            "+ If All Reach R16": f"+{_r16_data[p]['r16_additional']:.0f}",
            "Total": f"{_r16_data[p]['r16_total']:.0f}",
        }
        for p in _r16_players
    ]
    st.dataframe(pd.DataFrame(_r16_rows), use_container_width=True, hide_index=True)

st.divider()

# ── 9. Insurance Overview ─────────────────────────────────────────────────
st.divider()
st.subheader("🛡️ Insurance Tracker")
st.caption("+25 pts per Tier 1 team eliminated before R16 · max +50 if both go out")

_ins_ov = get_insurance_overview()
_t1_status = _ins_ov.get("t1_status", [])
_ins_holders = _ins_ov.get("holders", [])

if _t1_status:
    _t1_cols = st.columns(min(len(_t1_status), 4))
    for _ci, _t1 in enumerate(_t1_status):
        with _t1_cols[_ci % len(_t1_cols)]:
            _eliminated = _t1["eliminated"]
            _rnd = _t1["round_reached"]
            _bg   = "rgba(110,231,183,0.10)" if _eliminated else ("rgba(248,113,113,0.08)" if _rnd and not _eliminated else "#1E2937")
            _icon = "🔴" if _eliminated else ("🟢" if _rnd else "⏳")
            _status_txt = "OUT — Groups" if _eliminated else (f"Alive — {_rnd}" if _rnd else "In groups")
            _owners_str = ", ".join(_t1["owners"]) if _t1["owners"] else "Unowned"
            st.markdown(
                f'<div style="background:{_bg};border:1px solid #2A3A4A;border-radius:8px;'
                f'padding:0.6rem 0.75rem;margin-bottom:0.4rem;text-align:center">'
                f'<div style="font-size:1.3rem">{_icon}</div>'
                f'<div style="color:#F5F5F5;font-weight:700;font-size:0.9rem">{_t1["team"]}</div>'
                f'<div style="color:{"#6EE7B7" if _eliminated else "#D4A017"};font-size:0.72rem;margin-top:2px">{_status_txt}</div>'
                f'<div style="color:#9CA3AF;font-size:0.65rem;margin-top:4px">Owners: {_owners_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

if _ins_holders:
    st.markdown("**Insurance Holders**")
    _ins_rows = []
    for _h in sorted(_ins_holders, key=lambda x: -x["bonus_earned"]):
        _ins_rows.append({
            "Player":      _h["player"],
            "T1 Teams":    " · ".join(_h["t1_teams"]),
            "Teams Out":   _h["eliminated_count"],
            "Earned":      f"+{_h['bonus_earned']:.0f} pts",
            "Max Possible": f"+{_h['max_bonus']:.0f} pts",
        })
    import pandas as _pd_ins
    st.dataframe(_pd_ins.DataFrame(_ins_rows), use_container_width=True, hide_index=True)
    _max_earner = max(_ins_holders, key=lambda x: x["bonus_earned"], default=None)
    if _max_earner and _max_earner["bonus_earned"] > 0:
        st.caption(f"🏆 Biggest insurance payout so far: **{_max_earner['player']}** (+{_max_earner['bonus_earned']:.0f} pts)")
else:
    st.info("No insurance purchases yet — or no Tier 1 eliminations yet.")

st.divider()

# ── 10. Captain Selections ─────────────────────────────────────────────────
st.divider()
caps = get_captains()
if not caps.empty:
    st.subheader("🎖️ Captain Selections")
    cap_col1, cap_col2 = st.columns(2)
    for col, cap_type, title in [
        (cap_col1, "PreTournament", "Pre-Tournament Captains"),
        (cap_col2, "Knockout",       "Knockout Captains"),
    ]:
        with col:
            st.markdown(f"**{title}**")
            subset = caps[caps["CaptainType"] == cap_type]
            if not subset.empty:
                counts = subset["Team"].value_counts().reset_index()
                counts.columns = ["Team", "Count"]
                fig7 = go.Figure(go.Bar(
                    x=counts["Team"].tolist(), y=counts["Count"].tolist(),
                    marker_color=COLORS["gold"],
                    hovertemplate="%{x}: %{y}<extra></extra>",
                ))
                fig7.update_layout(**PLOTLY_LAYOUT, height=250)
                st.plotly_chart(fig7, use_container_width=True)
