"""Prize Leaderboard — paid players only, with medal highlights."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import math

import streamlit as st
import pandas as pd

from dashboard.data import get_prize_leaderboard, get_prize_pool, get_remaining_potential
from dashboard.components.ui import page_header, empty_state


page_header("🏆 Prize Leaderboard", "Paid players — eligible for prizes")

pool = get_prize_pool()
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("💰 Total Pot", f"€{pool.get('current_pot',0):.2f}")
with c2: st.metric("🥇 1st", f"€{pool.get('first_prize',0):.2f}")
with c3: st.metric("🥈 2nd", f"€{pool.get('second_prize',0):.2f}")
with c4: st.metric("🥉 3rd", f"€{pool.get('third_prize',0):.2f}")

st.divider()

lb = get_prize_leaderboard()
if lb.empty:
    empty_state("No paid players yet — leaderboard will appear once players pay in.")
    st.stop()

# Build display table
leader_pts = float(lb.iloc[0]["TotalPoints"]) if "TotalPoints" in lb.columns else 0.0

# Win probability via softmax: amplifies differences so leader stands out meaningfully.
# Temperature = spread/5 so a gap equal to 20% of the range is ~55% more likely.
_scores = lb["TotalPoints"].astype(float).tolist()
_min_s  = min(_scores) if _scores else 0
_spread = (max(_scores) - _min_s) if len(_scores) > 1 else 1
_temp   = max(_spread / 5, 1.0)
_exps   = [math.exp((s - _min_s) / _temp) for s in _scores]
_total  = sum(_exps) or 1
_probs  = [e / _total * 100 for e in _exps]

_potential = get_remaining_potential()

rows = []
for i, (_, row) in enumerate(lb.iterrows()):
    rank = int(row.get("Rank", 0))
    pts  = float(row.get("TotalPoints", 0))
    gap  = pts - leader_pts
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
    prize_pos = {1: "Winner", 2: "Runner-up", 3: "3rd Place"}.get(rank, "—")
    tb = "Yes" if row.get("TiebreakerApplied", False) else ""
    chance = _probs[i]
    player = row.get("Player", "")
    pot = _potential.get(player, 0)
    rows.append({
        "": medal,
        "Player":      player,
        "Points":      f"{pts:.0f}",
        "Potential":   f"+{pot:.0f}",
        "Gap":         f"{gap:+.0f}" if rank > 1 else "—",
        "Chance":      f"{chance:.1f}%",
        "Tiebreak":    tb,
        "Prize":       prize_pos,
    })

display = pd.DataFrame(rows)


def _style(row: pd.Series):
    rank_idx = list(display.index).index(row.name)
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
st.caption("Chance % = softmax win probability · Potential = max progression pts still earnable from surviving teams.")

# Detailed breakdown toggle
with st.expander("Show full points breakdown"):
    detail_cols = [c for c in [
        "Rank", "Player", "BasePoints", "CaptainBonus",
        "InsuranceBonus", "PredictionBonus", "TotalPoints",
    ] if c in lb.columns]
    st.dataframe(lb[detail_cols], use_container_width=True, hide_index=True)
