"""Admin page — password-protected event and draw controls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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


def _refresh():
    st.cache_data.clear()


def _save_purchases(df: pd.DataFrame):
    df.to_csv(DATA / "purchases.csv", index=False)


def _save_statuses(df: pd.DataFrame):
    df.to_csv(DATA / "players.csv", index=False)


# ── Tabs ──────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "Draw Events", "Purchases", "Picks",
    "Locking", "Results Entry", "Special Events",
    "Tournament Results",
    "WhatsApp", "Draw Broadcast", "Deadlines", "Snapshots",
])

# ─────────────────────────────────────────────
# Tab 0: Draw Events
# ─────────────────────────────────────────────
with tabs[0]:
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
                elif _del_type == "NINTH_TEAM_DRAW":
                    if not _purch.empty and "PurchaseType" in _purch.columns:
                        mask = _purch["PurchaseType"] == "NinthTeam"
                        _purch.loc[mask, "Selection"] = ""
                        _purch.to_csv(DATA / "purchases.csv", index=False)
                elif _del_type == "RESURRECTION_DRAW":
                    if not _purch.empty and "PurchaseType" in _purch.columns:
                        mask = (
                            (_purch["PurchaseType"] == "Resurrection") &
                            (_purch["Selection"].str.contains("->", na=False))
                        )
                        _purch.loc[mask, "Selection"] = ""
                        _purch.to_csv(DATA / "purchases.csv", index=False)

                # 2. Remove the event row
                _ev_df_new = _ev_df[_ev_df["EventID"].astype(str) != _del_eid].copy()
                _ev_df_new.to_csv(DATA / "events.csv", index=False)

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
with tabs[1]:
    st.subheader("Add Purchase")
    st.caption("Record a payment received via the Shared Revolut Pocket.")

    from src.competition import PRICES as _PRICES
    _price_labels = {k: f"{k}  (€{int(v)})" for k, v in _PRICES.items()}

    with st.form("add_purchase"):
        from dashboard.data import get_participants
        players = get_participants() or []
        add_player = st.selectbox("Player", players or ["—"])
        add_type   = st.selectbox("Type", list(_price_labels.keys()), format_func=lambda k: _price_labels[k])
        add_ref    = st.text_input("Payment Reference (optional)", placeholder="e.g. Oisin - BUY IN")
        add_sel    = st.text_input("Resurrection — player's eliminated team to swap out", placeholder="e.g. Spain (you choose which of your eliminated teams to replace)")
        submitted  = st.form_submit_button("Add Purchase", type="primary")

        if submitted and add_player and add_player != "—":
            try:
                from src.competition import add_purchase, load_purchases, load_player_status
                from src.event_engine import process_pending_purchases

                p = load_purchases()
                s = load_player_status()
                p = add_purchase(add_player, add_type, add_ref, p, selection=add_sel)

                # Mark PAID for BuyIn
                up, us, _msgs = process_pending_purchases(p, s)
                _save_purchases(up)
                _save_statuses(us)

                cost = _PRICES.get(add_type, 0)
                st.success(f"✓ {add_type} added for {add_player}  (€{int(cost)})")
                _refresh()
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

# ─────────────────────────────────────────────
# Tab 2: Picks (captains + predictions)
# ─────────────────────────────────────────────
with tabs[2]:
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
            "GoldenBoot", "DarkHorse", "FirstKnockedOut",
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

            pd4, pd5, pd6 = st.columns(3)
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
            with pd6:
                st.markdown("**First Knocked Out**")
                st.caption("Any team — first eliminated from the tournament")
                cur_fko = _v("FirstKnockedOut")
                fko_idx = ([""] + _all_teams).index(cur_fko) if cur_fko in ([""] + _all_teams) else 0
                new_fko = st.selectbox("Any team", [""] + _all_teams, index=fko_idx,
                                       key="fko", label_visibility="collapsed")

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
                    _picks_df.loc[_row_mask, "FirstKnockedOut"]      = new_fko
                    _picks_df.to_csv(_players_path, index=False)
                    st.success(f"Picks saved for {_player_sel}.")
                    _refresh()

        st.divider()
        st.markdown("**All current picks**")
        _show_picks = _picks_df[["Player"] + _pick_cols].copy()
        st.dataframe(_show_picks, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# Tab 3: Locking
# ─────────────────────────────────────────────
with tabs[3]:
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
with tabs[4]:
    from datetime import date as _date, timedelta as _td
    from dashboard.data import (
        get_fixtures, get_match_results, save_match_result_and_recalculate,
        get_teams,
    )
    from src.scoring_engine import load_match_stats

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
                            pw_label = m["home_team"] if pwin == "home" else m["away_team"]
                            score_str += f" · {pw_label} win on pens"

                    label = f"{dot} M{mn}: {m['home_team']} v {m['away_team']}"
                    match_options.append((label + score_str, mn, m))

                sel_label = st.selectbox(
                    "Select match to enter / edit",
                    [opt[0] for opt in match_options],
                )
                sel_idx  = [opt[0] for opt in match_options].index(sel_label)
                sel_mn   = match_options[sel_idx][1]
                sel_fix  = match_options[sel_idx][2]

                home_team = sel_fix["home_team"]
                away_team = sel_fix["away_team"]
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
            with ca1: g_goals  = st.number_input("Goals",      0, 50, _ev("GroupGoals"))
            with ca2: g_cs     = st.number_input("Cl. Sheets", 0, 10, _ev("GroupCleanSheets"))
            with ca3: g_pw     = st.number_input("Pen. Wins",  0,  5, _ev("GroupPenaltyWins"))
            with ca4: g_cw     = st.number_input("CB Wins",    0,  5, _ev("GroupComebackWins"))
            with ca5: g_winner = st.checkbox("Group Winner", value=bool(_ev("GroupWinner")))

            st.markdown("**Knockout**")
            cb1, cb2, cb3, cb4 = st.columns(4)
            with cb1: ko_goals = st.number_input("Goals",      0, 50, _ev("KnockoutGoals"))
            with cb2: ko_cs    = st.number_input("Cl. Sheets", 0, 10, _ev("KnockoutCleanSheets"))
            with cb3: ko_pw    = st.number_input("Pen. Wins",  0,  5, _ev("KnockoutPenaltyWins"))
            with cb4: ko_cw    = st.number_input("CB Wins",    0,  5, _ev("KnockoutComebackWins"))
            rounds  = ["", "GroupStage", "R16", "QF", "SF", "Final", "Winner"]
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
                    st.success(f"Saved {res_team}.")
                    _refresh()
                except Exception as exc:
                    st.error(f"{exc}")

# ─────────────────────────────────────────────
# Tab 5: Special Events
# ─────────────────────────────────────────────
with tabs[5]:
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

        st.markdown("**Red Cards** (−15 per card)")
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
with tabs[6]:
    import json as _json
    st.subheader("Tournament Results")
    st.caption(
        "Set the final outcomes used for prediction bonus calculations. "
        "Leave fields blank until the result is known. "
        "First Knocked Out is auto-derived from the Special Events tab."
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
with tabs[7]:
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
with tabs[8]:
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
with tabs[9]:
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
with tabs[10]:
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
