"""Leaderboard — Prize standings + All Players with full score breakdown."""
import sys, math
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import streamlit as st
import pandas as pd
from dashboard.data import (
    get_prize_leaderboard, get_overall_leaderboard,
    get_prize_pool, get_remaining_potential, get_player_goals_wins,
)
from dashboard.config import PLOTLY_LAYOUT, COLORS
from dashboard.components.ui import page_header, empty_state

page_header("Leaderboard", "Prize standings and full score breakdown")

pool = get_prize_pool()
lb_prize = get_prize_leaderboard()
lb_all   = get_overall_leaderboard()
pot      = get_remaining_potential()
_gw      = get_player_goals_wins()
_goals_map = dict(zip(_gw["Player"], _gw["Goals"])) if not _gw.empty else {}
_wins_map  = dict(zip(_gw["Player"], _gw["Wins"]))  if not _gw.empty else {}

tab_prize, tab_all = st.tabs(["🏆 Prize Standings", "🌍 All Players"])

# ── shared helpers ─────────────────────────────────────────────────────────

BREAKDOWN_COLS = [
    "GoalsPoints", "CleanSheetPoints", "WinPoints", "WinBonusPoints",
    "HatTrickPoints", "UpsetPoints", "ProgressionPoints",
    "CaptainBonus", "InsuranceBonus",
    "ShirtPoints", "GKGoalPoints", "RedCardPoints", "FirstElimPoints",
    "PredictionBonus",
]
BREAKDOWN_LABELS = {
    "GoalsPoints":      "Goals",
    "CleanSheetPoints": "Clean Sheets",
    "WinPoints":        "Wins",
    "WinBonusPoints":   "Pen/Comeback",
    "HatTrickPoints":   "Hat Tricks",
    "UpsetPoints":      "Upset Wins",
    "ProgressionPoints":"Progression",
    "CaptainBonus":     "Captain",
    "InsuranceBonus":   "Insurance",
    "ShirtPoints":      "Shirt Off",
    "GKGoalPoints":     "GK Goal",
    "RedCardPoints":    "Red Cards",
    "FirstElimPoints":  "1st Elim",
    "PredictionBonus":  "Predictions",
    # legacy key — kept so existing cached DataFrames don't break
    "BasePoints":       "Match Pts",
    "SpecialBonus":     "Special",
}
BREAKDOWN_COLORS = {
    "GoalsPoints":      "#3B82F6",
    "CleanSheetPoints": "#06B6D4",
    "WinPoints":        "#10B981",
    "WinBonusPoints":   "#34D399",
    "HatTrickPoints":   "#F59E0B",
    "UpsetPoints":      "#EF4444",
    "ProgressionPoints":"#8B5CF6",
    "CaptainBonus":     "#D4A017",
    "InsuranceBonus":   "#15803D",
    "ShirtPoints":      "#EC4899",
    "GKGoalPoints":     "#F97316",
    "RedCardPoints":    "#991B1B",
    "FirstElimPoints":  "#6366F1",
    "PredictionBonus":  "#B91C1C",
    # legacy
    "BasePoints":       "#4A6FA5",
    "SpecialBonus":     "#7C3AED",
}


_BREAKDOWN_GROUPS = [
    ("Goals",    ["GoalsPoints"],                                              "#3B82F6"),
    ("CS",       ["CleanSheetPoints"],                                         "#06B6D4"),
    ("Wins",     ["WinPoints"],                                                "#10B981"),
    ("Pen/CB",   ["WinBonusPoints"],                                           "#34D399"),
    ("H-Trick",  ["HatTrickPoints"],                                           "#F59E0B"),
    ("Upsets",   ["UpsetPoints"],                                              "#EF4444"),
    ("Progress", ["ProgressionPoints"],                                        "#8B5CF6"),
    ("Captain",  ["CaptainBonus"],                                             "#D4A017"),
    ("Insure",   ["InsuranceBonus"],                                           "#15803D"),
    ("Special",  ["ShirtPoints", "GKGoalPoints", "FirstElimPoints"],           "#EC4899"),
    ("RedCards", ["RedCardPoints"],                                            "#991B1B"),
    ("Preds",    ["PredictionBonus"],                                          "#B91C1C"),
]


def _breakdown_table(lb: pd.DataFrame) -> None:
    """Per-player score breakdown table — one row per player, one column per category."""
    if lb.empty:
        return

    th = "color:#9CA3AF;font-size:0.62rem;font-weight:600;padding:0.28rem 0.5rem;white-space:nowrap;text-align:center"
    header = f'<th style="{th};text-align:left">Player</th>'
    for label, _, color in _BREAKDOWN_GROUPS:
        header += f'<th style="{th};border-top:2px solid {color}">{label}</th>'
    header += f'<th style="{th};text-align:right">Total</th>'

    rows_html = ""
    for _, row in lb.iterrows():
        rank   = int(row.get("Rank", 0))
        player = row["Player"]
        total  = float(row.get("TotalPoints", 0))
        bg     = "background:rgba(212,160,23,0.10);" if rank == 1 else ""
        fw     = "700" if rank == 1 else "400"
        td     = "padding:0.26rem 0.5rem;font-size:0.8rem;text-align:center;"

        cells = f'<td style="{td}text-align:left;color:#F1F5F9;font-weight:{fw}">{player}</td>'
        for _, src_cols, color in _BREAKDOWN_GROUPS:
            val = sum(float(row.get(c, 0)) for c in src_cols if c in lb.columns)
            if val == 0:
                cells += f'<td style="{td}color:#374151">—</td>'
            elif val > 0:
                cells += f'<td style="{td}color:{color};font-weight:600">{val:.0f}</td>'
            else:
                cells += f'<td style="{td}color:#EF4444;font-weight:600">{val:.0f}</td>'

        cells += f'<td style="{td}text-align:right;color:#F1F5F9;font-weight:700">{total:.0f}</td>'
        rows_html += f'<tr style="border-top:1px solid #1E293B;{bg}">{cells}</tr>'

    st.markdown(
        '<div style="overflow-x:auto;margin-bottom:0.5rem">'
        '<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr style="background:#0D1B2A">{header}</tr></thead>'
        f'<tbody style="background:#131D2A">{rows_html}</tbody>'
        '</table></div>',
        unsafe_allow_html=True,
    )


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
        goals = _goals_map.get(player, 0)
        wins  = _wins_map.get(player, 0)
        r = {
            "":         medal,
            "Player":   player,
            "Total":    f"{pts:.0f}",
            "Gap":      f"{pts - leader_pts:+.0f}" if rank > 1 else "—",
            "Match":    f"{base:.0f}",
            "⚽ Goals": str(goals) if goals else "—",
            "🏆 Wins":  str(wins)  if wins  else "—",
            "Captain":  f"+{cap:.0f}" if cap else "—",
            "Special":  f"{spec:+.0f}" if spec else "—",
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

        # Score breakdown table
        st.subheader("Score Breakdown")
        _breakdown_table(lb_prize)

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
            "Potential = max remaining progression points · "
            "Chance = softmax win probability"
        )


# ═══════════════════════════════════════════════════════════════════
# TAB 2 — ALL PLAYERS
# ═══════════════════════════════════════════════════════════════════
with tab_all:
    st.info("Players marked **UNPAID** appear here but cannot win prizes.", icon="ℹ️")

    if lb_all.empty:
        empty_state("No players found.")
    else:
        st.subheader("Score Breakdown")
        _breakdown_table(lb_all)

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
