"""Overall Leaderboard — all players including unpaid."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import get_overall_leaderboard, get_remaining_potential
from dashboard.components.ui import page_header, empty_state


page_header("🌍 Overall Leaderboard", "All players — unpaid players are not eligible for prizes")

lb = get_overall_leaderboard()

if lb.empty:
    empty_state("No players found.  Add participants via the Admin page.")
    st.stop()

st.info("Players marked **UNPAID** are not eligible for prizes even if ranked highly.", icon="⚠️")

_potential = get_remaining_potential()
rows = []
leader_pts = float(lb.iloc[0]["TotalPoints"]) if "TotalPoints" in lb.columns else 0.0

for _, row in lb.iterrows():
    rank   = int(row.get("Rank", 0))
    pts    = float(row.get("TotalPoints", 0))
    status = row.get("PaymentStatus", "UNPAID")
    medal  = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
    player = row.get("Player", "")
    pot    = _potential.get(player, 0)
    rows.append({
        "":          medal,
        "Player":    player,
        "Points":    f"{pts:.0f}",
        "Potential": f"+{pot:.0f}",
        "Gap":       f"{pts - leader_pts:+.0f}" if rank > 1 else "—",
        "Status":    status,
    })

display = pd.DataFrame(rows)
lb_status = lb["PaymentStatus"].tolist() if "PaymentStatus" in lb.columns else ["PAID"] * len(lb)


def _style(row: pd.Series):
    status = lb_status[row.name]
    if status == "UNPAID":
        return ["color: #6B7280"] * len(row)
    rank_idx = row.name
    if rank_idx == 0:
        return ["background-color: rgba(212,160,23,0.20); font-weight:700"] * len(row)
    if rank_idx == 1:
        return ["background-color: rgba(192,192,192,0.12)"] * len(row)
    if rank_idx == 2:
        return ["background-color: rgba(205,127,50,0.12)"] * len(row)
    return [""] * len(row)


st.dataframe(
    display.style.apply(_style, axis=1),
    use_container_width=True, hide_index=True,
)

# Count summary
paid_n   = int((display["Status"] == "PAID").sum())
unpaid_n = int((display["Status"] == "UNPAID").sum())
st.caption(f"✅ {paid_n} paid  ·  ⚠️ {unpaid_n} unpaid")
