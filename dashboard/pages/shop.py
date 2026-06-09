"""Add-on Shop — self-service purchasing for each participant."""
import sys
import json
import urllib.parse as _urlparse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import yaml
import streamlit as st

from dashboard.data import get_participants, get_purchases
from dashboard.components.ui import page_header

_ROOT = Path(__file__).parent.parent.parent


def _load_config() -> dict:
    p = _ROOT / "config.yaml"
    if p.exists():
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}


_cfg   = _load_config()
_swp   = _cfg.get("sweepstake", {})
BUDGET = int(_swp.get("budget_per_player", 0))
COSTS: dict[str, int] = {k: int(v) for k, v in _swp.get("addon_costs", {}).items()}

# ── Deadlines ──────────────────────────────────────────────────────────────
_now = datetime.now(tz=timezone.utc)
_DL_KEY: dict[str, str] = {
    "PredictionPack": "prediction_lock",
    "Mulligan":       "mulligan_deadline",
    "NinthTeam":      "ninth_team_draw",
    "Resurrection":   "resurrection_window_close",
    "Insurance":      "group_stage_closes",
}
_deadlines: dict[str, datetime] = {}
_dl_path = _ROOT / "data" / "deadlines.json"
if _dl_path.exists():
    try:
        for _k, _v in json.loads(_dl_path.read_text()).items():
            try:
                _deadlines[_k] = datetime.fromisoformat(_v)
            except Exception:
                pass
    except Exception:
        pass


def _open(pt: str) -> bool:
    key = _DL_KEY.get(pt)
    dl  = _deadlines.get(key) if key else None
    return dl is None or _now < dl


# ── Add-on catalogue (BuyIn is admin-only) ─────────────────────────────────
ADDONS = [
    (
        "PredictionPack", "Prediction Pack",
        "Pick your WC Winner, Golden Boot & Dark Horse for bonus prediction points.",
    ),
    (
        "Insurance", "Insurance",
        "Earn bonus points when your Tier 1 teams are knocked out in the group stage.",
    ),
    (
        "Mulligan", "Mulligan",
        "Full redraw of all 8 of your teams. Admin runs the draw after your purchase.",
    ),
    (
        "NinthTeam", "Ninth Team",
        "Get a randomly drawn 9th team from surviving sides. Admin runs the draw after purchase.",
    ),
    (
        "Resurrection", "Resurrection",
        "Replace one eliminated team with a surviving same-tier team. Admin runs the draw after purchase.",
    ),
]

# ── Page ───────────────────────────────────────────────────────────────────
page_header("Add-on Shop", "Buy add-ons for your sweepstake entry")

participants = get_participants()
if not participants:
    st.info("No participants found.")
    st.stop()

# Player identity: URL param → sidebar viewer → picker
url_player     = st.query_params.get("player", "")
sidebar_viewer = st.session_state.get("viewer") or ""
default = (
    url_player if url_player in participants
    else sidebar_viewer if sidebar_viewer in participants
    else ""
)

options     = ["— select your name —"] + participants
default_idx = options.index(default) if default in options else 0
player = st.selectbox("Your name", options, index=default_idx, label_visibility="collapsed")

if player == "— select your name —":
    st.info("Select your name above to open your shop.")
    st.stop()

st.query_params["player"] = player  # keep URL in sync

# Shareable link
try:
    _host = st.context.headers.get("host", "localhost:8502")
except Exception:
    _host = "localhost:8502"
with st.expander("Share my shop link"):
    st.code(f"http://{_host}/shop?player={_urlparse.quote(player)}", language=None)

# ── Budget meter ──────────────────────────────────────────────────────────
purchases = get_purchases()
owned_types: set[str] = set()
if not purchases.empty:
    owned_types = set(purchases.loc[purchases["Player"] == player, "PurchaseType"].tolist())

spent     = sum(COSTS.get(pt, 0) for pt in owned_types if pt != "BuyIn")
remaining = BUDGET - spent

if BUDGET > 0:
    pct       = max(0, min(100, round(remaining / BUDGET * 100)))
    bar_color = "#6EE7B7" if remaining >= 0 else "#EF4444"
    st.markdown(
        f'<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:10px;'
        f'padding:1rem 1.25rem;margin-bottom:1.25rem">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">'
        f'<span style="color:#D4A017;font-weight:700">Your Add-on Budget</span>'
        f'<span style="color:{bar_color};font-weight:800;font-size:1.15rem">€{remaining} left</span>'
        f'</div>'
        f'<div style="background:#0D1B2A;border-radius:4px;height:8px">'
        f'<div style="background:{bar_color};width:{pct}%;height:8px;border-radius:4px"></div>'
        f'</div>'
        f'<div style="color:#6B7280;font-size:0.78rem;margin-top:0.35rem">€{spent} of €{BUDGET} budget spent</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Add-on cards ──────────────────────────────────────────────────────────
st.markdown("### Add-ons")

for pt, label, description in ADDONS:
    cost       = COSTS.get(pt, 0)
    is_owned   = pt in owned_types
    is_open    = _open(pt)
    can_afford = BUDGET == 0 or remaining >= cost

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        if is_owned:
            status_html = '<span style="color:#6EE7B7;font-weight:600">✓ Purchased</span>'
        elif not is_open:
            status_html = '<span style="color:#4B5563;font-style:italic">Deadline passed</span>'
        elif not can_afford:
            status_html = f'<span style="color:#EF4444;font-weight:600">Over budget (need €{cost}, have €{remaining})</span>'
        else:
            status_html = '<span style="color:#D4A017;font-weight:600">Available</span>'

        st.markdown(
            f'<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:8px;'
            f'padding:0.8rem 1rem;margin-bottom:0.5rem">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<span style="font-weight:700;color:#F5F5F5;font-size:0.97rem">{label}</span>'
            f'<span style="color:#D4A017;font-weight:700">€{cost}</span>'
            f'</div>'
            f'<div style="color:#9CA3AF;font-size:0.83rem;margin:0.2rem 0 0.35rem">{description}</div>'
            f'{status_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_btn:
        st.write("")  # vertical alignment nudge
        if is_owned:
            st.button("Owned", key=f"btn_{pt}", disabled=True)
        elif not is_open:
            st.button("Closed", key=f"btn_{pt}", disabled=True)
        elif not can_afford:
            st.button(f"€{cost}", key=f"btn_{pt}", disabled=True)
        else:
            if st.button(f"Buy  €{cost}", key=f"btn_{pt}", type="primary"):
                from src.competition import add_purchase, load_purchases, PURCHASES_PATH
                _ts  = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                _all = load_purchases()
                _upd = add_purchase(player, pt, reference="self-service", purchases=_all, timestamp=_ts)
                _upd.to_csv(PURCHASES_PATH, index=False)
                st.cache_data.clear()
                st.rerun()

st.divider()
st.caption("BuyIn is handled by the admin.  Mulligan / Ninth Team / Resurrection draws are run by the admin after your purchase is recorded.")
