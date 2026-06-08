"""Predictions Centre — winner, golden boot, dark horse picks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import (
    get_predictions_centre_data, is_predictions_locked,
    get_predictions, get_participants, get_purchases,
    get_deadlines, countdown,
)
from dashboard.components.ui import page_header, empty_state


page_header("Predictions Centre", "World Cup Winner · Golden Boot · Dark Horse picks")

locked = is_predictions_locked()
participants = get_participants() or []
preds_df = get_predictions()

# ── Status banner ──────────────────────────────────────────────────────────
if locked:
    st.success("Predictions are locked and revealed — all picks are now public.", icon="🔓")
else:
    # Prediction lock countdown
    deadlines = get_deadlines()
    lock_iso = deadlines.get("prediction_lock", "")
    cd = countdown(lock_iso) if lock_iso else "—"
    cd_line = (
        f'<br><span style="color:#7C3AED;font-size:1.1rem;font-weight:700">'
        f'{cd} remaining</span>'
        if cd not in ("—", "PASSED") else ""
    )

    try:
        from datetime import datetime, timezone, timedelta
        _IST = timezone(timedelta(hours=1))
        _lock_dt = datetime.fromisoformat(lock_iso).astimezone(_IST)
        _lock_label = f"{_lock_dt.day} {_lock_dt.strftime('%b %H:%M')}"
    except Exception:
        _lock_label = "the prediction lock deadline"
    st.markdown(
        '<div class="lock-banner">'
        '<span style="font-size:1.4rem">🔒</span><br>'
        '<strong style="color:#C4B5FD;font-size:1.05rem">Predictions Hidden</strong><br>'
        '<span style="color:#9CA3AF;font-size:0.85rem">'
        f'All picks are sealed until {_lock_label}.'
        '</span>'
        f'{cd_line}'
        '</div>',
        unsafe_allow_html=True,
    )

    # Show who has submitted without revealing what they picked
    st.subheader("Pack Holders")
    purchases_df = get_purchases()
    pack_holders: set[str] = set()
    if not purchases_df.empty and "PurchaseType" in purchases_df.columns:
        pack_holders = set(
            purchases_df[purchases_df["PurchaseType"] == "PredictionPack"]["Player"].tolist()
        )

    def _has_picks(player: str) -> bool:
        if preds_df.empty:
            return False
        row = preds_df[preds_df["Player"] == player]
        if row.empty:
            return False
        r = row.iloc[0]
        return any(str(r.get(col, "")).strip() for col in ["WorldCupWinner", "GoldenBoot", "DarkHorse"])

    rows = []
    for p in sorted(participants):
        if p in pack_holders:
            status = "Submitted ✓" if _has_picks(p) else "Pending"
        else:
            status = "No Pack"
        rows.append({"Player": p, "Status": status})
    status_df = pd.DataFrame(rows)

    def _style(row):
        if row["Status"].startswith("Submitted"):
            return ["", "color: #6EE7B7; font-weight: 600"]
        if row["Status"] == "Pending":
            return ["", "color: #D4A017"]
        return ["", "color: #6B7280"]

    st.dataframe(
        status_df.style.apply(_style, axis=1),
        use_container_width=True, hide_index=True,
    )
    st.stop()

# ── Predictions revealed ───────────────────────────────────────────────────
data = get_predictions_centre_data()

if not data or preds_df.empty:
    empty_state("No predictions submitted.")
    st.stop()

col1, col2, col3 = st.columns(3)

def _pick_card(col, title: str, icon: str, picks: dict):
    with col:
        st.subheader(f"{icon} {title}")
        if not picks:
            st.markdown(
                '<div class="card"><span style="color:#9CA3AF">No picks submitted</span></div>',
                unsafe_allow_html=True,
            )
            return
        for choice, players in sorted(picks.items(), key=lambda x: -len(x[1])):
            count = len(players)
            players_str = ", ".join(sorted(players))
            st.markdown(
                f'<div class="card" style="margin-bottom:0.4rem">'
                f'<p style="margin:0;font-weight:600;color:#F5F5F5">{choice}</p>'
                f'<p style="margin:0.1rem 0 0;color:#9CA3AF;font-size:0.8rem">'
                f'{players_str} ({count})</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

_pick_card(col1, "World Cup Winner", "🏆", data.get("world_cup_winner", {}))
_pick_card(col2, "Golden Boot",      "👟", data.get("golden_boot", {}))
_pick_card(col3, "Dark Horse",       "🌟", data.get("dark_horse", {}))

st.divider()
st.subheader("All Picks")
if not preds_df.empty:
    st.dataframe(preds_df, use_container_width=True, hide_index=True)
