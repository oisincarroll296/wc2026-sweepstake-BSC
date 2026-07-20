"""Admin page — password-protected event and draw controls."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import streamlit as st
import pandas as pd

from dashboard.config import ADMIN_PASSWORD
from dashboard.components.ui import page_header, copyable_text

ROOT = Path(__file__).parent.parent.parent
DATA = ROOT / "data"

page_header("Admin", "Tournament management controls")

# ── Auth ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("**Admin Login**")

pwd = st.text_input("Password", type="password", placeholder="Enter admin password")
if not pwd:
    st.info("Enter the admin password to access controls.")
    st.stop()
if pwd != ADMIN_PASSWORD:
    st.error("Incorrect password.")
    st.stop()

st.success("Authenticated", icon="🔓")
st.divider()


from dashboard.github_sync import push_file as _push_gh


def _refresh():
    st.cache_data.clear()


def _push(local, repo_path: str, msg: str) -> None:
    try:
        _push_gh(local, repo_path, msg)
    except Exception as _e:
        st.warning(f"⚠️ GitHub sync: {_e}")


def _save_purchases(df: pd.DataFrame, msg: str = "Update purchases"):
    from src.competition import save_purchases_to_players, load_player_status
    df.to_csv(DATA / "purchases.csv", index=False)
    _push(DATA / "purchases.csv", "data/purchases.csv", msg)
    _pl = load_player_status()
    _pl = save_purchases_to_players(df, _pl)
    _save_statuses(_pl, msg)


def _save_statuses(df: pd.DataFrame, msg: str = "Update players.csv"):
    df.to_csv(DATA / "players.csv", index=False)
    _push(DATA / "players.csv", "data/players.csv", msg)


# ── Tabs ──────────────────────────────────────────────────────────────────
_TAB_NAMES = [
    "Draw Events", "Purchases", "Picks",
    "Locking", "Results Entry", "Special Events",
    "Tournament Results",
    "WhatsApp", "Draw Broadcast", "Deadlines", "Snapshots", "Budgets",
]
# st.tabs() only remembers its selection in the frontend widget itself (older
# Streamlit versions don't even support a key/default for it at all) — a
# mobile browser backgrounding the tab, or a flaky connection reconnecting,
# remounts that widget from scratch and snaps back to the first tab. Use a
# plain st.radio (stateful via key= on every Streamlit version we support)
# tracked in session state + the URL, so admin actions (e.g. saving a
# Results Entry) don't bounce back to Draw Events.
_default_tab = st.session_state.get("admin_active_tab", st.query_params.get("admin_tab", _TAB_NAMES[0]))
if _default_tab not in _TAB_NAMES:
    _default_tab = _TAB_NAMES[0]
if "admin_active_tab" not in st.session_state:
    st.session_state["admin_active_tab"] = _default_tab

selected_tab = st.radio(
    "Section", _TAB_NAMES, key="admin_active_tab",
    horizontal=True, label_visibility="collapsed",
)
st.query_params["admin_tab"] = selected_tab
st.divider()

# ─────────────────────────────────────────────
# Tab 0: Draw Events
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[0]:
    st.subheader("Run Draw Events")

    st.caption(
        "Use this panel to run the Initial Draw, Mulligan, Ninth Team, and Resurrection draws. "
        "Each draw is logged and can be broadcast via the Draw Broadcast tab."
    )

    event_type = st.selectbox("Event Type", [
        "INITIAL_DRAW", "MULLIGAN_DRAW", "GROUP_STAGE_CLOSE",
        "NINTH_TEAM_DRAW", "RESURRECTION_DRAW", "TOURNAMENT_COMPLETE",
    ])
    seed_input = st.text_input("Random Seed (leave blank for random)", placeholder="e.g. 42")
    seed = int(seed_input) if seed_input.strip().isdigit() else None

    if st.button(f"Run {event_type}", type="primary"):
        with st.spinner(f"Running {event_type}…"):
            try:
                from src.event_engine import run_event
                result = run_event(event_type, seed=seed)
                # Push all files that draw events can modify
                for _f, _r in [
                    ("allocation.csv",  "data/allocation.csv"),
                    ("events.csv",      "data/events.csv"),
                    ("audit_log.csv",   "data/audit_log.csv"),
                    ("match_stats.csv", "data/match_stats.csv"),
                    ("players.csv",     "data/players.csv"),
                ]:
                    _fp = DATA / _f
                    if _fp.exists():
                        _push(_fp, _r, f"{event_type}: update {_f}")
                st.success(f"{event_type} executed successfully.")
                if "errors" in result and result["errors"]:
                    st.warning("Some players had errors:")
                    st.json(result["errors"])
                if "results" in result and result["results"]:
                    st.markdown("**Results:**")
                    st.json({k: str(v) for k, v in result["results"].items()})
                if "broadcast" in result:
                    st.markdown("**Broadcast text:**")
                    st.code(result["broadcast"], language=None)
                if "summary" in result:
                    st.info(result["summary"])
                _refresh()
            except Exception as exc:
                st.error(f"Error: {exc}")

    st.divider()

    # ── Delete / undo a historical draw ──────────────────────────────────────
    st.subheader("Delete a Draw")
    st.caption(
        "Remove a draw event and reverse its effects — as if it never happened. "
        "The draw can then be re-run from scratch."
    )

    from src.competition import load_events, load_purchases, load_audit_log

    _ev_df = load_events()
    _UNDOABLE = {"INITIAL_DRAW", "MULLIGAN_DRAW", "NINTH_TEAM_DRAW", "RESURRECTION_DRAW"}
    _executed = (
        _ev_df[
            _ev_df["EventType"].isin(_UNDOABLE) &
            (_ev_df["Status"] == "EXECUTED")
        ]
        if not _ev_df.empty and "Status" in _ev_df.columns
        else pd.DataFrame()
    )

    if _executed.empty:
        st.info("No executed draw events to delete.")
    else:
        _del_opts = [
            f'{row["EventID"]} · {row["EventType"]} '
            f'({str(row.get("ExecutedTime",""))[:16]})'
            for _, row in _executed.iterrows()
        ]
        _del_sel = st.selectbox("Select draw to delete", _del_opts, key="del_event_sel")
        _del_idx = _del_opts.index(_del_sel)
        _del_row = _executed.iloc[_del_idx]
        _del_eid = str(_del_row["EventID"])
        _del_type = str(_del_row["EventType"])

        # Explain what will happen
        _consequences = {
            "INITIAL_DRAW":    "allocation.csv will be cleared — all team assignments removed.",
            "MULLIGAN_DRAW":   "allocation.csv will be cleared — the allocation reverts to nothing (re-run INITIAL_DRAW to restore).",
            "NINTH_TEAM_DRAW": "All NinthTeam purchases will have their drawn team removed (Selection reset to blank).",
            "RESURRECTION_DRAW": "All Resurrection purchases will have their replacement removed (Selection reset to blank).",
        }
        st.warning(f"**What this undoes:** {_consequences.get(_del_type, 'Event removed from log.')}")

        _confirm_key = f"confirm_delete_{_del_eid}"
        _confirmed = st.checkbox("I understand — delete this draw", key=_confirm_key)

        if st.button("Delete Draw", type="primary", disabled=not _confirmed):
            try:
                _purch = load_purchases()
                _audit = load_audit_log()

                # 1. Reverse the draw effects
                if _del_type in ("INITIAL_DRAW", "MULLIGAN_DRAW"):
                    pd.DataFrame(columns=["Player", "Team"]).to_csv(
                        DATA / "allocation.csv", index=False
                    )
                    _push(DATA / "allocation.csv", "data/allocation.csv", "Clear allocation (draw deleted)")
                elif _del_type == "NINTH_TEAM_DRAW":
                    from src.competition import load_player_status as _lps_undo
                    _pl_undo = _lps_undo()
                    if not _pl_undo.empty and "NinthTeamSelection" in _pl_undo.columns:
                        _pl_undo["NinthTeamSelection"] = ""
                        _pl_undo.to_csv(DATA / "players.csv", index=False)
                        _push(DATA / "players.csv", "data/players.csv", "Reset NinthTeam selections")
                elif _del_type == "RESURRECTION_DRAW":
                    from src.competition import load_player_status as _lps_undo
                    _pl_undo = _lps_undo()
                    if not _pl_undo.empty and "ResurrectionSelection" in _pl_undo.columns:
                        _pl_undo["ResurrectionSelection"] = ""
                        _pl_undo.to_csv(DATA / "players.csv", index=False)
                        _push(DATA / "players.csv", "data/players.csv", "Reset Resurrection selections")

                # 2. Remove the event row
                _ev_df_new = _ev_df[_ev_df["EventID"].astype(str) != _del_eid].copy()
                _ev_df_new.to_csv(DATA / "events.csv", index=False)
                _push(DATA / "events.csv", "data/events.csv", f"Delete draw event {_del_eid}")

                # 3. Add audit entry
                from datetime import datetime, timezone, timedelta
                _now = datetime.now(timezone(timedelta(hours=1))).isoformat()
                _new_log = pd.DataFrame([{
                    "Timestamp": _now,
                    "Event":  "DRAW_DELETED",
                    "Player": "ADMIN",
                    "Action": f"DELETE {_del_type} (EventID {_del_eid})",
                    "Result": "Draw reversed and event removed",
                }])
                _audit_new = pd.concat([_audit, _new_log], ignore_index=True)
                _audit_new.to_csv(DATA / "audit_log.csv", index=False)
                _push(DATA / "audit_log.csv", "data/audit_log.csv", "Audit: draw deleted")

                _refresh()
                st.success(
                    f"{_del_type} deleted. "
                    + {
                        "INITIAL_DRAW":      "Allocation cleared — re-run INITIAL_DRAW when ready.",
                        "MULLIGAN_DRAW":     "Allocation cleared — re-run the draw.",
                        "NINTH_TEAM_DRAW":   "Ninth team selections reset — re-run NINTH_TEAM_DRAW.",
                        "RESURRECTION_DRAW": "Resurrection selections reset — re-run RESURRECTION_DRAW.",
                    }.get(_del_type, "")
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Error: {exc}")

# ─────────────────────────────────────────────
# Tab 1: Purchases
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[1]:
    st.subheader("Add Purchase")
    st.caption("Record a payment received via the Shared Revolut Pocket.")

    from src.competition import PRICES as _PRICES
    _price_labels = {k: f"{k}  (€{int(v)})" for k, v in _PRICES.items()}

    from dashboard.data import get_participants as _gp_adm
    _adm_players = ["—"] + (_gp_adm() or [])
    _adm_player = st.selectbox("Player", _adm_players, key="adm_ap_player")
    _adm_type   = st.selectbox("Type", list(_price_labels.keys()),
                                format_func=lambda k: _price_labels[k], key="adm_ap_type")
    _adm_ref    = st.text_input("Payment Reference (optional)",
                                 placeholder="e.g. Oisin - BUY IN", key="adm_ap_ref")

    _adm_sel = ""
    if _adm_type == "Resurrection" and _adm_player and _adm_player != "—":
        from src.competition import load_purchases as _lp_adm
        from src.event_engine import resurrection_candidates as _rc_adm
        from dashboard.data import (get_assignments as _ga_adm, get_match_stats as _gms_adm,
                                     get_tier_map as _gtm_adm)
        _assign_adm = _ga_adm()
        _ms_adm     = _gms_adm()
        _tm_adm     = _gtm_adm()
        _pr_adm     = _lp_adm()
        _pteams_adm = _assign_adm.get(_adm_player, [])
        _rounds_adm: dict[str, str] = {}
        if not _ms_adm.empty:
            for _, _sr_adm in _ms_adm.iterrows():
                _rounds_adm[str(_sr_adm["Team"])] = str(_sr_adm.get("RoundReached", "") or "").strip()
        _gs_adm = any(v not in ("", "GroupStage") for v in _rounds_adm.values())
        if not _gs_adm:
            st.info("Group stage not yet concluded.")
        else:
            _ko_adm = [t for t in _pteams_adm if _rounds_adm.get(t, "") in ("", "GroupStage")]
            if not _ko_adm:
                st.info(f"No group-stage knockouts for {_adm_player}.")
            else:
                _elim_adm = st.selectbox("Eliminated team to replace", _ko_adm, key="adm_ap_elim")
                _cands_adm = _rc_adm(_adm_player, _elim_adm, _assign_adm, _ms_adm, _pr_adm, _tm_adm)
                if not _cands_adm:
                    st.info("No valid same-tier replacements available.")
                else:
                    _repl_adm = st.selectbox("Replacement team", _cands_adm, key="adm_ap_repl")
                    _adm_sel = f"{_elim_adm}->{_repl_adm}"

    if st.button("Add Purchase", type="primary", key="adm_ap_submit"):
        if not _adm_player or _adm_player == "—":
            st.error("Select a player.")
        elif _adm_type == "Resurrection" and not _adm_sel:
            st.error("Complete the Resurrection team selections first.")
        else:
            try:
                from src.competition import add_purchase, load_purchases, load_player_status
                from src.event_engine import process_pending_purchases

                p = load_purchases()
                s = load_player_status()
                p = add_purchase(_adm_player, _adm_type, _adm_ref, p, selection=_adm_sel)

                up, us, _msgs = process_pending_purchases(p, s)
                _save_purchases(up)
                _save_statuses(us)

                cost = _PRICES.get(_adm_type, 0)
                st.success(f"✓ {_adm_type} added for {_adm_player}  (€{int(cost)})")
                _refresh()
                st.rerun()
            except Exception as exc:
                st.error(f"Error: {exc}")

    st.divider()

    # Current purchase log
    st.subheader("Purchase Log")
    from src.competition import load_purchases
    p = load_purchases()
    if p.empty:
        st.caption("No purchases recorded yet.")
    else:
        disp = p.copy()
        disp.insert(2, "€", disp["PurchaseType"].map(_PRICES).fillna(0.0).astype(int))
        show = disp[["Player", "PurchaseType", "€", "Selection", "Reference", "Timestamp"]].copy()
        show = show.sort_values("Timestamp", ascending=False)
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Delete Purchase")
    _p_del = load_purchases()
    if _p_del.empty:
        st.caption("No purchases to delete.")
    else:
        _del_p_opts = [
            f"{i}: {row['Player']} — {row['PurchaseType']} ({str(row.get('Timestamp', ''))[:16]})"
            for i, (_, row) in enumerate(_p_del.iterrows())
        ]
        _del_p_sel   = st.selectbox("Select purchase to delete", _del_p_opts, key="del_purch_sel")
        _del_p_idx   = _del_p_opts.index(_del_p_sel)
        _del_p_row   = _p_del.iloc[_del_p_idx]
        _del_p_ok    = st.checkbox("Confirm deletion", key="del_purch_confirm")
        if st.button("Delete Purchase", type="primary", disabled=not _del_p_ok):
            try:
                from src.competition import load_player_status, mark_unpaid
                _p_new = _p_del.drop(_p_del.index[_del_p_idx]).reset_index(drop=True)
                _s_del = load_player_status()
                if _del_p_row["PurchaseType"] == "BuyIn":
                    _s_del = mark_unpaid(str(_del_p_row["Player"]), _s_del)
                    _save_statuses(_s_del)
                _save_purchases(_p_new)
                _refresh()
                st.success(f"Deleted: {_del_p_row['Player']} — {_del_p_row['PurchaseType']}")
                st.rerun()
            except Exception as _del_exc:
                st.error(f"Error: {_del_exc}")

    # ── Team Swaps ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Team Swaps")
    st.caption(
        "Execute a full roster swap between two players — all 8 teams are exchanged. "
        "The initiator (the player who chose the swap) pays €5. "
        "Each set of 8 teams can only be swapped once — first come, first served. Send Oisin a message to lock in."
    )

    from src.competition import (
        load_swaps as _load_swaps, get_swapped_players as _get_swapped_players,
        execute_team_swap as _execute_team_swap, SWAPS_PATH as _SWAPS_PATH,
        load_swap_offsets as _load_swap_offsets, SWAP_OFFSETS_PATH as _SWAP_OFFSETS_PATH,
    )
    from src.event_engine import load_allocation as _la_swap

    _sw_alloc      = _la_swap()
    _sw_all_players = sorted(_sw_alloc.assignments.keys())
    _sw_df         = _load_swaps()
    _sw_already    = _get_swapped_players(_sw_df)
    _sw_eligible   = [p for p in _sw_all_players if p not in _sw_already]

    _sw_init = st.selectbox("Initiator (pays €5)", ["—"] + _sw_eligible, key="sw_init")
    _sw_ctrp = st.selectbox(
        "Counterpart",
        ["—"] + [p for p in _sw_eligible if p != _sw_init],
        key="sw_ctrp",
    )

    if _sw_init != "—" and _sw_ctrp != "—":
        _sw_i_teams = sorted(_sw_alloc.assignments.get(_sw_init, []))
        _sw_c_teams = sorted(_sw_alloc.assignments.get(_sw_ctrp, []))
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            st.markdown(f"**{_sw_init}'s current teams** (→ go to {_sw_ctrp})")
            st.markdown("  \n".join(f"• {t}" for t in _sw_i_teams))
        with _pc2:
            st.markdown(f"**{_sw_ctrp}'s current teams** (→ go to {_sw_init})")
            st.markdown("  \n".join(f"• {t}" for t in _sw_c_teams))

    _sw_confirm = st.checkbox("I've confirmed payment of €5 from the initiator", key="sw_confirm")
    if st.button("Execute Swap", type="primary", key="sw_submit", disabled=not _sw_confirm):
        if _sw_init == "—" or _sw_ctrp == "—":
            st.error("Select both players.")
        elif _sw_init == _sw_ctrp:
            st.error("Players must be different.")
        else:
            try:
                from src.competition import load_audit_log as _lal_sw
                from dashboard.data import get_match_stats as _gms_sw, get_tier_map as _gtm_sw
                _sw_audit      = _lal_sw()
                _sw_offsets    = _load_swap_offsets()
                _sw_new, _sw_offsets_new, _sw_audit_new, _sw_errs = _execute_team_swap(
                    initiator=_sw_init,
                    counterpart=_sw_ctrp,
                    allocation_path=DATA / "allocation.csv",
                    swaps=_sw_df, audit_log=_sw_audit,
                    swap_offsets=_sw_offsets,
                    match_stats=_gms_sw(),
                    tier_map=_gtm_sw(),
                )
                if _sw_errs:
                    for _e in _sw_errs:
                        st.error(_e)
                else:
                    _sw_new.to_csv(_SWAPS_PATH, index=False)
                    _push(_SWAPS_PATH, "data/swaps.csv",
                          f"TeamSwap: {_sw_init} ↔ {_sw_ctrp}")
                    _sw_offsets_new.to_csv(_SWAP_OFFSETS_PATH, index=False)
                    _push(_SWAP_OFFSETS_PATH, "data/swap_offsets.csv",
                          f"SwapOffsets: {_sw_init} ↔ {_sw_ctrp}")
                    _sw_audit_new.to_csv(DATA / "audit_log.csv", index=False)
                    _push(DATA / "audit_log.csv", "data/audit_log.csv", "Audit: team swap")
                    _push(DATA / "allocation.csv", "data/allocation.csv",
                          f"Allocation: {_sw_init} ↔ {_sw_ctrp}")
                    _refresh()
                    st.success(f"✓ Full roster swap complete: {_sw_init} ↔ {_sw_ctrp}")
                    st.rerun()
            except Exception as _sw_exc:
                st.error(f"Error: {_sw_exc}")

    if not _sw_df.empty:
        st.markdown("**Swap history:**")
        st.dataframe(_sw_df, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# Tab 2: Picks (captains + predictions)
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[2]:
    st.subheader("Captain & Prediction Picks")
    st.caption(
        "Enter each player's Pre-Tournament captain, Knockout captain, "
        "World Cup Winner, Golden Boot, and Dark Horse picks. "
        "Changes are saved immediately to players.csv."
    )

    from src.event_engine import load_allocation
    from src.team_database import load_teams as _load_teams

    _players_path = DATA / "players.csv"
    _picks_df = pd.read_csv(_players_path, dtype=str).fillna("") if _players_path.exists() else pd.DataFrame()
    _alloc    = load_allocation()
    _teams_df = _load_teams()

    _tier_map = {str(r["Team"]): int(r.get("Tier", 4)) for _, r in _teams_df.iterrows()} if not _teams_df.empty else {}

    if _picks_df.empty:
        st.warning("players.csv not found or empty.")
    else:
        _pick_cols = [
            "PreTournamentCaptain", "KnockoutCaptain",
            "WorldCupWinner", "RunnerUp", "BronzeMedal",
            "GoldenBoot", "DarkHorse",
        ]
        for col in _pick_cols:
            if col not in _picks_df.columns:
                _picks_df[col] = ""

        _player_sel = st.selectbox(
            "Player",
            _picks_df["Player"].tolist(),
            key="picks_player_sel",
        )

        _row_mask = _picks_df["Player"] == _player_sel
        _row = _picks_df[_row_mask].iloc[0] if _row_mask.any() else {}

        def _v(col):
            v = _row.get(col, "") if isinstance(_row, pd.Series) else ""
            return str(v) if pd.notna(v) else ""

        # Build team options for this player
        _owned = sorted(_alloc.assignments.get(_player_sel, []))
        _all_teams = sorted(_teams_df["Team"].tolist()) if not _teams_df.empty else []
        _low_tier = sorted([t for t, ti in _tier_map.items() if ti in (3, 4) and t not in _owned])

        # captain options: their owned teams + blank
        _cap_opts = [""] + _owned

        with st.form(f"picks_form_{_player_sel}"):
            st.markdown(f"**{_player_sel}** · owned teams: {', '.join(_owned) if _owned else '—'}")
            st.markdown("")

            pc1, pc2 = st.columns(2)
            with pc1:
                st.markdown("**Pre-Tournament Captain**")
                cur_ptc = _v("PreTournamentCaptain")
                ptc_idx = _cap_opts.index(cur_ptc) if cur_ptc in _cap_opts else 0
                new_ptc = st.selectbox("Must be one of their original 8 teams",
                                       _cap_opts, index=ptc_idx, key="ptc",
                                       label_visibility="collapsed")
            with pc2:
                st.markdown("**Knockout Captain**")
                cur_kc = _v("KnockoutCaptain")
                # Knockout captain can be any team (incl. 9th/resurrection — free text safer)
                new_kc = st.text_input("Surviving team they own (can include 9th/resurrection)",
                                       value=cur_kc, key="kc", label_visibility="collapsed",
                                       placeholder="e.g. France")

            st.markdown("---")
            pd1, pd2, pd3 = st.columns(3)
            with pd1:
                st.markdown("**World Cup Winner**")
                cur_wcw = _v("WorldCupWinner")
                wcw_idx = ([""] + _all_teams).index(cur_wcw) if cur_wcw in ([""] + _all_teams) else 0
                new_wcw = st.selectbox("Any team", [""] + _all_teams, index=wcw_idx,
                                       key="wcw", label_visibility="collapsed")
            with pd2:
                st.markdown("**Runner-Up**")
                cur_ru = _v("RunnerUp")
                ru_idx = ([""] + _all_teams).index(cur_ru) if cur_ru in ([""] + _all_teams) else 0
                new_ru = st.selectbox("Any team", [""] + _all_teams, index=ru_idx,
                                      key="ru", label_visibility="collapsed")
            with pd3:
                st.markdown("**Bronze Medal**")
                cur_bm = _v("BronzeMedal")
                bm_idx = ([""] + _all_teams).index(cur_bm) if cur_bm in ([""] + _all_teams) else 0
                new_bm = st.selectbox("Any team", [""] + _all_teams, index=bm_idx,
                                      key="bm", label_visibility="collapsed")

            pd4, pd5 = st.columns(2)
            with pd4:
                st.markdown("**Golden Boot**")
                new_gb = st.text_input("Player name (free text)",
                                       value=_v("GoldenBoot"), key="gb",
                                       label_visibility="collapsed",
                                       placeholder="e.g. Mbappé")
            with pd5:
                st.markdown("**Dark Horse**")
                st.caption("Tier 3/4 team they don't own")
                cur_dh = _v("DarkHorse")
                dh_idx = ([""] + _low_tier).index(cur_dh) if cur_dh in ([""] + _low_tier) else 0
                new_dh = st.selectbox("Tier 3 or 4, not already owned",
                                      [""] + _low_tier, index=dh_idx,
                                      key="dh", label_visibility="collapsed")

            if st.form_submit_button("Save picks", type="primary"):
                # Validate same-captain rule
                if new_ptc and new_kc and new_ptc == new_kc:
                    st.error("Pre-Tournament and Knockout captains cannot be the same team.")
                else:
                    _picks_df.loc[_row_mask, "PreTournamentCaptain"] = new_ptc
                    _picks_df.loc[_row_mask, "KnockoutCaptain"]      = new_kc
                    _picks_df.loc[_row_mask, "WorldCupWinner"]       = new_wcw
                    _picks_df.loc[_row_mask, "RunnerUp"]             = new_ru
                    _picks_df.loc[_row_mask, "BronzeMedal"]          = new_bm
                    _picks_df.loc[_row_mask, "GoldenBoot"]           = new_gb
                    _picks_df.loc[_row_mask, "DarkHorse"]            = new_dh
                    _picks_df.to_csv(_players_path, index=False)
                    _push(_players_path, "data/players.csv", f"Picks saved for {_player_sel}")
                    st.success(f"Picks saved for {_player_sel}.")
                    _refresh()

        st.divider()
        st.markdown("**All current picks**")
        _show_picks = _picks_df[["Player"] + _pick_cols].copy()
        st.dataframe(_show_picks, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# Tab 3: Locking
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[3]:
    st.subheader("Lock Controls")
    st.caption("Locks are time-based — they trigger automatically when the deadline passes. Use the Deadlines tab to adjust timing. The buttons below force an immediate lock.")

    from dashboard.data import is_predictions_locked, is_buyin_locked, save_deadlines, get_deadlines
    pred_locked  = is_predictions_locked()
    buyin_locked = is_buyin_locked()

    col_status_a, col_status_b = st.columns(2)
    with col_status_a:
        if pred_locked:
            st.success("Predictions: LOCKED")
        else:
            st.warning("Predictions: Open")
    with col_status_b:
        if buyin_locked:
            st.success("Buy-ins: LOCKED")
        else:
            st.warning("Buy-ins: Open")

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        if not pred_locked:
            if st.button("Lock Predictions Now", type="primary"):
                try:
                    from src.competition import load_events, load_audit_log, load_predictions
                    from src.event_engine import lock_predictions
                    from datetime import datetime, timezone, timedelta
                    now_iso = datetime.now(timezone(timedelta(hours=1))).isoformat()
                    ev, log = lock_predictions(load_events(), load_audit_log())
                    ev.to_csv(DATA / "events.csv", index=False)
                    log.to_csv(DATA / "audit_log.csv", index=False)
                    _push(DATA / "events.csv", "data/events.csv", "Lock predictions")
                    _push(DATA / "audit_log.csv", "data/audit_log.csv", "Audit: predictions locked")
                    dl = get_deadlines()
                    dl["prediction_lock"] = now_iso
                    save_deadlines(dl)
                    preds = load_predictions()
                    n = len(preds) if not preds.empty else 0
                    st.success(f"Predictions locked. {n} player prediction(s) now public.")
                    _refresh()
                    st.rerun()
                except Exception as exc:
                    st.error(f"{exc}")
        else:
            st.info("Predictions are locked. To unlock, update the prediction_lock deadline in the Deadlines tab.")

    with col_b:
        if not buyin_locked:
            if st.button("Lock Buy-Ins Now", type="primary"):
                try:
                    from src.competition import load_events, load_audit_log, load_player_status
                    from src.event_engine import lock_buyins
                    from datetime import datetime, timezone, timedelta
                    now_iso = datetime.now(timezone(timedelta(hours=1))).isoformat()
                    s, ev, log = lock_buyins(load_player_status(), load_events(), load_audit_log())
                    ev.to_csv(DATA / "events.csv", index=False)
                    log.to_csv(DATA / "audit_log.csv", index=False)
                    _push(DATA / "events.csv", "data/events.csv", "Lock buy-ins")
                    _push(DATA / "audit_log.csv", "data/audit_log.csv", "Audit: buy-ins locked")
                    dl = get_deadlines()
                    dl["buy_in_deadline"] = now_iso
                    save_deadlines(dl)
                    paid = s[s["Status"] == "PAID"] if not s.empty else pd.DataFrame()
                    unpaid = s[s["Status"] != "PAID"] if not s.empty else pd.DataFrame()
                    st.success(f"Buy-ins locked. {len(paid)} paid / {len(unpaid)} unpaid.")
                    if not unpaid.empty:
                        st.warning("Unpaid players (excluded from prizes): " +
                                   ", ".join(unpaid["Player"].tolist()))
                    _refresh()
                    st.rerun()
                except Exception as exc:
                    st.error(f"{exc}")
        else:
            st.info("Buy-ins are locked. To unlock, update the buy_in_deadline in the Deadlines tab.")

# ─────────────────────────────────────────────
# Tab 4: Results Entry
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[4]:
    from datetime import date as _date, timedelta as _td
    from dashboard.data import (
        get_fixtures, get_match_results, save_match_result_and_recalculate,
        get_teams,
    )
    from src.scoring_engine import load_match_stats

    # ── Group Stage Elimination ────────────────────────────────────────────────
    with st.expander("🚫 Mark Group Stage Eliminations", expanded=True):
        st.caption(
            "Select teams that have been eliminated from the group stage. "
            "Sets RoundReached = 'GroupStage' without touching any other stats."
        )
        _gs_ms = load_match_stats()
        _gs_teams_df = get_teams()
        _gs_all_teams = sorted(_gs_teams_df["Team"].tolist()) if not _gs_teams_df.empty else []

        # Determine current status for each team
        _gs_round_map: dict[str, str] = {}
        if not _gs_ms.empty and "RoundReached" in _gs_ms.columns:
            for _, _r in _gs_ms.iterrows():
                _gs_round_map[str(_r["Team"])] = str(_r.get("RoundReached", "") or "").strip()

        _already_elim = [t for t in _gs_all_teams if _gs_round_map.get(t) == "GroupStage"]
        _active_teams = [t for t in _gs_all_teams if _gs_round_map.get(t, "") == ""]

        if _already_elim:
            st.markdown(
                "**Already eliminated:** " +
                "  ".join(f'<span style="color:#EF4444">{t}</span>' for t in _already_elim),
                unsafe_allow_html=True,
            )

        _to_elim = st.multiselect(
            "Select teams to mark as eliminated (group stage)",
            options=_active_teams,
            key="gs_elim_multi",
        )

        _col_elim1, _col_elim2 = st.columns([1, 3])
        with _col_elim1:
            if st.button("Mark Eliminated", type="primary", disabled=not _to_elim):
                try:
                    _gs_ms2 = load_match_stats()
                    for _t in _to_elim:
                        _mask = _gs_ms2["Team"] == _t
                        if _mask.any():
                            _gs_ms2.loc[_mask, "RoundReached"] = "GroupStage"
                        else:
                            # Team row doesn't exist yet — add it
                            _new_row = {"Team": _t, "RoundReached": "GroupStage"}
                            _gs_ms2 = pd.concat([_gs_ms2, pd.DataFrame([_new_row])], ignore_index=True)
                    _gs_ms2.to_csv(DATA / "match_stats.csv", index=False)
                    _push(DATA / "match_stats.csv", "data/match_stats.csv",
                          "Eliminations: " + ", ".join(_to_elim))
                    _refresh()
                    st.success(f"Marked {len(_to_elim)} team(s) as eliminated.")
                    st.rerun()
                except Exception as _ge:
                    st.error(f"Error: {_ge}")

        with _col_elim2:
            if _already_elim:
                _undo = st.selectbox(
                    "Undo elimination",
                    ["— select —"] + _already_elim,
                    key="gs_elim_undo",
                )
                if _undo != "— select —":
                    if st.button(f"Restore {_undo}", key="gs_elim_undo_btn"):
                        try:
                            _gs_ms3 = load_match_stats()
                            _mask3 = _gs_ms3["Team"] == _undo
                            if _mask3.any():
                                _gs_ms3.loc[_mask3, "RoundReached"] = ""
                            _gs_ms3.to_csv(DATA / "match_stats.csv", index=False)
                            _push(DATA / "match_stats.csv", "data/match_stats.csv",
                                  f"Restore: {_undo}")
                            _refresh()
                            st.success(f"Restored {_undo}.")
                            st.rerun()
                        except Exception as _ue:
                            st.error(f"Error: {_ue}")

    st.divider()

    result_mode = st.radio(
        "Entry method",
        ["By Match (recommended)", "Advanced / Special Stats"],
        horizontal=True,
    )

    # ── By Match ──────────────────────────────────────────────────────────────
    if result_mode == "By Match (recommended)":
        st.caption(
            "Select a date, pick a match, enter the score. "
            "Goals and clean sheets are calculated automatically for both teams. "
            "Use **Advanced** for comeback wins, group winners, round reached."
        )

        fixtures_df = get_fixtures()
        results_df  = get_match_results()

        # Build winner_of/loser_of dicts so KO placeholder names resolve to
        # real teams. A QF fixture's home/away text is itself a placeholder
        # like "Winner match 89", and match 89's own fixture text is in turn
        # a placeholder referencing R32 matches — so this must process
        # matches in ascending order and resolve each fixture through the
        # already-built dicts before recording that match's winner/loser,
        # otherwise later rounds show one-level-stale placeholders (e.g.
        # "Winner match 77" instead of the actual R32 winner). loser_of
        # resolves "Runner-up match X", used by the 3rd-place playoff (103),
        # which pits the two semi-final losers against each other.
        _winner_of: dict[int, str] = {}
        _loser_of: dict[int, str] = {}

        def _resolve_placeholder(raw: str) -> str:
            s = str(raw or "").strip()
            seen = set()
            while (s.startswith("Winner match ") or s.startswith("Runner-up match ")) and s not in seen:
                seen.add(s)
                try:
                    mn_ = int(s.split()[-1])
                except ValueError:
                    break
                src = _winner_of if s.startswith("Winner match ") else _loser_of
                s = src.get(mn_, s)
            return s

        if not results_df.empty and not fixtures_df.empty:
            _rr_sorted = results_df.copy()
            _rr_sorted["match_number"] = pd.to_numeric(_rr_sorted["match_number"], errors="coerce")
            _rr_sorted = _rr_sorted.dropna(subset=["match_number"]).sort_values("match_number")
            for _, _rr in _rr_sorted.iterrows():
                _rmn = int(_rr["match_number"])
                if _rmn < 73:
                    continue
                _rf = fixtures_df[fixtures_df["match_number"] == _rmn]
                if _rf.empty:
                    continue
                _rh = _resolve_placeholder(_rf.iloc[0]["home_team"])
                _ra = _resolve_placeholder(_rf.iloc[0]["away_team"])
                _rhg = int(float(_rr.get("home_goals", 0) or 0))
                _rag = int(float(_rr.get("away_goals", 0) or 0))
                _rpw = str(_rr.get("penalty_winner", "") or "").strip()
                if _rpw == "home" or (not _rpw and _rhg > _rag):
                    _winner_of[_rmn] = _rh
                    _loser_of[_rmn]  = _ra
                elif _rpw == "away" or (not _rpw and _rag > _rhg):
                    _winner_of[_rmn] = _ra
                    _loser_of[_rmn]  = _rh

        def _resolve_team(raw: str) -> str:
            return _resolve_placeholder(str(raw or "").strip())

        if fixtures_df.empty:
            st.warning("No fixture data found. Ensure data/fixtures.csv exists.")
        else:
            # Build set of already-entered match numbers
            entered_nums = set()
            if not results_df.empty and "match_number" in results_df.columns:
                entered_nums = set(results_df["match_number"].dropna().astype(int).tolist())

            # Date selector — default to earliest unplayed date or today
            all_dates = sorted(fixtures_df["match_date"].dropna().unique())
            today = _date.today()
            # Pick the first date with unplayed matches on or after today
            default_date = today
            for d in all_dates:
                day_matches = fixtures_df[fixtures_df["match_date"] == d]
                day_nums = set(pd.to_numeric(day_matches["match_number"], errors="coerce").dropna().astype(int))
                if day_nums - entered_nums:
                    default_date = d
                    break

            sel_date = st.date_input(
                "Match date",
                value=default_date,
                min_value=min(all_dates) if all_dates else today,
                max_value=max(all_dates) if all_dates else today + _td(days=60),
            )

            day_df = fixtures_df[fixtures_df["match_date"] == sel_date]

            if day_df.empty:
                st.info("No fixtures on that date.")
            else:
                # Show fixture status cards
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#9CA3AF;margin-bottom:0.3rem">'
                    f'{len(day_df)} matches · '
                    f'<span style="color:#6EE7B7">●</span> entered &nbsp; '
                    f'<span style="color:#6B7280">●</span> pending</div>',
                    unsafe_allow_html=True,
                )

                match_options = []
                for _, m in day_df.iterrows():
                    mn = int(pd.to_numeric(m["match_number"], errors="coerce"))
                    done = mn in entered_nums
                    dot = "🟢" if done else "⚪"

                    # Get existing result if entered
                    res_row = {}
                    if done and not results_df.empty:
                        rr = results_df[results_df["match_number"] == mn]
                        if not rr.empty:
                            res_row = rr.iloc[0].to_dict()

                    score_str = ""
                    if res_row:
                        hg = int(float(res_row.get("home_goals", 0) or 0))
                        ag = int(float(res_row.get("away_goals", 0) or 0))
                        et = int(float(res_row.get("extra_time", 0) or 0))
                        pwin = str(res_row.get("penalty_winner", "") or "")
                        score_str = f" **{hg}–{ag}**"
                        if et:
                            score_str += " (AET)"
                        if pwin:
                            pw_label = _resolve_team(m["home_team"]) if pwin == "home" else _resolve_team(m["away_team"])
                            score_str += f" · {pw_label} win on pens"

                    label = f"{dot} M{mn}: {_resolve_team(m['home_team'])} v {_resolve_team(m['away_team'])}"
                    match_options.append((label + score_str, mn, m))

                sel_label = st.selectbox(
                    "Select match to enter / edit",
                    [opt[0] for opt in match_options],
                )
                sel_idx  = [opt[0] for opt in match_options].index(sel_label)
                sel_mn   = match_options[sel_idx][1]
                sel_fix  = match_options[sel_idx][2]

                home_team = _resolve_team(sel_fix["home_team"])
                away_team = _resolve_team(sel_fix["away_team"])
                is_group  = bool(str(sel_fix.get("group", "")).strip())

                # Pre-fill if already entered
                prev = {}
                if sel_mn in entered_nums and not results_df.empty:
                    pr = results_df[results_df["match_number"] == sel_mn]
                    if not pr.empty:
                        prev = pr.iloc[0].to_dict()

                def _pi(key, default=0):
                    try: return int(float(prev.get(key, default) or default))
                    except Exception: return default

                st.divider()
                st.markdown(
                    f'<div style="font-size:1rem;font-weight:700;color:#F5F5F5;margin-bottom:0.5rem">'
                    f'Match {sel_mn} · Group {sel_fix.get("group","")} · {sel_fix.get("venue","")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                with st.form("match_result_form"):
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        st.markdown(f"**{home_team}** (Home)")
                        h_goals = st.number_input("Goals", 0, 20, _pi("home_goals"), key="hg")
                        cb_home = st.checkbox("Comeback win", value=bool(_pi("comeback_home")), key="cbh")
                    with fc2:
                        st.markdown(f"**{away_team}** (Away)")
                        a_goals = st.number_input("Goals", 0, 20, _pi("away_goals"), key="ag")
                        cb_away = st.checkbox("Comeback win", value=bool(_pi("comeback_away")), key="cba")

                    et_played = st.checkbox(
                        "Went to extra time / penalties",
                        value=bool(_pi("extra_time")),
                        disabled=is_group,
                        help="Group stage matches cannot go to extra time",
                    )
                    prev_pwin = str(prev.get("penalty_winner", "") or "")
                    pwin_opts = ["none", "home", "away"]
                    pwin_idx  = pwin_opts.index(prev_pwin) if prev_pwin in pwin_opts else 0
                    pen_winner = ""
                    if et_played and not is_group:
                        pen_winner_sel = st.radio(
                            "Penalty winner (if applicable)",
                            ["None", home_team, away_team],
                            index=pwin_idx,
                            horizontal=True,
                        )
                        pen_winner = ("home" if pen_winner_sel == home_team
                                      else "away" if pen_winner_sel == away_team
                                      else "")

                    st.divider()
                    st.markdown("**Special Events**")
                    se1, se2 = st.columns(2)
                    with se1:
                        st.caption(f"{home_team}")
                        h_ht   = st.number_input("Hat Tricks 🎩",     0, 5,  _pi("home_hat_tricks"),      key="h_ht",  help="+10 pts each")
                        h_rc   = st.number_input("Red Cards 🟥",      0, 10, _pi("home_red_cards"),       key="h_rc",  help="−5 pts each")
                        h_so   = st.number_input("Shirt Off 👕",      0, 5,  _pi("home_shirt_off"),       key="h_so",  help="+25 pts each")
                        h_gk   = st.number_input("GK Goal 🧤",        0, 3,  _pi("home_gk_goals"),        key="h_gk",  help="+75 pts each")
                    with se2:
                        st.caption(f"{away_team}")
                        a_ht   = st.number_input("Hat Tricks 🎩",     0, 5,  _pi("away_hat_tricks"),      key="a_ht",  help="+10 pts each")
                        a_rc   = st.number_input("Red Cards 🟥",      0, 10, _pi("away_red_cards"),       key="a_rc",  help="−5 pts each")
                        a_so   = st.number_input("Shirt Off 👕",      0, 5,  _pi("away_shirt_off"),       key="a_so",  help="+25 pts each")
                        a_gk   = st.number_input("GK Goal 🧤",        0, 3,  _pi("away_gk_goals"),        key="a_gk",  help="+75 pts each")

                    submitted_m = st.form_submit_button("Save Result", type="primary")
                    if submitted_m:
                        try:
                            save_match_result_and_recalculate(
                                match_number  = sel_mn,
                                home_goals    = h_goals,
                                away_goals    = a_goals,
                                extra_time    = et_played and not is_group,
                                penalty_winner= pen_winner,
                                comeback_home = cb_home,
                                comeback_away = cb_away,
                                home_hat_tricks       = h_ht,
                                away_hat_tricks       = a_ht,
                                home_red_cards        = h_rc,
                                away_red_cards        = a_rc,
                                home_shirt_off        = h_so,
                                away_shirt_off        = a_so,
                                home_gk_goals         = h_gk,
                                away_gk_goals         = a_gk,
                            )
                            st.success(
                                f"Saved: {home_team} {h_goals}–{a_goals} {away_team}. "
                                "Stats recalculated."
                            )
                            # Who Benefits panel
                            from dashboard.data import get_match_impact
                            _impact = get_match_impact(sel_mn)
                            if _impact:
                                st.markdown("**⚡ Who Benefits from this result:**")
                                _imp_rows = []
                                for _r in _impact:
                                    _imp_rows.append({
                                        "Player": _r["Player"],
                                        "Team":   _r["Team"],
                                        "Goals":  _r["Goals"],
                                        "CS":     "✓" if _r["CS"] else "",
                                        "Pts":    f"+{_r['Pts']:.0f}",
                                    })
                                import pandas as _pd2
                                st.dataframe(_pd2.DataFrame(_imp_rows), use_container_width=True, hide_index=True)
                            _refresh()
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed: {exc}")

    # ── Advanced / Special Stats ───────────────────────────────────────────────
    else:
        st.caption(
            "Use this for: Group Winners, Round Reached, and any manual corrections. "
            "Goals and clean sheets are normally auto-calculated from match results above."
        )

        teams_df  = get_teams()
        team_list = sorted(teams_df["Team"].tolist()) if not teams_df.empty else []

        with st.form("results_form_advanced"):
            res_team = st.selectbox("Team", team_list)

            ms = load_match_stats()
            existing = {}
            if not ms.empty and res_team:
                row = ms[ms["Team"] == res_team]
                if not row.empty:
                    existing = row.iloc[0].to_dict()

            def _ev(col, default=0):
                v = existing.get(col, default)
                try: return int(float(v)) if v != "" else default
                except Exception: return default

            def _es(col):
                v = existing.get(col, "")
                return str(v) if v and str(v) != "nan" else ""

            st.markdown("**Group Stage**")
            ca1, ca2, ca3, ca4, ca5 = st.columns(5)
            with ca1: g_goals  = st.number_input("Goals",      0, 50, _ev("GroupGoals"),       key="adv_g_goals")
            with ca2: g_cs     = st.number_input("Cl. Sheets", 0, 10, _ev("GroupCleanSheets"), key="adv_g_cs")
            with ca3: g_pw     = st.number_input("Pen. Wins",  0,  5, _ev("GroupPenaltyWins"), key="adv_g_pw")
            with ca4: g_cw     = st.number_input("CB Wins",    0,  5, _ev("GroupComebackWins"),key="adv_g_cw")
            with ca5: g_winner = st.checkbox("Group Winner", value=bool(_ev("GroupWinner")))

            st.markdown("**Knockout**")
            cb1, cb2, cb3, cb4 = st.columns(4)
            with cb1: ko_goals = st.number_input("Goals",      0, 50, _ev("KnockoutGoals"),       key="adv_ko_goals")
            with cb2: ko_cs    = st.number_input("Cl. Sheets", 0, 10, _ev("KnockoutCleanSheets"), key="adv_ko_cs")
            with cb3: ko_pw    = st.number_input("Pen. Wins",  0,  5, _ev("KnockoutPenaltyWins"), key="adv_ko_pw")
            with cb4: ko_cw    = st.number_input("CB Wins",    0,  5, _ev("KnockoutComebackWins"),key="adv_ko_cw")
            rounds  = ["", "GroupStage", "R32", "R16", "QF", "SF", "Final", "Winner"]
            cur_rnd = _es("RoundReached")
            rnd     = st.selectbox("Round Reached", rounds,
                                   index=rounds.index(cur_rnd) if cur_rnd in rounds else 0)

            if st.form_submit_button("Save", type="primary") and res_team:
                try:
                    from src.event_engine import update_results
                    ms = update_results(res_team, {
                        "GroupGoals": g_goals, "GroupCleanSheets": g_cs,
                        "GroupPenaltyWins": g_pw, "GroupComebackWins": g_cw,
                        "GroupWinner": int(g_winner),
                        "KnockoutGoals": ko_goals, "KnockoutCleanSheets": ko_cs,
                        "KnockoutPenaltyWins": ko_pw, "KnockoutComebackWins": ko_cw,
                        "RoundReached": rnd,
                    }, ms)
                    ms.to_csv(DATA / "match_stats.csv", index=False)
                    _push(DATA / "match_stats.csv", "data/match_stats.csv", f"Results: {res_team}")
                    st.success(f"Saved {res_team}.")
                    _refresh()
                except Exception as exc:
                    st.error(f"{exc}")

# ─────────────────────────────────────────────
# Tab 5: Special Events
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[5]:
    st.subheader("Special Events")
    st.caption(
        "Log match events that are awarded manually: hat tricks, shirt-removal celebrations, "
        "goalkeeper goals, red cards, and first-team-eliminated. "
        "These are preserved when match stats are recalculated."
    )

    from src.scoring_engine import load_match_stats as _lms
    from src.team_database import load_teams as _lts

    _se_teams_df = _lts()
    _se_team_list = sorted(_se_teams_df["Team"].tolist()) if not _se_teams_df.empty else []

    with st.form("special_events_form"):
        _se_team = st.selectbox("Team", _se_team_list, key="se_team")

        _se_ms = _lms()
        _se_ex: dict = {}
        if not _se_ms.empty and _se_team:
            _row = _se_ms[_se_ms["Team"] == _se_team]
            if not _row.empty:
                _se_ex = _row.iloc[0].to_dict()

        def _sei(col):
            v = _se_ex.get(col, 0)
            try: return int(float(v)) if str(v) not in ("", "nan") else 0
            except Exception: return 0

        st.markdown("**Group Stage Hat Tricks** (+10 per hat trick)")
        _ht_grp = st.number_input("Count", 0, 20, _sei("GroupHatTricks"), key="se_ht_grp",
                                  help="Any player from this team scored a hat trick in the group stage")

        st.markdown("**Knockout Hat Tricks** (+10 per hat trick)")
        _ht_ko = st.number_input("Count", 0, 10, _sei("KnockoutHatTricks"), key="se_ht_ko",
                                 help="Any player from this team scored a hat trick in the knockout rounds")

        st.markdown("**Shirt Removal Celebrations** (+25 per incident)")
        _shirts = st.number_input("Count", 0, 20, _sei("ShirtRemovals"), key="se_shirts",
                                  help="Player from this team removes shirt to celebrate a goal/win")

        st.markdown("**Goalkeeper Goals** (+75 per goal)")
        _gk = st.number_input("Count", 0, 10, _sei("GKGoals"), key="se_gk",
                               help="Goal scored by a goalkeeper")

        st.markdown("**Red Cards** (−5 per card)")
        _red = st.number_input("Count", 0, 20, _sei("RedCards"), key="se_red",
                               help="Total red cards received by this team across the tournament")

        st.markdown("**First Team Eliminated** (+35 for owners)")
        _first_e = st.checkbox("This team was the first knocked out of the tournament",
                               value=bool(_sei("FirstEliminated")), key="se_first_e")

        if st.form_submit_button("Save Special Events", type="primary") and _se_team:
            try:
                _se_ms2 = _lms()
                _mask = _se_ms2["Team"] == _se_team
                if not _mask.any():
                    st.error(f"Team {_se_team!r} not found in match_stats.csv")
                else:
                    # If marking first eliminated, clear any previous flag first
                    if _first_e and "FirstEliminated" in _se_ms2.columns:
                        _se_ms2["FirstEliminated"] = 0
                    for _col, _val in [
                        ("GroupHatTricks", _ht_grp),
                        ("KnockoutHatTricks", _ht_ko),
                        ("ShirtRemovals", _shirts),
                        ("GKGoals", _gk),
                        ("RedCards", _red),
                        ("FirstEliminated", int(_first_e)),
                    ]:
                        if _col not in _se_ms2.columns:
                            _se_ms2[_col] = 0
                        _se_ms2.loc[_mask, _col] = _val
                    _se_ms2.to_csv(DATA / "match_stats.csv", index=False)
                    _push(DATA / "match_stats.csv", "data/match_stats.csv", f"Special events: {_se_team}")
                    st.success(f"Special events saved for {_se_team}.")
                    _refresh()
            except Exception as exc:
                st.error(f"Error: {exc}")

    st.divider()
    st.markdown("**Current special event totals**")
    _se_cur = _lms()
    _se_cols = ["GroupHatTricks", "KnockoutHatTricks", "ShirtRemovals", "GKGoals", "RedCards", "FirstEliminated"]
    _se_display_cols = [c for c in _se_cols if c in _se_cur.columns]
    if not _se_cur.empty and _se_display_cols:
        _se_show = _se_cur[["Team"] + _se_display_cols].copy()
        _se_show = _se_show[(_se_show[_se_display_cols] != 0).any(axis=1)]
        if _se_show.empty:
            st.caption("No special events logged yet.")
        else:
            st.dataframe(_se_show, use_container_width=True, hide_index=True)
    else:
        st.caption("No special events logged yet.")


# ─────────────────────────────────────────────
# Tab 6: Tournament Results
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[6]:
    import json as _json
    st.subheader("Tournament Results")
    st.caption(
        "Set the final outcomes used for prediction bonus calculations. "
        "Leave fields blank until the result is known."
    )

    _tr_path = DATA / "tournament_results.json"
    _tr_cur: dict = {}
    if _tr_path.exists():
        try:
            _tr_cur = _json.loads(_tr_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    from src.team_database import load_teams as _lts2
    _tr_teams = sorted(_lts2()["Team"].tolist())

    with st.form("tournament_results_form"):
        _tr_c1, _tr_c2 = st.columns(2)
        with _tr_c1:
            _tr_winner_cur = _tr_cur.get("world_cup_winner", "")
            _tr_winner_idx = ([""] + _tr_teams).index(_tr_winner_cur) if _tr_winner_cur in _tr_teams else 0
            _tr_winner = st.selectbox("World Cup Winner",  [""] + _tr_teams, index=_tr_winner_idx, key="tr_w")

            _tr_ru_cur = _tr_cur.get("runner_up", "")
            _tr_ru_idx = ([""] + _tr_teams).index(_tr_ru_cur) if _tr_ru_cur in _tr_teams else 0
            _tr_ru = st.selectbox("Runner-Up (2nd place)", [""] + _tr_teams, index=_tr_ru_idx, key="tr_ru")
        with _tr_c2:
            _tr_bronze_cur = _tr_cur.get("bronze_winner", "")
            _tr_bronze_idx = ([""] + _tr_teams).index(_tr_bronze_cur) if _tr_bronze_cur in _tr_teams else 0
            _tr_bronze = st.selectbox("Bronze Medal (3rd place)", [""] + _tr_teams, index=_tr_bronze_idx, key="tr_bz")

            _tr_gb_cur = _tr_cur.get("golden_boot_winner", "")
            _tr_gb = st.text_input("Golden Boot Winner (player name)",
                                   value=_tr_gb_cur, key="tr_gb",
                                   placeholder="e.g. Mbappé")

        if st.form_submit_button("Save Tournament Results", type="primary"):
            _tr_new = {
                "world_cup_winner":  _tr_winner,
                "runner_up":         _tr_ru,
                "bronze_winner":     _tr_bronze,
                "golden_boot_winner": _tr_gb,
            }
            _tr_path.write_text(_json.dumps(_tr_new, indent=2), encoding="utf-8")
            st.success("Tournament results saved.")
            _refresh()
            st.rerun()


# ─────────────────────────────────────────────
# Tab 7: WhatsApp Update
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[7]:
    st.subheader("Generate WhatsApp Update")
    st.caption("Generates a formatted standings update to paste into your WhatsApp group.")

    if st.button("Generate Update", type="primary"):
        with st.spinner("Generating…"):
            try:
                from src.event_engine import generate_whatsapp_update
                from dashboard.data import (
                    get_prize_leaderboard, get_overall_leaderboard,
                    get_prize_pool, get_events, get_match_stats,
                )
                text = generate_whatsapp_update(
                    get_prize_leaderboard(), get_overall_leaderboard(),
                    get_prize_pool(), get_events(), get_match_stats(),
                )
                copyable_text("WhatsApp Update", text)
            except Exception as exc:
                st.error(f"{exc}")

# ─────────────────────────────────────────────
# Tab 8: Draw Broadcast
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[8]:
    st.subheader("Generate Draw Broadcast")
    st.caption("Generates a formatted draw announcement to paste into your WhatsApp group.")

    bc_type = st.selectbox("Draw Type", [
        "Initial Draw", "Mulligan Draw", "Ninth Team Draw", "Resurrection Draw",
    ])

    if st.button("Generate Broadcast", type="primary"):
        try:
            from src.event_engine import generate_draw_broadcast, load_allocation
            from src.competition import load_purchases

            results: dict[str, str] = {}

            if bc_type == "Initial Draw":
                alloc = load_allocation()
                if alloc.assignments:
                    results = {p: " | ".join(t) for p, t in alloc.assignments.items()}
                else:
                    st.warning(
                        "No draw found. Run INITIAL_DRAW first via the Draw Events tab, "
                        "then come back here to generate the broadcast."
                    )
                    st.stop()
            elif bc_type == "Mulligan Draw":
                alloc = load_allocation()
                if alloc.assignments:
                    results = {pl: " | ".join(t) for pl, t in alloc.assignments.items()}
                else:
                    st.warning("No allocation found. Run the Mulligan Draw event first.")
                    st.stop()
            elif bc_type == "Ninth Team Draw":
                p = load_purchases()
                done = p[(p["PurchaseType"] == "NinthTeam") & (p["Selection"].str.strip() != "")] if not p.empty else p
                if done.empty:
                    st.warning("No Ninth Team draws recorded yet. Run the draw event first.")
                    st.stop()
                results = {str(r["Player"]): str(r["Selection"]) for _, r in done.iterrows()}
            elif bc_type == "Resurrection Draw":
                p = load_purchases()
                done = p[(p["PurchaseType"] == "Resurrection") & p["Selection"].str.contains("->", na=False)] if not p.empty else p
                if done.empty:
                    st.warning("No Resurrection draws recorded yet. Run the draw event first.")
                    st.stop()
                results = {str(r["Player"]): str(r["Selection"]) for _, r in done.iterrows()}

            text = generate_draw_broadcast(bc_type, results)
            copyable_text("Draw Broadcast", text)
        except Exception as exc:
            st.error(f"{exc}")

    st.divider()
    if st.button("Refresh All Scores"):
        _refresh()
        st.success("Cache cleared — scores will reload on next page view.")

# ─────────────────────────────────────────────
# Tab 9: Deadlines
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[9]:
    import json
    from datetime import datetime, timezone, timedelta, date, time as dtime
    from dashboard.data import get_deadlines, save_deadlines, countdown, DEADLINE_LABELS

    _IST = timezone(timedelta(hours=1))  # Irish Summer Time = UTC+1

    st.subheader("Tournament Deadlines")
    st.caption(
        "Set the exact date and time for each deadline. All times are Irish Summer Time. "
        "The countdown shown on the Home page and Predictions Centre is derived from these values."
    )

    deadlines = get_deadlines()

    with st.form("deadlines_form"):
        updated: dict[str, str] = {}

        for key, label in DEADLINE_LABELS.items():
            iso = deadlines.get(key, "")
            try:
                dt = datetime.fromisoformat(iso).astimezone(_IST)
                cur_date = dt.date()
                cur_time = dt.time().replace(second=0, microsecond=0)
            except Exception:
                cur_date = date(2026, 6, 11)
                cur_time = dtime(20, 0)

            cd = countdown(iso) if iso else "—"
            cd_text = f"  ·  **{cd}**" if cd not in ("—", "PASSED") else ("  ·  ~~passed~~" if cd == "PASSED" else "")

            st.markdown(f"**{label}**{cd_text}")
            col_d, col_t = st.columns([2, 1])
            with col_d:
                new_date = st.date_input(f"Date##{key}", value=cur_date, label_visibility="collapsed")
            with col_t:
                new_time = st.time_input(f"Time (IST)##{key}", value=cur_time, label_visibility="collapsed", step=300)

            combined = datetime(
                new_date.year, new_date.month, new_date.day,
                new_time.hour, new_time.minute, 0,
                tzinfo=_IST,
            )
            updated[key] = combined.isoformat()
            st.markdown("")

        if st.form_submit_button("Save All Deadlines", type="primary"):
            save_deadlines(updated)
            _refresh()
            st.success("Deadlines saved.")
            st.rerun()

# ─────────────────────────────────────────────
# Tab 10: Snapshots
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[10]:
    import shutil
    from datetime import datetime as _dt

    SNAPSHOTS_DIR = DATA / "snapshots"
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    st.subheader("💾 Snapshots")
    st.caption(
        "A snapshot copies every file in data/ so you can restore to a known state. "
        "All draw seeds are recorded in events.csv — restoring a pre-draw snapshot "
        "and re-running with the same seed reproduces the identical allocation."
    )

    # ── Take snapshot ────────────────────────────────────────────────────────
    with st.form("snapshot_form"):
        snap_label = st.text_input("Label (optional)", placeholder="e.g. pre_draw, after_r16")
        if st.form_submit_button("📸 Take Snapshot", type="primary"):
            ts = _dt.now().strftime("%Y-%m-%d_%H%M%S")
            name = f"{ts}_{snap_label}" if snap_label.strip() else ts
            dest = SNAPSHOTS_DIR / name
            dest.mkdir(parents=True, exist_ok=True)
            for f in sorted(DATA.glob("*.csv")):
                shutil.copy2(f, dest / f.name)
            for f in sorted(DATA.glob("*.json")):
                shutil.copy2(f, dest / f.name)
            st.success(f"Snapshot saved: **{name}**")
            st.rerun()

    st.divider()

    # ── List + restore ────────────────────────────────────────────────────────
    snaps = sorted(SNAPSHOTS_DIR.iterdir(), reverse=True) if SNAPSHOTS_DIR.exists() else []
    if not snaps:
        st.info("No snapshots yet. Take one above before making any changes.")
    else:
        st.markdown(f"**{len(snaps)} snapshot{'s' if len(snaps) != 1 else ''} available**")
        for snap in snaps:
            files = list(snap.glob("*.csv")) + list(snap.glob("*.json"))
            col_name, col_btn = st.columns([4, 1])
            with col_name:
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#E5E7EB;padding:0.3rem 0">'
                    f'<strong>{snap.name}</strong> '
                    f'<span style="color:#6B7280;font-size:0.75rem">({len(files)} files)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button("Restore", key=f"restore_{snap.name}"):
                    for f in snap.glob("*.csv"):
                        shutil.copy2(f, DATA / f.name)
                    for f in snap.glob("*.json"):
                        shutil.copy2(f, DATA / f.name)
                    _refresh()
                    st.success(f"Restored from **{snap.name}**")
                    st.rerun()

# ─────────────────────────────────────────────
# Tab 11: Budgets
# ─────────────────────────────────────────────
if selected_tab == _TAB_NAMES[11]:
    st.subheader("Player Budgets")
    st.caption(
        "Budget = money each player has contributed to the Revolut pocket. "
        "The prize pool equals the sum of all budgets. "
        "Available balance = Budget minus recorded purchases."
    )

    from src.competition import load_player_status as _lps_b
    from dashboard.data import get_prize_pool as _gpp_b
    _budg_st = _lps_b()

    if _budg_st.empty:
        st.warning("No player data found.")
    else:
        _pool_b = _gpp_b()
        _bc1, _bc2, _bc3, _bc4 = st.columns(4)
        with _bc1:
            st.metric("Prize Pool", f"€{_pool_b['current_pot']:.2f}",
                      help="Sum of all Budget values in players.csv")
        with _bc2:
            st.metric("🥇 1st (50%)", f"€{_pool_b['first_prize']:.2f}")
        with _bc3:
            st.metric("🥈 2nd (30%)", f"€{_pool_b['second_prize']:.2f}")
        with _bc4:
            st.metric("🥉 3rd (20%)", f"€{_pool_b['third_prize']:.2f}")

        st.divider()

        with st.form("budgets_form"):
            st.markdown("**Set each player's budget** (€ contributed to the Revolut pocket)")
            _new_budgets: dict[str, float] = {}
            _b_cols = st.columns(2)
            for _bi, (_b_idx, _b_row) in enumerate(_budg_st.iterrows()):
                _b_player = str(_b_row["Player"])
                _b_cur = float(pd.to_numeric(_b_row.get("Budget", 0.0), errors="coerce") or 0.0)
                with _b_cols[_bi % 2]:
                    _new_budgets[_b_player] = st.number_input(
                        _b_player,
                        min_value=0.0,
                        max_value=500.0,
                        value=_b_cur,
                        step=0.5,
                        format="%.2f",
                        key=f"budget_{_b_player}",
                    )

            if st.form_submit_button("💾 Save Budgets", type="primary"):
                from src.competition import (
                    load_purchases as _lp_b, add_purchase as _ap_b,
                    mark_paid as _mp_b,
                )
                from src.event_engine import process_pending_purchases as _ppp_b
                _budg_st2 = _lps_b().copy()
                _budg_st2["Budget"] = _budg_st2["Player"].map(_new_budgets).fillna(0.0)

                # Auto-add BuyIn for any player whose budget is >= €5 (cost of Buy In).
                # Remove BuyIn and mark UNPAID for any player whose budget drops below €5.
                _purch_b = _lp_b()
                _has_buyin = set(_purch_b[_purch_b["PurchaseType"] == "BuyIn"]["Player"].tolist()) if not _purch_b.empty else set()
                from src.competition import mark_unpaid as _mu_b
                for _bp, _bv in _new_budgets.items():
                    if _bv >= 5.0 and _bp not in _has_buyin:
                        _purch_b = _ap_b(_bp, "BuyIn", "auto (budget set)", _purch_b)
                    elif _bv < 5.0 and _bp in _has_buyin:
                        # Budget dropped below Buy In cost — remove auto BuyIn and mark UNPAID
                        _purch_b = _purch_b[
                            ~((_purch_b["Player"] == _bp) &
                              (_purch_b["PurchaseType"] == "BuyIn") &
                              (_purch_b["Reference"].str.contains("auto", case=False, na=False)))
                        ].reset_index(drop=True)
                        _budg_st2 = _mu_b(_bp, _budg_st2)
                _up_b, _us_b, _ = _ppp_b(_purch_b, _budg_st2)
                # Preserve the budget values (process_pending_purchases may not know about Budget)
                _us_b["Budget"] = _us_b["Player"].map(_new_budgets).fillna(0.0)
                _save_purchases(_up_b)
                _save_statuses(_us_b)
                _refresh()
                _new_pool = sum(_new_budgets.values())
                st.success(f"Budgets saved. New prize pool: **€{_new_pool:.2f}**")
                st.rerun()

        st.divider()
        st.markdown("**Spend vs budget breakdown**")
        st.caption("Spend is computed from purchase records × unit price. Available = Budget − Spent.")

        try:
            from dashboard.data import get_player_budgets as _gpb
            _bdf = _gpb()
            if _bdf.empty:
                st.info("No data yet.")
            else:
                def _bdf_style(row):
                    styles = []
                    for col in row.index:
                        if col == "Budget":
                            styles.append("color:#D4A017;font-weight:700")
                        elif col == "Available":
                            try:
                                v = float(str(row[col]).replace("€", "") or 0)
                            except (ValueError, TypeError):
                                v = 0.0
                            styles.append("color:#EF4444;font-weight:700" if v < 0 else (
                                "color:#6EE7B7;font-weight:600" if v > 0 else "color:#9CA3AF"))
                        else:
                            styles.append("")
                    return styles

                _bdf_disp = _bdf.copy()
                for _c in ["Budget", "Spent", "Available"]:
                    _bdf_disp[_c] = _bdf_disp[_c].apply(lambda v: f"€{float(v):.2f}")
                st.dataframe(_bdf_disp.style.apply(_bdf_style, axis=1),
                             use_container_width=True, hide_index=True)
        except Exception as _be:
            st.warning(f"Could not load budget detail: {_be}")
