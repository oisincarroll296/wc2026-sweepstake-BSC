"""Leaderboard — Prize standings + All Players with full score breakdown."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from dashboard.data import (
    get_prize_leaderboard, get_overall_leaderboard,
    get_prize_pool, get_remaining_potential,
)
from dashboard.config import PLOTLY_LAYOUT, COLORS
from dashboard.components.ui import page_header, empty_state

page_header("Leaderboard", "Prize standings and full score breakdown")

pool = get_prize_pool()
lb_prize = get_prize_leaderboard()
lb_all   = get_overall_leaderboard()
pot      = get_remaining_potential()

tab_prize, tab_all = st.tabs(["🏆 Prize Standings", "🌍 All Players"])

# ── shared helpers ─────────────────────────────────────────────────────────

BREAKDOWN_COLS = ["BasePoints", "CaptainBonus", "InsuranceBonus", "SpecialBonus", "PredictionBonus"]
BREAKDOWN_LABELS = {
    "BasePoints":      "Match Pts",
    "CaptainBonus":    "Captain",
    "InsuranceBonus":  "Insurance",
    "SpecialBonus":    "Special",
    "PredictionBonus": "Predictions",
}
BREAKDOWN_COLORS = {
    "BasePoints":      "#4A6FA5",
    "CaptainBonus":    "#D4A017",
    "InsuranceBonus":  "#15803D",
    "SpecialBonus":    "#7C3AED",
    "PredictionBonus": "#B91C1C",
}


def _stacked_chart(lb: pd.DataFrame, title: str):
    """Stacked bar chart: one bar per player coloured by score category."""
    if lb.empty:
        return
    players = lb["Player"].tolist()
    fig = go.Figure()
    for col in BREAKDOWN_COLS:
        if col not in lb.columns:
            continue
        vals = lb[col].fillna(0).astype(float).tolist()
        if all(v == 0 for v in vals):
            continue
        fig.add_trace(go.Bar(
            name=BREAKDOWN_LABELS[col],
            x=players,
            y=vals,
            marker_color=BREAKDOWN_COLORS[col],
            hovertemplate=f"<b>%{{x}}</b><br>{BREAKDOWN_LABELS[col]}: %{{y:.0f}} pts<extra></extra>",
        ))
    _layout = {**PLOTLY_LAYOUT}
    _layout["legend"] = {**_layout.get("legend", {}), "orientation": "h", "y": -0.25, "x": 0, "font": {"size": 11}}
    _layout["margin"] = dict(l=5, r=5, t=35, b=60)
    fig.update_layout(barmode="stack", title=title, height=320, **_layout)
    st.plotly_chart(fig, use_container_width=True)


def _breakdown_bar(row: dict) -> str:
    """Inline HTML progress-style breakdown for a single player row."""
    total = float(row.get("TotalPoints", 0)) or 1
    segments = []
    for col in BREAKDOWN_COLS:
        val = float(row.get(col, 0))
        if val <= 0:
            continue
        pct = val / total * 100
        color = BREAKDOWN_COLORS[col]
        label = BREAKDOWN_LABELS[col]
        segments.append(
            f'<div title="{label}: {val:.0f}" style="background:{color};width:{pct:.1f}%;'
            f'height:6px;display:inline-block;border-radius:2px"></div>'
        )
    return (
        '<div style="display:flex;gap:1px;margin-top:3px;width:100%">' +
        "".join(segments) + "</div>"
    ) if segments else ""


def _format_lb(lb: pd.DataFrame, show_prize: bool = False) -> pd.DataFrame:
    """Build display-ready table from leaderboard DataFrame."""
    if lb.empty:
        return lb
    leader_pts = float(lb.iloc[0]["TotalPoints"]) if "TotalPoints" in lb.columns else 0.0
    rows = []
    for _, row in lb.iterrows():
        rank   = int(row.get("Rank", 0))
        pts    = float(row.get("TotalPoints", 0))
        player = row.get("Player", "")
        medal  = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
        base   = float(row.get("BasePoints", 0))
        cap    = float(row.get("CaptainBonus", 0))
        ins    = float(row.get("InsuranceBonus", 0))
        spec   = float(row.get("SpecialBonus", 0))
        pred   = float(row.get("PredictionBonus", 0))
        rem    = pot.get(player, 0)
        r = {
            "":         medal,
            "Player":   player,
            "Total":    f"{pts:.0f}",
            "Gap":      f"{pts - leader_pts:+.0f}" if rank > 1 else "—",
            "Match":    f"{base:.0f}",
            "Captain":  f"+{cap:.0f}" if cap else "—",
            "Special":  f"+{spec:.0f}" if spec else "—",
            "Insurance":f"+{ins:.0f}" if ins else "—",
            "Preds":    f"+{pred:.0f}" if pred else "—",
            "Potential":f"+{rem:.0f}",
        }
        if show_prize:
            r["Prize"] = {1: "Winner", 2: "Runner-up", 3: "3rd"}.get(rank, "—")
        if "PaymentStatus" in row:
            r["_status"] = row["PaymentStatus"]
        rows.append(r)
    return pd.DataFrame(rows)


def _style_lb(display: pd.DataFrame, paid_only: bool = False):
    def _style(row: pd.Series):
        status = row.get("_status", "PAID")
        if not paid_only and status == "UNPAID":
            return ["color: #6B7280"] * len(row)
        idx = row.name
        if idx == 0:
            return ["background-color: rgba(212,160,23,0.18); font-weight:700"] * len(row)
        if idx == 1:
            return ["background-color: rgba(192,192,192,0.10)"] * len(row)
        if idx == 2:
            return ["background-color: rgba(205,127,50,0.10)"] * len(row)
        return [""] * len(row)
    return display.style.apply(_style, axis=1)


# ═══════════════════════════════════════════════════════════════════
# TAB 1 — PRIZE STANDINGS
# ═══════════════════════════════════════════════════════════════════
with tab_prize:
    # Prize pool header
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Prize Pool", f"€{pool.get('current_pot', 0):.2f}")
    with c2: st.metric("1st Place",  f"€{pool.get('first_prize', 0):.2f}")
    with c3: st.metric("2nd Place",  f"€{pool.get('second_prize', 0):.2f}")
    with c4: st.metric("3rd Place",  f"€{pool.get('third_prize', 0):.2f}")

    st.divider()

    if lb_prize.empty:
        empty_state("No paid players yet.")
    else:
        # Win probability (softmax)
        _scores = lb_prize["TotalPoints"].astype(float).tolist()
        _spread = (max(_scores) - min(_scores)) if len(_scores) > 1 else 1
        _temp   = max(_spread / 5, 1.0)
        _exps   = [math.exp((s - min(_scores)) / _temp) for s in _scores]
        _probs  = [e / sum(_exps) * 100 for e in _exps]

        # Stacked breakdown chart
        _stacked_chart(lb_prize, "Score Breakdown by Category")

        st.subheader("Standings")
        display = _format_lb(lb_prize, show_prize=True)

        # Add win chance column
        if len(_probs) == len(display):
            display.insert(display.columns.get_loc("Potential"), "Chance", [f"{p:.1f}%" for p in _probs])

        # Drop internal status col for display
        show_cols = [c for c in display.columns if c != "_status"]
        st.dataframe(
            _style_lb(display[show_cols]),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Match = team goals/clean sheets/bonuses/progression/upsets · "
            "Potential = max remaining points from surviving teams · "
            "Chance = softmax win probability"
        )

        # Legend
        st.markdown(
            '<div style="display:flex;flex-wrap:wrap;gap:0.5rem;margin-top:0.25rem">' +
            "".join(
                f'<span style="background:{BREAKDOWN_COLORS[c]};color:#fff;font-size:0.7rem;'
                f'border-radius:3px;padding:2px 7px">{BREAKDOWN_LABELS[c]}</span>'
                for c in BREAKDOWN_COLS
            ) + "</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════
# TAB 2 — ALL PLAYERS
# ═══════════════════════════════════════════════════════════════════
with tab_all:
    st.info("Players marked **UNPAID** appear here but cannot win prizes.", icon="ℹ️")

    if lb_all.empty:
        empty_state("No players found.")
    else:
        _stacked_chart(lb_all, "Score Breakdown — All Players")

        st.subheader("All Players")
        display_all = _format_lb(lb_all)
        show_cols_all = [c for c in display_all.columns if c != "_status"]
        paid_flags = lb_all["PaymentStatus"].tolist() if "PaymentStatus" in lb_all.columns else ["PAID"] * len(lb_all)

        def _style_all(row: pd.Series):
            status = paid_flags[row.name] if row.name < len(paid_flags) else "PAID"
            if status == "UNPAID":
                return ["color: #6B7280"] * len(row)
            idx = row.name
            if idx == 0:
                return ["background-color: rgba(212,160,23,0.18); font-weight:700"] * len(row)
            if idx == 1:
                return ["background-color: rgba(192,192,192,0.10)"] * len(row)
            if idx == 2:
                return ["background-color: rgba(205,127,50,0.10)"] * len(row)
            return [""] * len(row)

        st.dataframe(
            display_all[show_cols_all].style.apply(_style_all, axis=1),
            use_container_width=True, hide_index=True,
        )
        paid_n   = sum(1 for s in paid_flags if s == "PAID")
        unpaid_n = len(paid_flags) - paid_n
        st.caption(f"Paid: {paid_n}  ·  Unpaid: {unpaid_n}")
