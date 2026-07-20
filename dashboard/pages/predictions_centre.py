"""Predictions Centre — winner, golden boot, dark horse picks + new categories."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import streamlit as st
import pandas as pd

from dashboard.data import (
    get_predictions_centre_data, is_predictions_locked,
    get_predictions, get_participants, get_purchases,
    get_deadlines, countdown, get_tournament_results, get_match_stats,
)
from dashboard.components.ui import page_header, empty_state


page_header("Predictions Centre", "World Cup Winner · Runner-Up · Golden Boot · Dark Horse · More")

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

    _pick_check_cols = ["WorldCupWinner", "GoldenBoot", "DarkHorse",
                        "RunnerUp", "BronzeMedal", "FirstKnockedOut"]

    def _has_picks(player: str) -> bool:
        if preds_df.empty:
            return False
        row = preds_df[preds_df["Player"] == player]
        if row.empty:
            return False
        r = row.iloc[0]
        return any(str(r.get(col, "")).strip() for col in _pick_check_cols)

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

    # ── Self-service picks form ────────────────────────────────────────────
    _pv = st.session_state.get("viewer")
    if _pv and _pv != "— select —" and _pv in pack_holders:
        st.divider()
        st.subheader(f"📝 {_pv}'s Picks")
        st.caption("Picks are hidden from other players until the prediction lock deadline.")

        from pathlib import Path as _PP
        from src.team_database import load_teams as _ltpv
        from src.event_engine import load_allocation as _lapv
        from src.competition import load_player_status as _lpspv

        _PD = _PP(__file__).resolve().parent.parent.parent / "data"
        _ppdf = pd.read_csv(_PD / "players.csv", dtype=str).fillna("") if (_PD / "players.csv").exists() else pd.DataFrame()

        if not _ppdf.empty:
            _tdf = _ltpv()
            _alloc_pv = _lapv()
            _all_t = sorted(_tdf["Team"].tolist()) if not _tdf.empty else []
            _tm_pv = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in _tdf.iterrows()} if not _tdf.empty else {}
            _owned_pv = sorted(_alloc_pv.assignments.get(_pv, []))
            _low_pv = sorted([t for t, ti in _tm_pv.items() if ti in (3, 4) and t not in _owned_pv])

            _pick_cols_pv = ["PreTournamentCaptain", "KnockoutCaptain",
                              "WorldCupWinner", "RunnerUp", "BronzeMedal",
                              "GoldenBoot", "DarkHorse"]
            for _col in _pick_cols_pv:
                if _col not in _ppdf.columns:
                    _ppdf[_col] = ""

            _rmask = _ppdf["Player"] == _pv
            _rrow  = _ppdf[_rmask].iloc[0] if _rmask.any() else pd.Series(dtype=str)

            def _vp(col):
                v = _rrow.get(col, "") if not _rrow.empty else ""
                return str(v) if pd.notna(v) else ""

            with st.form(f"pred_picks_{_pv}"):
                _pc1, _pc2 = st.columns(2)
                with _pc1:
                    st.markdown("**Pre-Tournament Captain**")
                    _ptc_opts = [""] + _owned_pv
                    _ptc_cur  = _vp("PreTournamentCaptain")
                    _new_ptc  = st.selectbox("One of your 8 teams", _ptc_opts,
                                              index=_ptc_opts.index(_ptc_cur) if _ptc_cur in _ptc_opts else 0,
                                              key="pv_ptc", label_visibility="collapsed")
                with _pc2:
                    st.markdown("**Knockout Captain**")
                    _new_kc = st.text_input("Surviving team you own (can be 9th/Resurrection team)",
                                             value=_vp("KnockoutCaptain"), key="pv_kc",
                                             label_visibility="collapsed", placeholder="e.g. France")

                st.markdown("---")
                _pd1, _pd2, _pd3 = st.columns(3)
                _topts = [""] + _all_t
                with _pd1:
                    st.markdown("**World Cup Winner**")
                    _wcw_cur = _vp("WorldCupWinner")
                    _new_wcw = st.selectbox("Any team", _topts,
                                             index=_topts.index(_wcw_cur) if _wcw_cur in _topts else 0,
                                             key="pv_wcw", label_visibility="collapsed")
                with _pd2:
                    st.markdown("**Runner-Up**")
                    _ru_cur = _vp("RunnerUp")
                    _new_ru = st.selectbox("Any team", _topts,
                                            index=_topts.index(_ru_cur) if _ru_cur in _topts else 0,
                                            key="pv_ru", label_visibility="collapsed")
                with _pd3:
                    st.markdown("**Bronze Medal**")
                    _bm_cur = _vp("BronzeMedal")
                    _new_bm = st.selectbox("Any team", _topts,
                                            index=_topts.index(_bm_cur) if _bm_cur in _topts else 0,
                                            key="pv_bm", label_visibility="collapsed")

                _pd4, _pd5 = st.columns(2)
                with _pd4:
                    st.markdown("**Golden Boot**")
                    _new_gb = st.text_input("Player name", value=_vp("GoldenBoot"),
                                             key="pv_gb", label_visibility="collapsed",
                                             placeholder="e.g. Mbappé")
                with _pd5:
                    st.markdown("**Dark Horse**")
                    st.caption("Tier 3/4 team you don't own")
                    _dh_opts = [""] + _low_pv
                    _dh_cur  = _vp("DarkHorse")
                    _new_dh  = st.selectbox("Tier 3/4, not owned", _dh_opts,
                                             index=_dh_opts.index(_dh_cur) if _dh_cur in _dh_opts else 0,
                                             key="pv_dh", label_visibility="collapsed")

                if st.form_submit_button("Save Picks", type="primary"):
                    try:
                        if _rmask.any():
                            for _col, _val in [
                                ("PreTournamentCaptain", _new_ptc),
                                ("KnockoutCaptain",      _new_kc),
                                ("WorldCupWinner",       _new_wcw),
                                ("RunnerUp",             _new_ru),
                                ("BronzeMedal",          _new_bm),
                                ("GoldenBoot",           _new_gb),
                                ("DarkHorse",            _new_dh),
                            ]:
                                _ppdf.loc[_rmask, _col] = _val
                            _ppdf.to_csv(_PD / "players.csv", index=False)
                            from dashboard.github_sync import push_file as _pfpv
                            try:
                                _pfpv(_PD / "players.csv", "data/players.csv", f"Picks: {_pv}")
                            except Exception as _egh:
                                st.warning(f"⚠️ GitHub sync: {_egh}")
                            st.cache_data.clear()
                            st.success("✓ Picks saved!")
                            st.rerun()
                        else:
                            st.error(f"Player {_pv!r} not found in players.csv.")
                    except Exception as _exf:
                        st.error(f"Error: {_exf}")
    elif _pv and _pv != "— select —" and _pv not in pack_holders:
        st.info("Buy a Prediction Pack in the Shop to submit your picks.")

    st.stop()

# ── Predictions revealed ───────────────────────────────────────────────────
data = get_predictions_centre_data()

if not data or preds_df.empty:
    empty_state("No predictions submitted.")
    st.stop()

# Actual results — used to highlight correct picks in green. Empty strings
# (tournament still in progress) simply never match, so nothing lights up
# until results are actually in.
_tr = get_tournament_results()
_ms_pc = get_match_stats()
_round_reached_map: dict[str, str] = {}
_first_knocked_out = ""
if not _ms_pc.empty:
    _round_reached_map = {
        str(r["Team"]): str(r.get("RoundReached", "") or "") for _, r in _ms_pc.iterrows()
    }
    if "FirstEliminated" in _ms_pc.columns:
        _fko_rows = _ms_pc[pd.to_numeric(_ms_pc["FirstEliminated"], errors="coerce").fillna(0).astype(int) == 1]
        if not _fko_rows.empty:
            _first_knocked_out = str(_fko_rows.iloc[0]["Team"])

_ACTUAL = {
    "world_cup_winner": str(_tr.get("world_cup_winner", "") or ""),
    "runner_up":        str(_tr.get("runner_up", "") or ""),
    "bronze_winner":    str(_tr.get("bronze_winner", "") or ""),
    "golden_boot":      str(_tr.get("golden_boot_winner", "") or ""),
    "first_knocked_out": _first_knocked_out,
}
_DARK_HORSE_QUALIFYING = {"R32", "R16", "QF", "SF", "Final", "Winner"}


def _is_correct(choice: str, actual_key: str = "", dark_horse: bool = False) -> bool:
    if dark_horse:
        return bool(choice) and _round_reached_map.get(choice, "") in _DARK_HORSE_QUALIFYING
    actual = _ACTUAL.get(actual_key, "")
    return bool(actual) and choice == actual


def _pick_card(col, title: str, icon: str, picks: dict, bonus_label: str = "",
                actual_key: str = "", dark_horse: bool = False):
    with col:
        label = f"{icon} {title}"
        if bonus_label:
            label += f" <span style='color:#6EE7B7;font-size:0.75rem;font-weight:400'>({bonus_label})</span>"
        st.markdown(f"<h3 style='margin-bottom:0.5rem'>{label}</h3>", unsafe_allow_html=True)
        if not picks:
            st.markdown(
                '<div class="card"><span style="color:#9CA3AF">No picks submitted</span></div>',
                unsafe_allow_html=True,
            )
            return
        for choice, players in sorted(picks.items(), key=lambda x: -len(x[1])):
            count = len(players)
            players_str = ", ".join(sorted(players))
            correct = _is_correct(choice, actual_key, dark_horse)
            card_style = (
                "border:2px solid #22C55E;background:rgba(34,197,94,0.1)" if correct else ""
            )
            check = (
                ' <span style="color:#22C55E;font-weight:700">✓ Correct</span>' if correct else ""
            )
            st.markdown(
                f'<div class="card" style="margin-bottom:0.4rem;{card_style}">'
                f'<p style="margin:0;font-weight:600;color:#F5F5F5">{choice}{check}</p>'
                f'<p style="margin:0.1rem 0 0;color:#9CA3AF;font-size:0.8rem">'
                f'{players_str} ({count})</p>'
                f'</div>',
                unsafe_allow_html=True,
            )


# Row 1: tournament placings
col1, col2, col3 = st.columns(3)
_pick_card(col1, "World Cup Winner", "🏆", data.get("world_cup_winner", {}), "+30 pts",
           actual_key="world_cup_winner")
_pick_card(col2, "Runner-Up",        "🥈", data.get("runner_up", {}),        "+20 pts",
           actual_key="runner_up")
_pick_card(col3, "Bronze Medal",     "🥉", data.get("bronze_winner", {}),    "+15 pts",
           actual_key="bronze_winner")

st.divider()

# Row 2: individual & special
col4, col5, col6 = st.columns(3)
_pick_card(col4, "Golden Boot",      "👟", data.get("golden_boot", {}),      "+25 pts",
           actual_key="golden_boot")
_pick_card(col5, "Dark Horse",       "🌟", data.get("dark_horse", {}),       "+5→15→30→60→100→150 pts",
           dark_horse=True)
_pick_card(col6, "First Knocked Out","💀", data.get("first_knocked_out", {}), "+20 pts",
           actual_key="first_knocked_out")

st.divider()
st.subheader("All Picks")
st.caption("🟢 Green = correct pick")
if not preds_df.empty:
    _display_cols = [c for c in [
        "Player", "WorldCupWinner", "RunnerUp", "BronzeMedal",
        "GoldenBoot", "DarkHorse", "FirstKnockedOut",
    ] if c in preds_df.columns]
    _disp_df = preds_df[_display_cols].copy()

    _COL_TO_ACTUAL_KEY = {
        "WorldCupWinner": "world_cup_winner", "RunnerUp": "runner_up",
        "BronzeMedal": "bronze_winner", "GoldenBoot": "golden_boot",
        "FirstKnockedOut": "first_knocked_out",
    }

    def _style_pred_row(row):
        styles = []
        for col in row.index:
            if col == "DarkHorse":
                ok = _is_correct(str(row[col]), dark_horse=True)
            elif col in _COL_TO_ACTUAL_KEY:
                ok = _is_correct(str(row[col]), actual_key=_COL_TO_ACTUAL_KEY[col])
            else:
                ok = False
            styles.append(
                "background-color: rgba(34,197,94,0.22); color: #22C55E; font-weight: 700"
                if ok else ""
            )
        return styles

    st.dataframe(
        _disp_df.style.apply(_style_pred_row, axis=1),
        use_container_width=True, hide_index=True,
    )
