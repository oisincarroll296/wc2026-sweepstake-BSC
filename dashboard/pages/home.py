"""Home page — tournament overview dashboard."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import urllib.parse as _urlparse

import streamlit as st
import pandas as pd
from datetime import datetime

from dashboard.data import (
    get_prize_pool, get_overall_leaderboard, get_top_team,
    get_paid_count, get_pack_count, get_audit_log, get_events,
    get_assignments, get_participants, get_deadlines, countdown, DEADLINE_LABELS,
    get_fixtures, get_match_results, get_match_stats, get_tier_map, get_purchases,
)
from dashboard.components.ui import page_header, empty_state

ROOT = Path(__file__).parent.parent.parent


def _tournament_phase(events: pd.DataFrame) -> tuple[str, str]:
    """Return (phase_label, colour) based on logged events."""
    if events.empty:
        return "Pre-Tournament", "#6B7280"
    executed = events[events["Status"] == "EXECUTED"]["EventType"].tolist()
    if "TOURNAMENT_COMPLETE" in executed:
        return "Tournament Complete", "#D4A017"
    if "GROUP_STAGE_CLOSE" in executed:
        return "Knockout Rounds", "#15803D"
    if "INITIAL_DRAW" in executed:
        return "Group Stage", "#105AAC"
    return "Pre-Tournament", "#6B7280"


def _last_updated() -> str:
    """Return a human-readable 'last updated' string from the most recent match result."""
    p = ROOT / "data" / "match_results.csv"
    if not p.exists():
        return "No results yet"
    try:
        df = pd.read_csv(p, dtype=str).fillna("")
        if df.empty or "match_number" not in df.columns:
            return "No results yet"
        return f"{len(df)} result{'s' if len(df) != 1 else ''} entered"
    except Exception:
        return "—"


page_header("WC 2026 Sweepstake", "Live tournament tracker")

# ── Quick access — jump to a player's portfolio ─────────────────────────────
_participants_qa = get_participants()
if _participants_qa:
    _links = " ".join(
        f'<a href="/player_portfolios?player={_urlparse.quote(p)}" '
        f'target="_self" class="player-link-btn">{p}</a>'
        for p in sorted(_participants_qa)
    )
    st.markdown(
        f'<div style="margin-bottom:0.75rem">'
        f'<span style="font-size:0.78rem;color:#9CA3AF;display:block;margin-bottom:0.3rem">'
        f'Jump to your portfolio:</span>'
        f'<div style="display:flex;flex-wrap:wrap;gap:0.35rem">{_links}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

events   = get_events()
deadlines = get_deadlines()
phase, phase_colour = _tournament_phase(events)
last_upd = _last_updated()

# Next upcoming deadline
from datetime import datetime, timezone
_now = datetime.now(timezone.utc)
upcoming = []
for key, iso in deadlines.items():
    try:
        t = datetime.fromisoformat(iso).astimezone(timezone.utc)
        if t > _now:
            upcoming.append((t, key, iso))
    except Exception:
        pass
upcoming.sort()

# ── Phase banner ────────────────────────────────────────────────────────────
if upcoming:
    next_t, next_key, next_iso = upcoming[0]
    next_label = DEADLINE_LABELS.get(next_key, next_key.replace("_", " ").title())
    cd = countdown(next_iso)
    cd_colour = "#EF4444" if "d" not in cd and cd != "PASSED" else (
                "#F59E0B" if cd.startswith("1d") or cd.startswith("2d") else "#D4A017")
    deadline_tag = (
        f'<span style="color:#9CA3AF;font-size:0.8rem">'
        f'Next: <strong style="color:{cd_colour}">{next_label}</strong> '
        f'in <strong style="color:{cd_colour}">{cd}</strong>'
        f'</span>'
    )
else:
    deadline_tag = '<span style="color:#9CA3AF;font-size:0.8rem">No upcoming deadlines</span>'

st.markdown(
    f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.25rem;'
    f'background:{phase_colour}22;border:1px solid {phase_colour}55;'
    f'border-radius:8px;padding:0.5rem 1rem;margin-bottom:0.75rem">'
    f'<span style="color:{phase_colour};font-weight:700;font-size:0.95rem">● {phase}</span>'
    f'<span style="color:#9CA3AF;font-size:0.78rem">Updated {last_upd}</span>'
    f'{deadline_tag}'
    f'</div>',
    unsafe_allow_html=True,
)

# ── All deadlines expander ─────────────────────────────────────────────────
if deadlines:
    with st.expander("All Deadlines"):
        for key, iso in deadlines.items():
            label = DEADLINE_LABELS.get(key, key.replace("_", " ").title())
            cd = countdown(iso)
            passed = cd == "PASSED"
            colour = "#6B7280" if passed else "#F5F5F5"
            cd_colour = "#6B7280" if passed else "#D4A017"
            try:
                from datetime import timedelta, timezone as _tz
                _IST = _tz(timedelta(hours=1))
                _dt = datetime.fromisoformat(iso).astimezone(_IST)
                display_time = f"{_dt.day} {_dt.strftime('%b %Y %H:%M')}"
            except Exception:
                display_time = iso
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:0.3rem 0;border-bottom:1px solid #2A3A4A">'
                f'<span style="color:{colour};font-size:0.88rem">{label}</span>'
                f'<span style="font-size:0.85rem">'
                f'<span style="color:#9CA3AF">{display_time}</span>'
                f'&nbsp;&nbsp;<strong style="color:{cd_colour}">{cd}</strong>'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        st.markdown("")

# ── KPI Row ────────────────────────────────────────────────────────────────
pool     = get_prize_pool()
paid     = get_paid_count()
packs    = get_pack_count()
top_t, top_pts = get_top_team()
lb       = get_overall_leaderboard()
_assignments = get_assignments()

# Matches played per player (sum across all owned teams)
try:
    _mr = get_match_results()
    _played_teams: dict[str, int] = {}
    if not _mr.empty and "home_team" in _mr.columns:
        for _, _rrow in _mr.iterrows():
            for _tc in ["home_team", "away_team"]:
                _t = str(_rrow.get(_tc, "")).strip()
                if _t:
                    _played_teams[_t] = _played_teams.get(_t, 0) + 1
    _player_played: dict[str, int] = {
        p: sum(_played_teams.get(t, 0) for t in ts)
        for p, ts in _assignments.items()
    }
except Exception:
    _player_played = {}

r1c1, r1c2 = st.columns(2)
r2c1, r2c2 = st.columns(2)
with r1c1:
    st.metric("Prize Pool", f"€{pool.get('current_pot', 0):.2f}",
              help="Sum of all player budgets (money in the Revolut pocket)")
with r1c2:
    st.metric("Paid Players", f"{paid} / {len(lb)}" if not lb.empty else str(paid))
with r2c1:
    st.metric("Prediction Packs", packs)
with r2c2:
    if top_t:
        st.metric("Top Team", top_t, f"{top_pts:.0f} pts")
    else:
        st.metric("Top Team", "—")

st.divider()

# ── Player Summary Table ───────────────────────────────────────────────────
_PRICES_LOOKUP = {
    "BuyIn": 5, "PredictionPack": 5, "Mulligan": 3,
    "NinthTeam": 3, "Resurrection": 3, "Insurance": 2, "TeamSwap": 5,
}
_TC = {1: "#105AAC", 2: "#15803D", 3: "#A16207", 4: "#B91C1C"}

_ms_home    = get_match_stats()
_tmap_home  = get_tier_map()
_purch_home = get_purchases()

# Build set of eliminated teams: group stage eliminations + KO losers from match results
_elim_home: set[str] = set()
if not _ms_home.empty and "RoundReached" in _ms_home.columns:
    _elim_home = set(_ms_home[_ms_home["RoundReached"] == "GroupStage"]["Team"].tolist())
_fix_home = get_fixtures()
_res_home = get_match_results()
if not _res_home.empty and not _fix_home.empty and "match_number" in _res_home.columns:
    for _, _hr in _res_home.iterrows():
        _hmn = int(pd.to_numeric(_hr.get("match_number", 0), errors="coerce") or 0)
        if _hmn < 73 or _hmn == 103:
            continue
        _hfix = _fix_home[_fix_home["match_number"] == _hmn]
        if _hfix.empty:
            continue
        _hf = _hfix.iloc[0]
        _hh = str(_hf["home_team"]); _ha = str(_hf["away_team"])
        _hhg = int(float(_hr.get("home_goals", 0) or 0))
        _hag = int(float(_hr.get("away_goals", 0) or 0))
        _hpw = str(_hr.get("penalty_winner", "") or "").strip()
        if _hpw == "home" or (not _hpw and _hhg > _hag):
            _elim_home.add(_ha)
        elif _hpw == "away" or (not _hpw and _hag > _hhg):
            _elim_home.add(_hh)

def _alive_home(t: str) -> bool:
    return t not in _elim_home

# Build winner-of dict for placeholder resolution ("Winner match X")
_winner_of_home: dict[int, str] = {}
if not _res_home.empty and not _fix_home.empty and "match_number" in _res_home.columns:
    for _, _wr in _res_home.iterrows():
        _wmn = int(pd.to_numeric(_wr.get("match_number", 0), errors="coerce") or 0)
        if _wmn < 73 or _wmn == 103:
            continue
        _wfix = _fix_home[_fix_home["match_number"] == _wmn]
        if _wfix.empty:
            continue
        _wf  = _wfix.iloc[0]
        _whh = str(_wf["home_team"]); _wha = str(_wf["away_team"])
        _whg = int(float(_wr.get("home_goals", 0) or 0))
        _wag = int(float(_wr.get("away_goals", 0) or 0))
        _wpw = str(_wr.get("penalty_winner", "") or "").strip()
        if _wpw == "home" or (not _wpw and _whg > _wag):
            _winner_of_home[_wmn] = _whh
        elif _wpw == "away" or (not _wpw and _wag > _whg):
            _winner_of_home[_wmn] = _wha

def _resolve_home(raw: str) -> str:
    s = str(raw or "").strip()
    if s.startswith("Winner match "):
        mn_ = int(s.split()[-1])
        return _winner_of_home.get(mn_, s)
    return s

_pp_home: dict[str, set] = {}
if not _purch_home.empty:
    for _, _pr in _purch_home.iterrows():
        _pp_home.setdefault(str(_pr["Player"]), set()).add(str(_pr["PurchaseType"]))

if lb.empty:
    empty_state("No scores yet — draw pending.")
else:
    _leader_pts = float(lb.iloc[0]["TotalPoints"]) if "TotalPoints" in lb.columns else 0.0
    _sum_rows: list[dict] = []

    for _, _lrow in lb.iterrows():
        _rank   = int(_lrow.get("Rank", 0))
        _pts    = float(_lrow.get("TotalPoints", 0))
        _player = str(_lrow.get("Player", ""))
        _status = str(_lrow.get("PaymentStatus", "UNPAID"))
        _medal  = {1: "🥇", 2: "🥈", 3: "🥉"}.get(_rank, f"#{_rank}")
        _gap    = f"−{_leader_pts - _pts:.0f}" if _rank > 1 else "—"
        _played = _player_played.get(_player, 0)
        _teams  = _assignments.get(_player, [])
        _ph     = _pp_home.get(_player, set())
        _spent  = sum(_PRICES_LOOKUP.get(p, 0) for p in _ph)
        _sum_rows.append({
            "rank": _rank, "medal": _medal, "player": _player,
            "pts": int(_pts), "gap": _gap, "played": _played,
            "t1": sum(1 for t in _teams if _tmap_home.get(t,0)==1 and _alive_home(t)),
            "t2": sum(1 for t in _teams if _tmap_home.get(t,0)==2 and _alive_home(t)),
            "t3": sum(1 for t in _teams if _tmap_home.get(t,0)==3 and _alive_home(t)),
            "t4": sum(1 for t in _teams if _tmap_home.get(t,0)==4 and _alive_home(t)),
            "spent": _spent,
            "pack": "PredictionPack" in _ph, "ninth": "NinthTeam" in _ph,
            "res": "Resurrection" in _ph,    "swap": "TeamSwap"   in _ph,
            "status": _status,
        })

    # ── HTML table ────────────────────────────────────────────────────────
    _HS = "padding:0.32rem 0.6rem;font-size:0.71rem;font-weight:700;white-space:nowrap;text-align:center"
    _CS = "padding:0.38rem 0.6rem;font-size:0.83rem;text-align:center;border-bottom:1px solid #131f2e"
    _SEP = "border-right:1px solid #2A3A4A"

    def _th(txt, c="#9CA3AF", bg="transparent", extra="", rs=1, cs=1):
        return (
            f'<th rowspan="{rs}" colspan="{cs}" '
            f'style="{_HS};color:{c};background:{bg};{extra}">{txt}</th>'
        )

    h1 = (
        _th("",             c="#6B7280",  rs=2, extra="width:2.2rem")
        + _th("Player",     c="#F5F5F5",  rs=2, extra="text-align:left;min-width:90px")
        + _th("Pts",        c="#D4A017",  rs=2)
        + _th("Gap",        c="#9CA3AF",  rs=2)
        + _th("Played",     c="#9CA3AF",  rs=2, extra=_SEP)
        + _th("Teams Still In", c="#9CA3AF", cs=4,
              extra="border-bottom:1px solid #2A3A4A;" + _SEP)
        + _th("💵 Spent",   c="#6EE7B7",  rs=2, extra=_SEP)
        + _th("Purchases",  c="#9CA3AF",  cs=4,
              extra="border-bottom:1px solid #2A3A4A")
    )
    h2 = (
        _th("T1", c=_TC[1], bg=f"{_TC[1]}20")
        + _th("T2", c=_TC[2], bg=f"{_TC[2]}20")
        + _th("T3", c=_TC[3], bg=f"{_TC[3]}20")
        + _th("T4", c=_TC[4], bg=f"{_TC[4]}20", extra=_SEP)
        + _th("Pack",  c="#9CA3AF")
        + _th("9th",   c="#9CA3AF")
        + _th("Res",   c="#9CA3AF")
        + _th("Swap",  c="#9CA3AF")
    )

    def _td(val, extra=""):
        return f'<td style="{_CS};{extra}">{val}</td>'

    body = ""
    for r in _sum_rows:
        faded  = r["status"] == "UNPAID"
        leader = r["rank"] == 1 and not faded
        op     = "opacity:0.38;" if faded else ""
        row_bg = "background:rgba(212,160,23,0.07)" if leader else ""

        cells  = _td(r["medal"], f"{op}font-weight:700")
        pcolor = "#D4A017" if leader else "#F5F5F5"
        pw     = "800" if leader else "600"
        cells += f'<td style="{_CS};text-align:left;{op}color:{pcolor};font-weight:{pw}">{r["player"]}</td>'
        cells += _td(r["pts"],    f"{op}color:{'#D4A017' if leader else '#F5F5F5'};font-weight:{'800' if leader else '600'}")
        gap_c  = "#EF4444" if r["gap"] != "—" else "#D4A017"
        cells += _td(r["gap"],   f"{op}color:{gap_c}")
        cells += _td(r["played"],f"{op}{_SEP}")

        for n, tc in ((1,_TC[1]),(2,_TC[2]),(3,_TC[3]),(4,_TC[4])):
            v   = r[f"t{n}"]
            sep = _SEP if n == 4 else ""
            if faded:
                style = f"{op}{sep}"
            elif v == 0:
                style = f"color:#2A3A4A;font-weight:700;{sep}"
            elif v == 1:
                style = f"color:{tc};font-weight:700;opacity:0.6;{sep}"
            else:
                style = f"color:{tc};font-weight:800;{sep}"
            cells += _td(v, style)

        cells += _td(f"💵 €{r['spent']}", f"{op}color:#6EE7B7;font-weight:700;{_SEP}")

        for key in ("pack","ninth","res","swap"):
            v = r[key]
            cells += _td("✓" if v else "·",
                         f"{op}color:{'#6EE7B7' if v else '#2A3A4A'};font-weight:{'700' if v else '400'}")

        body += f'<tr style="{row_bg}">{cells}</tr>'

    st.markdown(
        f'<div style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse;background:#0D1B2A;'
        f'border-radius:8px;overflow:hidden;font-family:inherit">'
        f'<thead>'
        f'<tr style="background:#1A2535;border-bottom:1px solid #2A3A4A">{h1}</tr>'
        f'<tr style="background:#1A2535;border-bottom:2px solid #2A3A4A">{h2}</tr>'
        f'</thead>'
        f'<tbody>{body}</tbody>'
        f'</table></div>'
        f'<div style="font-size:0.69rem;color:#4B5563;margin-top:0.3rem">'
        f'T1–T4 = teams still in the tournament per tier (2 per tier at start) &nbsp;·&nbsp; '
        f'Unpaid players faded</div>',
        unsafe_allow_html=True,
    )

st.divider()

# ── Prize Split + Fixtures ─────────────────────────────────────────────────
col_left, col_right = st.columns([2, 3], gap="large")

with col_left:
    st.subheader("Prize Split")
    pool_val = pool.get("current_pot", 0)
    splits = [
        ("🥇 1st Place", pool.get("first_prize", 0)),
        ("🥈 2nd Place", pool.get("second_prize", 0)),
        ("🥉 3rd Place", pool.get("third_prize", 0)),
    ]
    for label, amount in splits:
        pct = f"{amount / pool_val * 100:.0f}%" if pool_val else "—"
        st.markdown(
            f'<div class="card" style="display:flex;justify-content:space-between;align-items:center">'
            f'<span>{label}</span>'
            f'<span style="color:#D4A017;font-size:1.05rem;font-weight:700">'
            f'€{amount:.2f} <span style="color:#9CA3AF;font-size:0.75rem">{pct}</span>'
            f'</span></div>',
            unsafe_allow_html=True,
        )

with col_right:
    # Today's Fixtures
    st.subheader("Today's Fixtures")
    try:
        from datetime import date as _date
        from dashboard.data import get_fixtures, get_match_results
        _fix_df = get_fixtures()
        _res_df = get_match_results()
        _owned  = {t for ts in get_assignments().values() for t in ts}
        _today  = _date.today()
        _today_matches = _fix_df[_fix_df["match_date"] == _today] if not _fix_df.empty else pd.DataFrame()

        _entered_nums: set = set()
        if not _res_df.empty and "match_number" in _res_df.columns:
            _entered_nums = set(_res_df["match_number"].dropna().astype(int).tolist())

        if _today_matches.empty:
            st.markdown(
                '<div class="card"><span style="color:#9CA3AF">No matches today.</span></div>',
                unsafe_allow_html=True,
            )
        else:
            for _, _m in _today_matches.iterrows():
                _h, _a = _resolve_home(_m["home_team"]), _resolve_home(_m["away_team"])
                _hc = "#D4A017" if _h in _owned else "#F5F5F5"
                _ac = "#D4A017" if _a in _owned else "#F5F5F5"
                _grp = _m.get("group", "")
                _mn  = int(pd.to_numeric(_m["match_number"], errors="coerce") or 0)
                _score_html = ""
                if _mn in _entered_nums and not _res_df.empty:
                    _rr = _res_df[_res_df["match_number"] == _mn]
                    if not _rr.empty:
                        _hg = int(float(_rr.iloc[0].get("home_goals", 0) or 0))
                        _ag = int(float(_rr.iloc[0].get("away_goals", 0) or 0))
                        _score_html = f' <strong style="color:#6EE7B7">{_hg}–{_ag}</strong>'
                st.markdown(
                    f'<div class="card" style="padding:0.4rem 0.7rem;margin-bottom:0.3rem">'
                    f'<span style="color:#6B7280;font-size:0.7rem">Grp {_grp}&nbsp;&nbsp;</span>'
                    f'<span style="color:{_hc};font-weight:600;font-size:0.82rem">{_h}</span>'
                    f'<span style="color:#6B7280;font-size:0.78rem">{_score_html} v </span>'
                    f'<span style="color:{_ac};font-weight:600;font-size:0.82rem">{_a}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    except Exception:
        pass

    # Next Event
    def _render_next_fixtures() -> None:
        from datetime import date as _date, timedelta as _td2
        _fix = get_fixtures()
        if _fix.empty:
            st.markdown('<div class="card"><span style="color:#9CA3AF">No upcoming fixtures.</span></div>', unsafe_allow_html=True)
            return
        _today = _date.today()
        _tomorrow = _today + _td2(days=1)
        _day_fix = pd.DataFrame()
        for _target in [_tomorrow, None]:
            if _target:
                _candidate = _fix[_fix["match_date"] == _target.strftime("%d/%m/%Y")]
            else:
                _future = _fix[pd.to_datetime(_fix["match_date"], format="%d/%m/%Y", errors="coerce") > pd.Timestamp(_today)]
                if _future.empty:
                    st.markdown('<div class="card"><span style="color:#9CA3AF">No upcoming fixtures.</span></div>', unsafe_allow_html=True)
                    return
                _next_date = pd.to_datetime(_future["match_date"], format="%d/%m/%Y", errors="coerce").min()
                _candidate = _fix[pd.to_datetime(_fix["match_date"], format="%d/%m/%Y", errors="coerce") == _next_date]
            if not _candidate.empty:
                _day_fix = _candidate
                break

        if _day_fix.empty:
            st.markdown('<div class="card"><span style="color:#9CA3AF">No upcoming fixtures.</span></div>', unsafe_allow_html=True)
            return

        _dt = pd.to_datetime(_day_fix.iloc[0]["match_date"], format="%d/%m/%Y", errors="coerce")
        try:
            _day_label = "Tomorrow" if _dt.date() == _tomorrow else _dt.strftime("%A") + " " + str(_dt.day) + " " + _dt.strftime("%b")
        except Exception:
            _day_label = str(_dt.date())

        st.markdown(
            f'<p style="color:#D4A017;font-weight:700;font-size:0.85rem;margin:0 0 0.4rem">'
            f'{_day_label} · {len(_day_fix)} match{"es" if len(_day_fix) != 1 else ""}</p>',
            unsafe_allow_html=True,
        )
        for _, _m in _day_fix.iterrows():
            _ko = str(_m.get("kickoff_time", "")).strip()
            _grp = str(_m.get("group", "")).strip()
            _lbl = f"Group {_grp}" if _grp else "Knockout"
            _time_str = f"{_ko} GMT · " if _ko else ""
            st.markdown(
                f'<div class="card" style="padding:0.4rem 0.7rem;margin:0.2rem 0">'
                f'<span style="color:#F1F5F9;font-weight:600">'
                f'{_resolve_home(_m["home_team"])} <span style="color:#6B7280">vs</span> {_resolve_home(_m["away_team"])}</span>'
                f'<span style="color:#6B7280;font-size:0.72rem;float:right">{_time_str}{_lbl}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.subheader("Next Event")
    if not events.empty:
        scheduled = events[events["Status"].isin(["SCHEDULED", "OPEN"])]
        if not scheduled.empty:
            nxt = scheduled.iloc[0]
            try:
                from datetime import timedelta as _td, timezone as _tz2
                _IST2 = _tz2(_td(hours=1))
                _sched_iso = str(nxt.get("ScheduledTime", "") or "")
                _sched_label = datetime.fromisoformat(_sched_iso).astimezone(_IST2).strftime("%d %b %H:%M") if _sched_iso else ""
            except Exception:
                _sched_label = ""
            st.markdown(
                f'<div class="card-gold">'
                f'<p style="color:#D4A017;font-weight:700;margin:0">'
                f'{str(nxt["EventType"]).replace("_", " ")}</p>'
                f'<p style="color:#9CA3AF;font-size:0.8rem;margin:0.25rem 0 0">'
                f'{_sched_label}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            _render_next_fixtures()
    else:
        _render_next_fixtures()

st.divider()

# ── Recent Activity ────────────────────────────────────────────────────────
st.subheader("Recent Activity")
audit = get_audit_log()
if audit.empty:
    empty_state("No activity recorded yet.")
else:
    recent = audit.tail(10).iloc[::-1].reset_index(drop=True)
    show = [c for c in ["Timestamp", "Event", "Player", "Action", "Result"] if c in recent.columns]
    st.dataframe(recent[show], use_container_width=True, hide_index=True)
