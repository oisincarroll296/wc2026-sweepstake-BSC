"""Add-on Shop — self-service purchasing, picks, and captain selections."""
import sys
import json
import urllib.parse as _urlparse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import get_participants, get_purchases, get_assignments, get_teams, get_tier_map
from dashboard.components.ui import page_header
from dashboard.github_sync import push_file
from src.competition import (
    add_purchase, load_purchases, load_player_status, PURCHASES_PATH,
)
from src.event_engine import process_pending_purchases

_ROOT         = Path(__file__).parent.parent.parent
_PLAYERS_PATH = _ROOT / "data" / "players.csv"

# ── Deadline colours ────────────────────────────────────────────────────────
_GRP = "#F59E0B"   # amber — before group stage closes
_KO  = "#22D3EE"   # cyan  — before knockout stage

# ── Add-on costs ─────────────────────────────────────────────────────────────
COSTS: dict[str, int] = {
    "PredictionPack": 5,
    "Mulligan":       3,
    "NinthTeam":      3,
    "Resurrection":   5,
    "Insurance":      2,
}

# ── Deadlines ─────────────────────────────────────────────────────────────────
_now = datetime.now(tz=timezone.utc)

_DL_KEY: dict[str, str] = {
    "PredictionPack":       "prediction_lock",
    "Mulligan":             "mulligan_deadline",
    "NinthTeam":            "ninth_team_draw",
    "Resurrection":         "resurrection_window_close",
    "Insurance":            "group_stage_closes",
    "PreTournamentCaptain": "pre_tournament_captain",
    "KnockoutCaptain":      "knockout_captain_deadline",
}
_DL_CAT: dict[str, str] = {
    "PredictionPack":       "group",
    "Mulligan":             "group",
    "Insurance":            "group",
    "PreTournamentCaptain": "group",
    "NinthTeam":            "knockout",
    "Resurrection":         "knockout",
    "KnockoutCaptain":      "knockout",
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


def _open(key: str) -> bool:
    dl = _deadlines.get(_DL_KEY.get(key, ""))
    return dl is None or _now < dl


def _fmt_dl(key: str) -> str:
    dt = _deadlines.get(_DL_KEY.get(key, ""))
    if dt is None:
        return "No deadline"
    d = dt.astimezone()
    return f"{d.day} {d.strftime('%b, %H:%M')}"


def _dl_badge(key: str) -> str:
    is_open = _open(key)
    if is_open:
        color = _GRP if _DL_CAT.get(key) == "group" else _KO
        label = f"⏰ {_fmt_dl(key)}"
    else:
        color = "#6B7280"
        label = "🔒 Closed"
    return (
        f'<span style="background:{color}22;border:1px solid {color};border-radius:4px;'
        f'padding:0.1rem 0.4rem;font-size:0.71rem;color:{color};white-space:nowrap">'
        f'{label}</span>'
    )


# ── Add-on catalogue ─────────────────────────────────────────────────────────
ADDONS = [
    ("PredictionPack", "Prediction Pack",
     "Pick your WC Winner, Runner-Up, Bronze, Golden Boot, Dark Horse & First Knocked Out."),
    ("Insurance", "Insurance",
     "+25 pts per Tier 1 team knocked out in the group stage or R32 (max +50 if both exit early)."),
    ("Mulligan", "Mulligan",
     "Full redraw of all your teams. Admin runs the draw after your purchase."),
    ("NinthTeam", "Ninth Team",
     "Get a randomly drawn 9th team from surviving sides after the group stage."),
    ("Resurrection", "Resurrection",
     "Replace one eliminated team with a surviving same-tier team. Pick which team below."),
]


# ── Data helpers ──────────────────────────────────────────────────────────────
def _load_player_row(player: str) -> dict:
    if not _PLAYERS_PATH.exists():
        return {}
    df = pd.read_csv(_PLAYERS_PATH, dtype=str).fillna("")
    row = df[df["Player"] == player]
    return row.iloc[0].to_dict() if not row.empty else {}


def _get_budget(player: str) -> int:
    row = _load_player_row(player)
    try:
        return int(float(row.get("Budget", 0) or 0))
    except (ValueError, TypeError):
        return 0


# ── Write helpers ─────────────────────────────────────────────────────────────
def _commit_purchase(player: str, pt: str, selection: str = "") -> None:
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    all_p = load_purchases()
    updated = add_purchase(player, pt, reference="self-service",
                           purchases=all_p, timestamp=ts, selection=selection)
    statuses = load_player_status()
    updated, updated_statuses, _ = process_pending_purchases(updated, statuses)
    updated.to_csv(PURCHASES_PATH, index=False)
    updated_statuses.to_csv(_PLAYERS_PATH, index=False)
    st.cache_data.clear()
    push_file(Path(PURCHASES_PATH), "data/purchases.csv", f"Purchase: {player} {pt}")
    push_file(_PLAYERS_PATH, "data/players.csv", f"Purchase: {player} {pt}")


def _cancel_purchase(player: str, pt: str) -> None:
    all_p = load_purchases()
    mask = (all_p["Player"] == player) & (all_p["PurchaseType"] == pt)
    idxs = all_p[mask].index
    if len(idxs) > 0:
        all_p = all_p.drop(idxs[-1])
    all_p.to_csv(PURCHASES_PATH, index=False)
    st.cache_data.clear()
    push_file(Path(PURCHASES_PATH), "data/purchases.csv", f"Cancel: {player} {pt}")


def _save_picks(player: str, picks: dict) -> None:
    if not _PLAYERS_PATH.exists():
        return
    df = pd.read_csv(_PLAYERS_PATH, dtype=str).fillna("")
    mask = df["Player"] == player
    for col, val in picks.items():
        if col not in df.columns:
            df[col] = ""
        df.loc[mask, col] = val
    df.to_csv(_PLAYERS_PATH, index=False)
    st.cache_data.clear()
    push_file(_PLAYERS_PATH, "data/players.csv", f"Picks: {player}")


def _save_resurrection_selection(player: str, team: str) -> None:
    all_p = load_purchases()
    mask = (all_p["Player"] == player) & (all_p["PurchaseType"] == "Resurrection")
    if mask.any():
        all_p.loc[mask.values.nonzero()[0][-1], "Selection"] = team
        all_p.to_csv(PURCHASES_PATH, index=False)
        st.cache_data.clear()
        push_file(Path(PURCHASES_PATH), "data/purchases.csv",
                  f"Resurrection selection: {player} → {team}")


# ── Page ──────────────────────────────────────────────────────────────────────
page_header("Add-on Shop", "Buy add-ons, enter picks, and set your captains")

st.info(
    "💡 **Budget = what you've put into the shared Revolut pocket.** "
    "Oisin credits your budget manually when money arrives. "
    "**The app updates every evening** when Oisin pushes the latest data — "
    "your purchases and picks are saved immediately but visible live after the next push.",
)

# ── Player selector ───────────────────────────────────────────────────────────
participants = get_participants()
if not participants:
    st.warning("No participants found.")
    st.stop()

url_player     = st.query_params.get("player", "")
sidebar_viewer = st.session_state.get("viewer") or ""
default = (
    url_player     if url_player     in participants else
    sidebar_viewer if sidebar_viewer in participants else ""
)
options     = ["— select your name —"] + participants
default_idx = options.index(default) if default in options else 0
player = st.selectbox("Your name", options, index=default_idx, label_visibility="collapsed")

if player == "— select your name —":
    st.info("Select your name above to open your shop.")
    st.stop()

st.query_params["player"] = player

try:
    _host   = st.context.headers.get("host", "localhost:8502")
    _scheme = "https" if "streamlit.app" in _host else "http"
except Exception:
    _host, _scheme = "localhost:8502", "http"

with st.expander("Share my shop link"):
    st.code(f"{_scheme}://{_host}/shop?player={_urlparse.quote(player)}", language=None)

# ── Load data ─────────────────────────────────────────────────────────────────
purchases    = get_purchases()
assignments  = get_assignments()
teams_df     = get_teams()
tier_map     = get_tier_map()
player_row   = _load_player_row(player)

owned_types: set[str] = set()
res_selection: str = ""
if not purchases.empty:
    player_purs = purchases[purchases["Player"] == player]
    owned_types = set(player_purs["PurchaseType"].tolist())
    res_rows    = player_purs[player_purs["PurchaseType"] == "Resurrection"]
    if not res_rows.empty:
        res_selection = str(res_rows.iloc[-1].get("Selection", "") or "")

player_teams = sorted(assignments.get(player, []))
all_teams    = sorted(teams_df["Team"].tolist()) if not teams_df.empty else []
t3_t4_teams  = sorted([t for t, ti in tier_map.items() if ti in (3, 4) and t not in player_teams])

# ── Budget meter ──────────────────────────────────────────────────────────────
budget    = _get_budget(player)
spent     = sum(COSTS.get(pt, 0) for pt in owned_types if pt in COSTS)
remaining = budget - spent

if budget > 0:
    pct       = max(0, min(100, round(remaining / budget * 100)))
    bar_color = "#6EE7B7" if remaining >= 0 else "#EF4444"
    st.markdown(
        f'<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:10px;'
        f'padding:1rem 1.25rem;margin-bottom:1.25rem">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">'
        f'<span style="color:#D4A017;font-weight:700">Your Budget</span>'
        f'<span style="color:{bar_color};font-weight:800;font-size:1.15rem">€{remaining} remaining</span>'
        f'</div>'
        f'<div style="background:#0D1B2A;border-radius:4px;height:8px">'
        f'<div style="background:{bar_color};width:{pct}%;height:8px;border-radius:4px"></div>'
        f'</div>'
        f'<div style="color:#6B7280;font-size:0.78rem;margin-top:0.35rem">'
        f'€{spent} spent of €{budget} deposited into the Revolut pocket</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.warning("Your budget hasn't been credited yet — ask Oisin once your payment is in the Revolut pocket.")

# ── Dialogs ───────────────────────────────────────────────────────────────────

@st.dialog("Confirm Purchase")
def _dlg_simple(pt: str, label: str, cost: int) -> None:
    st.markdown(f"Buy **{label}** for **€{cost}**?")
    st.caption("Recorded immediately and deducted from your budget.")
    c1, c2 = st.columns(2)
    if c1.button("Confirm", type="primary", use_container_width=True):
        try:
            _commit_purchase(player, pt)
            st.toast(f"{label} purchased!", icon="✅")
        except Exception as e:
            st.error(f"Purchase failed: {e}")
            return
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("Cancel Purchase")
def _dlg_cancel(pt: str, label: str) -> None:
    st.warning(f"Cancel your **{label}** purchase?")
    st.caption(
        "This removes the purchase and restores your budget. "
        "Any picks you've entered will remain saved in case you re-buy."
    )
    c1, c2 = st.columns(2)
    if c1.button("Yes, cancel it", type="primary", use_container_width=True):
        try:
            _cancel_purchase(player, pt)
            st.toast(f"{label} cancelled.", icon="↩️")
        except Exception as e:
            st.error(f"Cancel failed: {e}")
            return
        st.rerun()
    if c2.button("Keep it", use_container_width=True):
        st.rerun()


@st.dialog("Prediction Pack")
def _dlg_prediction_pack(cost: int) -> None:
    st.markdown(f"**Prediction Pack — €{cost}**")
    st.caption("You can enter your picks now, or buy first and fill them in later before the deadline.")

    def _ev(col: str) -> str:
        v = player_row.get(col, "")
        return str(v) if v and str(v) not in ("", "nan") else ""

    opts_all = [""] + all_teams
    opts_t34 = [""] + t3_t4_teams
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

    picks = {
        "WorldCupWinner": wcw, "RunnerUp": ru, "BronzeMedal": bm,
        "GoldenBoot": gb, "DarkHorse": dh, "FirstKnockedOut": fko,
    }
    st.divider()
    ca, cb, cc = st.columns(3)
    if ca.button("Buy & Save Picks", type="primary", use_container_width=True):
        try:
            _commit_purchase(player, "PredictionPack")
            _save_picks(player, picks)
            st.toast("Prediction Pack purchased with picks saved!", icon="✅")
        except Exception as e:
            st.error(f"Purchase failed: {e}")
            return
        st.rerun()
    if cb.button("Buy, fill picks later", use_container_width=True):
        try:
            _commit_purchase(player, "PredictionPack")
            st.toast("Prediction Pack purchased! Fill your picks any time before the deadline.", icon="✅")
        except Exception as e:
            st.error(f"Purchase failed: {e}")
            return
        st.rerun()
    if cc.button("Close", use_container_width=True):
        st.rerun()


@st.dialog("Resurrection — Pick Your Team")
def _dlg_resurrection(cost: int) -> None:
    st.markdown(f"**Resurrection — €{cost}**")
    st.caption(
        "Pick which of your teams to resurrect. "
        "Admin will draw a surviving same-tier replacement after your purchase. "
        "You can also buy now and choose your team later."
    )
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
    ca, cb, cc = st.columns(3)
    disabled = eliminated_team == "— select —"
    if ca.button("Buy & Submit", type="primary", use_container_width=True, disabled=disabled):
        try:
            _commit_purchase(player, "Resurrection", selection=eliminated_team)
            st.toast("Resurrection purchased!", icon="✅")
        except Exception as e:
            st.error(f"Purchase failed: {e}")
            return
        st.rerun()
    if cb.button("Buy, choose later", use_container_width=True):
        try:
            _commit_purchase(player, "Resurrection", selection="")
            st.toast("Resurrection purchased! Choose your team before the deadline.", icon="✅")
        except Exception as e:
            st.error(f"Purchase failed: {e}")
            return
        st.rerun()
    if cc.button("Close", use_container_width=True):
        st.rerun()


# ── Add-on cards ──────────────────────────────────────────────────────────────
st.markdown("### Add-ons")

for pt, label, description in ADDONS:
    cost       = COSTS.get(pt, 0)
    is_owned   = pt in owned_types
    is_open    = _open(pt)
    can_afford = remaining >= cost

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        if is_owned:
            status_html = '<span style="color:#6EE7B7;font-weight:600">✓ Purchased</span>'
        elif not is_open:
            status_html = '<span style="color:#4B5563;font-style:italic">🔒 Deadline passed</span>'
        elif not can_afford:
            status_html = (
                f'<span style="color:#EF4444;font-weight:600">'
                f'Insufficient budget (need €{cost}, have €{remaining})</span>'
            )
        else:
            status_html = '<span style="color:#D4A017;font-weight:600">Available</span>'

        st.markdown(
            f'<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:8px;'
            f'padding:0.8rem 1rem;margin-bottom:0.5rem">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem;flex-wrap:wrap">'
            f'<span style="font-weight:700;color:#F5F5F5">{label} '
            f'<span style="color:#D4A017">€{cost}</span></span>'
            f'{_dl_badge(pt)}'
            f'</div>'
            f'<div style="color:#9CA3AF;font-size:0.83rem;margin:0.2rem 0 0.35rem">{description}</div>'
            f'{status_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_btn:
        st.write("")
        if is_owned:
            if is_open:
                if st.button("Cancel", key=f"cancel_{pt}", use_container_width=True):
                    _dlg_cancel(pt, label)
            else:
                st.button("Owned 🔒", key=f"btn_{pt}", disabled=True, use_container_width=True)
        elif not is_open:
            st.button("Closed", key=f"btn_{pt}", disabled=True, use_container_width=True)
        elif not can_afford:
            st.button(f"€{cost}", key=f"btn_{pt}", disabled=True, use_container_width=True)
        else:
            if st.button(f"Buy  €{cost}", key=f"btn_{pt}", type="primary",
                         use_container_width=True):
                if pt == "PredictionPack":
                    _dlg_prediction_pack(cost)
                elif pt == "Resurrection":
                    _dlg_resurrection(cost)
                else:
                    _dlg_simple(pt, label, cost)


# ── Prediction picks editor ───────────────────────────────────────────────────
if "PredictionPack" in owned_types:
    st.divider()
    picks_locked = not _open("PredictionPack")
    heading = "🔮 Prediction Picks" + (" 🔒" if picks_locked else "")
    with st.expander(heading, expanded=True):
        if picks_locked:
            st.caption("🔒 Deadline passed — picks are locked in.")
        else:
            st.caption(f"Edit your picks any time before **{_fmt_dl('PredictionPack')}**.")

        def _ev(col: str) -> str:
            v = player_row.get(col, "")
            return str(v) if v and str(v) not in ("", "nan") else ""

        opts_all = [""] + all_teams
        opts_t34 = [""] + t3_t4_teams
        c1, c2 = st.columns(2)
        with c1:
            cur = _ev("WorldCupWinner")
            wcw = st.selectbox("World Cup Winner", opts_all,
                               index=opts_all.index(cur) if cur in opts_all else 0,
                               disabled=picks_locked, key="edit_wcw")
            cur = _ev("BronzeMedal")
            bm  = st.selectbox("Bronze Medal", opts_all,
                               index=opts_all.index(cur) if cur in opts_all else 0,
                               disabled=picks_locked, key="edit_bm")
            gb  = st.text_input("Golden Boot (player name)", value=_ev("GoldenBoot"),
                                placeholder="e.g. Mbappé", disabled=picks_locked, key="edit_gb")
        with c2:
            cur = _ev("RunnerUp")
            ru  = st.selectbox("Runner-Up", opts_all,
                               index=opts_all.index(cur) if cur in opts_all else 0,
                               disabled=picks_locked, key="edit_ru")
            cur = _ev("DarkHorse")
            dh  = st.selectbox("Dark Horse (Tier 3/4, not your team)", opts_t34,
                               index=opts_t34.index(cur) if cur in opts_t34 else 0,
                               disabled=picks_locked, key="edit_dh")
            cur = _ev("FirstKnockedOut")
            fko = st.selectbox("First Knocked Out", opts_all,
                               index=opts_all.index(cur) if cur in opts_all else 0,
                               disabled=picks_locked, key="edit_fko")

        if not picks_locked:
            if st.button("Save Picks", type="primary", key="save_picks_btn"):
                try:
                    _save_picks(player, {
                        "WorldCupWinner": wcw, "RunnerUp": ru, "BronzeMedal": bm,
                        "GoldenBoot": gb, "DarkHorse": dh, "FirstKnockedOut": fko,
                    })
                    st.toast("Picks saved!", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")


# ── Resurrection team selector ────────────────────────────────────────────────
if "Resurrection" in owned_types and _open("Resurrection"):
    with st.expander(
        "⚡ Resurrection — " + (f"Team: {res_selection}" if res_selection else "Choose your team"),
        expanded=not res_selection,
    ):
        st.caption(f"Choose before **{_fmt_dl('Resurrection')}**.")
        if player_teams:
            opts_r = ["— select —"] + player_teams
            cur_r  = res_selection if res_selection in player_teams else "— select —"
            sel    = st.selectbox("Team to resurrect", opts_r,
                                  index=opts_r.index(cur_r), key="res_sel_edit")
            if st.button("Save Selection", key="save_res_sel",
                         disabled=sel == "— select —", type="primary"):
                try:
                    _save_resurrection_selection(player, sel)
                    st.toast("Selection saved!", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")
        else:
            st.warning("No teams allocated yet.")


# ── Captain picks ─────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Captain Picks")
st.caption(
    "Free — no purchase required. Your captain earns **1.5× their points**. "
    "Pre-Tournament Captain covers the whole tournament; Knockout Captain covers R32 onward only."
)

cap1, cap2 = st.columns(2)

# Pre-Tournament Captain
with cap1:
    ptc_open    = _open("PreTournamentCaptain")
    current_ptc = str(player_row.get("PreTournamentCaptain", "") or "")
    st.markdown(
        f'<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:8px;'
        f'padding:0.8rem 1rem;margin-bottom:0.5rem">'
        f'<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.3rem">'
        f'<span style="font-weight:700;color:#D4A017">Pre-Tournament Captain</span>'
        f'{_dl_badge("PreTournamentCaptain")}</div>'
        f'<div style="color:#9CA3AF;font-size:0.83rem">'
        f'1.5× all points for the entire tournament (group + knockout stages).</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if player_teams:
        opts_ptc  = ["— select —"] + player_teams
        cur_idx   = opts_ptc.index(current_ptc) if current_ptc in opts_ptc else 0
        ptc_pick  = st.selectbox("Pre-Tournament Captain", opts_ptc, index=cur_idx,
                                  key="ptc_pick", label_visibility="collapsed",
                                  disabled=not ptc_open)
        if ptc_open:
            if st.button("Save Pre-Tournament Captain", key="save_ptc",
                         disabled=ptc_pick == "— select —", type="primary"):
                try:
                    _save_picks(player, {"PreTournamentCaptain": ptc_pick})
                    st.toast("Pre-Tournament Captain saved!", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")
        elif current_ptc:
            st.success(f"Locked in: **{current_ptc}**")
        else:
            st.error("Deadline passed — no pre-tournament captain was set.")
    else:
        st.caption("Teams not yet allocated.")

# Knockout Captain
with cap2:
    koc_open    = _open("KnockoutCaptain")
    current_koc = str(player_row.get("KnockoutCaptain", "") or "")
    current_ptc = str(player_row.get("PreTournamentCaptain", "") or "")
    st.markdown(
        f'<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:8px;'
        f'padding:0.8rem 1rem;margin-bottom:0.5rem">'
        f'<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.3rem">'
        f'<span style="font-weight:700;color:#D4A017">Knockout Captain</span>'
        f'{_dl_badge("KnockoutCaptain")}</div>'
        f'<div style="color:#9CA3AF;font-size:0.83rem">'
        f'1.5× knockout-round points only (R32 onward). Cannot be same as Pre-Tournament Captain.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    eligible_ko = [t for t in player_teams if t != current_ptc]
    if eligible_ko:
        opts_koc = ["— select —"] + eligible_ko
        cur_idx  = opts_koc.index(current_koc) if current_koc in opts_koc else 0
        koc_pick = st.selectbox("Knockout Captain", opts_koc, index=cur_idx,
                                 key="koc_pick", label_visibility="collapsed",
                                 disabled=not koc_open)
        if koc_open:
            if st.button("Save Knockout Captain", key="save_koc",
                         disabled=koc_pick == "— select —", type="primary"):
                try:
                    _save_picks(player, {"KnockoutCaptain": koc_pick})
                    st.toast("Knockout Captain saved!", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")
        elif current_koc:
            st.success(f"Locked in: **{current_koc}**")
        else:
            st.error("Deadline passed — no knockout captain was set.")
    elif player_teams:
        st.caption("Set your Pre-Tournament Captain first.")
    else:
        st.caption("Teams not yet allocated.")

st.divider()
st.caption(
    "Purchases are recorded immediately and deducted from your budget. "
    "Mulligan / Ninth Team / Resurrection draws are run by Oisin once purchased. "
    "BuyIn is handled by Oisin directly and does not appear here."
)
