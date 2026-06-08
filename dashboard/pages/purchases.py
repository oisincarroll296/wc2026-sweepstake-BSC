"""Purchases — who has bought what at a glance."""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import get_purchases, get_statuses, get_participants
from dashboard.components.ui import page_header, empty_state

_ROOT = Path(__file__).parent.parent.parent
_now = datetime.now(tz=timezone.utc)
_deadline_key: dict[str, str] = {
    "BuyIn":         "buy_in_deadline",
    "PredictionPack":"prediction_lock",
    "Mulligan":      "mulligan_deadline",
    "NinthTeam":     "ninth_team_draw",
    "Resurrection":  "resurrection_window_close",
    "Insurance":     "group_stage_closes",
}
_deadlines: dict[str, datetime] = {}
_dl_path = _ROOT / "data" / "deadlines.json"
if _dl_path.exists():
    try:
        _raw = json.loads(_dl_path.read_text())
        for _k, _v in _raw.items():
            try:
                _deadlines[_k] = datetime.fromisoformat(_v)
            except Exception:
                pass
    except Exception:
        pass


def _available(pt: str) -> bool:
    key = _deadline_key.get(pt)
    if not key:
        return True
    dl = _deadlines.get(key)
    return dl is None or _now < dl

page_header("Purchases", "Who has bought what — full purchase overview")

# ── How to buy ───────────────────────────────────────────────────────────────
_price_chips = "".join(
    f'<span style="background:#0D1B2A;border:1px solid #2A3A4A;border-radius:6px;'
    f'padding:0.2rem 0.6rem;font-size:0.78rem;color:#F5F5F5;white-space:nowrap">'
    f'{lbl} <strong style="color:#D4A017">€{cost}</strong></span> '
    for _, lbl, cost in [
        ("Buy In", "Buy In", 5), ("Prediction Pack", "Prediction Pack", 5),
        ("Insurance", "Insurance", 2), ("Mulligan", "Mulligan", 3),
        ("Ninth Team", "Ninth Team", 3), ("Resurrection", "Resurrection", 5),
    ]
)
st.markdown(
    '<div style="background:#1A2535;border:1px solid #D4A01744;border-radius:10px;'
    'padding:0.85rem 1.1rem;margin-bottom:1.1rem">'
    '<div style="color:#D4A017;font-weight:700;font-size:0.92rem;margin-bottom:0.45rem">'
    '💳 How to Buy an Add-On</div>'
    '<div style="color:#E5E7EB;font-size:0.84rem;line-height:1.65">'
    '1. Send the money to the <strong style="color:#D4A017">Shared Revolut Pocket</strong> '
    'and include what you\'re buying in the transaction message<br>'
    '2. <strong>Ninth Team</strong> &amp; <strong>Resurrection</strong> — teams are randomly drawn, '
    'no selection needed<br>'
    '3. <strong>Prediction Pack</strong> — send your picks (World Cup winner, Golden Boot, Dark Horse) '
    'in a separate message<br>'
    '4. <strong>Captains</strong> — send your Pre-Tournament and Knockout captain picks separately'
    '</div>'
    f'<div style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.65rem">{_price_chips}</div>'
    '</div>',
    unsafe_allow_html=True,
)

participants = get_participants()
purchases    = get_purchases()
statuses     = get_statuses()

if not participants:
    empty_state("No participants found.")
    st.stop()

# ── Build lookup structures ─────────────────────────────────────────────────
status_map: dict[str, str] = {}
if not statuses.empty:
    for _, r in statuses.iterrows():
        status_map[r["Player"]] = r.get("Status", "UNPAID")

PTYPES = [
    ("BuyIn",         "Buy In",       5),
    ("PredictionPack","Pack",         5),
    ("Insurance",     "Insurance",    2),
    ("Mulligan",      "Mulligan",     3),
    ("NinthTeam",     "Ninth",        3),
    ("Resurrection",  "Resurrection", 5),
]
COSTS = {pt: cost for pt, _, cost in PTYPES}

processed: dict[str, set] = {}
if not purchases.empty:
    for _, r in purchases.iterrows():
        p  = r["Player"]
        pt = r["PurchaseType"]
        processed.setdefault(p, set()).add(pt)

# ── Build matrix ────────────────────────────────────────────────────────────
rows = []
for player in sorted(participants, key=lambda p: (status_map.get(p, "UNPAID") != "PAID", p)):
    has = processed.get(player, set())
    spent = sum(COSTS[pt] for pt in has if pt in COSTS)
    row: dict = {
        "Player": player,
        "Status": status_map.get(player, "UNPAID"),
    }
    for pt, label, _ in PTYPES:
        if pt in has:
            row[label] = "✓"
        elif _available(pt):
            row[label] = "Available"
        else:
            row[label] = "Deadline passed"
    row["Spent"] = f"€{spent}"
    rows.append(row)

df = pd.DataFrame(rows)


def _style(row: pd.Series):
    styles = []
    for col in row.index:
        if col == "Player":
            styles.append("font-weight: 600")
        elif col == "Status":
            if row[col] == "PAID":
                styles.append("color: #6EE7B7; font-weight: 600")
            else:
                styles.append("color: #EF4444; font-weight: 600")
        elif col == "Spent":
            styles.append("color: #D4A017; font-weight: 700")
        elif row[col] == "✓":
            styles.append("color: #6EE7B7; font-weight: 700")
        elif row[col] == "Available":
            styles.append("color: #D4A017; font-weight: 600")
        elif row[col] == "Deadline passed":
            styles.append("color: #4B5563; font-style: italic")
        else:
            styles.append("color: #4B5563")
    return styles


st.dataframe(
    df.style.apply(_style, axis=1),
    use_container_width=True,
    hide_index=True,
)
st.caption("✓ Purchased  ·  Available — message Oisin to buy  ·  Deadline passed — window closed")

# ── Summary strip ───────────────────────────────────────────────────────────
st.divider()
n = len(participants)
r1c1, r1c2 = st.columns(2)
r2c1, r2c2 = st.columns(2)
with r1c1:
    paid_in = sum(1 for p in participants if "BuyIn" in processed.get(p, set()))
    st.metric("Bought In (€5)", f"{paid_in} / {n}")
with r1c2:
    has_pack = sum(1 for p in participants if "PredictionPack" in processed.get(p, set()))
    st.metric("Pred. Packs (€5)", f"{has_pack} / {n}")
with r2c1:
    has_insurance = sum(1 for p in participants if "Insurance" in processed.get(p, set()))
    st.metric("Insurance (€2)", f"{has_insurance} / {n}")
with r2c2:
    from src.competition import calculate_prize_pool
    pool = calculate_prize_pool(purchases)
    st.metric("Total Collected", f"€{pool['current_pot']:.0f}")
