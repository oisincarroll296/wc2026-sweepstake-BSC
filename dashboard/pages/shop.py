"""Add-on Shop — self-service purchasing for each participant."""
import sys
import json
import urllib.parse as _urlparse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import yaml
import streamlit as st
import pandas as pd

import os
import tempfile

from dashboard.data import get_participants, get_purchases, get_assignments, get_teams, get_tier_map
from dashboard.components.ui import page_header
from src.competition import (
    add_purchase, load_purchases, load_player_status, PURCHASES_PATH,
)
from src.event_engine import process_pending_purchases


def _atomic_csv_write(df: pd.DataFrame, path: Path) -> None:
    """Write DataFrame to CSV atomically via temp-file + os.replace."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.close(fd)
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise

_ROOT = Path(__file__).parent.parent.parent
_PLAYERS_PATH = _ROOT / "data" / "players.csv"


# ── Config ─────────────────────────────────────────────────────────────────
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
        "Pick your WC Winner, Runner-Up, Bronze, Golden Boot, Dark Horse & First Knocked Out for bonus points.",
    ),
    (
        "Insurance", "Insurance",
        "Earn bonus points when your Tier 1 teams are knocked out in the group stage.",
    ),
    (
        "Mulligan", "Mulligan",
        "Full redraw of all 12 of your teams. Admin runs the draw after your purchase.",
    ),
    (
        "NinthTeam", "Ninth Team",
        "Get a randomly drawn 9th team from surviving sides. Admin runs the draw after your purchase.",
    ),
    (
        "Resurrection", "Resurrection",
        "Replace one eliminated team with a surviving same-tier team. You'll pick which team in the next step — admin draws the replacement.",
    ),
]


# ── Helpers ────────────────────────────────────────────────────────────────
def _commit_purchase(player: str, pt: str, selection: str = "") -> None:
    """Write purchase atomically, marking PAID if it's a BuyIn."""
    ts       = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    all_p    = load_purchases()
    updated  = add_purchase(player, pt, reference="self-service",
                            purchases=all_p, timestamp=ts, selection=selection)
    statuses = load_player_status()
    updated, updated_statuses, _ = process_pending_purchases(updated, statuses)
    _atomic_csv_write(updated, PURCHASES_PATH)
    _atomic_csv_write(updated_statuses, _PLAYERS_PATH)
    st.cache_data.clear()


def _save_picks(player: str, picks: dict) -> None:
    """Persist prediction picks into players.csv atomically."""
    df = pd.read_csv(_PLAYERS_PATH, dtype=str).fillna("") if _PLAYERS_PATH.exists() else pd.DataFrame()
    if df.empty:
        return
    mask = df["Player"] == player
    for col, val in picks.items():
        if col not in df.columns:
            df[col] = ""
        df.loc[mask, col] = val
    _atomic_csv_write(df, _PLAYERS_PATH)
    st.cache_data.clear()


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

st.query_params["player"] = player

try:
    _host = st.context.headers.get("host", "localhost:8502")
    _scheme = "https" if "streamlit.app" in _host else "http"
except Exception:
    _host = "localhost:8502"
    _scheme = "http"
with st.expander("Share my shop link"):
    st.code(f"{_scheme}://{_host}/shop?player={_urlparse.quote(player)}", language=None)

# ── Load data ──────────────────────────────────────────────────────────────
purchases   = get_purchases()
assignments = get_assignments()
teams_df    = get_teams()
tier_map    = get_tier_map()

owned_types: set[str] = set()
if not purchases.empty:
    owned_types = set(purchases.loc[purchases["Player"] == player, "PurchaseType"].tolist())

player_teams = sorted(assignments.get(player, []))
all_teams    = sorted(teams_df["Team"].tolist()) if not teams_df.empty else []
t3_t4_teams  = sorted([t for t, ti in tier_map.items() if ti in (3, 4) and t not in player_teams])

# ── Budget meter ──────────────────────────────────────────────────────────
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
        f'<div style="color:#6B7280;font-size:0.78rem;margin-top:0.35rem">'
        f'€{spent} of €{BUDGET} budget spent</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Confirm dialogs ────────────────────────────────────────────────────────

@st.dialog("Confirm Purchase")
def _dlg_simple(pt: str, label: str, cost: int) -> None:
    st.markdown(f"Buy **{label}** for **€{cost}**?")
    st.caption("This will be recorded immediately and deducted from your budget.")
    c1, c2 = st.columns(2)
    if c1.button("Confirm", type="primary", use_container_width=True):
        _commit_purchase(player, pt)
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("Prediction Pack — Enter Your Picks")
def _dlg_prediction_pack(cost: int) -> None:
    st.markdown(f"Enter your predictions below, then confirm your **€{cost}** purchase.")
    st.caption("Picks are saved with your purchase and locked in immediately.")

    # Pre-fill existing picks if any
    existing: dict = {}
    if _PLAYERS_PATH.exists():
        _pdf = pd.read_csv(_PLAYERS_PATH, dtype=str).fillna("")
        _row = _pdf[_pdf["Player"] == player]
        if not _row.empty:
            existing = _row.iloc[0].to_dict()

    def _ev(col: str) -> str:
        v = existing.get(col, "")
        return str(v) if v and str(v) != "nan" else ""

    opts_all  = [""] + all_teams
    opts_t34  = [""] + t3_t4_teams

    c1, c2 = st.columns(2)
    with c1:
        cur = _ev("WorldCupWinner")
        wcw = st.selectbox("World Cup Winner", opts_all,
                           index=opts_all.index(cur) if cur in opts_all else 0)
        cur = _ev("BronzeMedal")
        bm  = st.selectbox("Bronze Medal", opts_all,
                           index=opts_all.index(cur) if cur in opts_all else 0)
        gb  = st.text_input("Golden Boot (player name)", value=_ev("GoldenBoot"),
                            placeholder="e.g. Mbappé")
    with c2:
        cur = _ev("RunnerUp")
        ru  = st.selectbox("Runner-Up", opts_all,
                           index=opts_all.index(cur) if cur in opts_all else 0)
        cur = _ev("DarkHorse")
        dh  = st.selectbox("Dark Horse (Tier 3/4, not your team)", opts_t34,
                           index=opts_t34.index(cur) if cur in opts_t34 else 0)
        cur = _ev("FirstKnockedOut")
        fko = st.selectbox("First Knocked Out", opts_all,
                           index=opts_all.index(cur) if cur in opts_all else 0)

    st.divider()
    ca, cb = st.columns(2)
    if ca.button("Buy & Save Picks", type="primary", use_container_width=True):
        _commit_purchase(player, "PredictionPack")
        _save_picks(player, {
            "WorldCupWinner": wcw, "RunnerUp": ru, "BronzeMedal": bm,
            "GoldenBoot": gb, "DarkHorse": dh, "FirstKnockedOut": fko,
        })
        st.rerun()
    if cb.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("Resurrection — Pick Your Team")
def _dlg_resurrection(cost: int) -> None:
    st.markdown(f"Pick which of your teams to resurrect, then confirm your **€{cost}** purchase.")
    st.caption("Admin will draw a surviving same-tier replacement team after your purchase is recorded.")

    if not player_teams:
        st.warning("No teams allocated yet — check back after the initial draw.")
        if st.button("Close"):
            st.rerun()
        return

    eliminated_team = st.selectbox(
        "Which of your teams to resurrect?",
        ["— select —"] + player_teams,
    )

    st.divider()
    ca, cb = st.columns(2)
    disabled = eliminated_team == "— select —"
    if ca.button("Buy & Submit", type="primary", use_container_width=True, disabled=disabled):
        _commit_purchase(player, "Resurrection", selection=eliminated_team)
        st.rerun()
    if cb.button("Cancel", use_container_width=True):
        st.rerun()


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
            status_html = (
                f'<span style="color:#EF4444;font-weight:600">'
                f'Over budget (need €{cost}, have €{remaining})</span>'
            )
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
        st.write("")
        if is_owned:
            st.button("Owned", key=f"btn_{pt}", disabled=True)
        elif not is_open:
            st.button("Closed", key=f"btn_{pt}", disabled=True)
        elif not can_afford:
            st.button(f"€{cost}", key=f"btn_{pt}", disabled=True)
        else:
            if st.button(f"Buy  €{cost}", key=f"btn_{pt}", type="primary"):
                if pt == "PredictionPack":
                    _dlg_prediction_pack(cost)
                elif pt == "Resurrection":
                    _dlg_resurrection(cost)
                else:
                    _dlg_simple(pt, label, cost)

st.divider()
st.caption(
    "Purchasing here records your add-on — you still need to send payment to Oisin (Revolut). "
    "Mulligan / Ninth Team / Resurrection draws are run by Oisin once your payment clears. "
    "BuyIn is handled by Oisin directly."
)
