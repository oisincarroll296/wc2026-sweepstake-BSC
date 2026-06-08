"""Home page — tournament overview dashboard."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import urllib.parse as _urlparse

import streamlit as st
import pandas as pd
from datetime import datetime

from dashboard.data import (
    get_prize_pool, get_overall_leaderboard, get_top_team,
    get_paid_count, get_pack_count, get_audit_log, get_events,
    get_assignments, get_participants, get_deadlines, countdown, DEADLINE_LABELS,
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
        # Use row count as proxy — most recent result = last row
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

r1c1, r1c2 = st.columns(2)
r2c1, r2c2 = st.columns(2)
with r1c1:
    st.metric("Prize Pool", f"€{pool.get('current_pot', 0):.2f}")
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

# ── Two-column layout ──────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    st.subheader("Current Standings")
    if lb.empty:
        empty_state("No scores yet — draw pending.")
    else:
        leader_pts = float(lb.iloc[0]["TotalPoints"]) if "TotalPoints" in lb.columns else 0.0

        rows = []
        for _, row in lb.iterrows():
            rank   = int(row.get("Rank", 0))
            pts    = float(row.get("TotalPoints", 0))
            status = row.get("PaymentStatus", "UNPAID")
            medal  = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
            gap    = f"{pts - leader_pts:+.0f}" if rank > 1 else "—"
            rows.append({
                "":       medal,
                "Player": row.get("Player", ""),
                "Points": f"{pts:.0f}",
                "Gap":    gap,
                "Status": status,
            })

        display = pd.DataFrame(rows)
        lb_status = lb["PaymentStatus"].tolist() if "PaymentStatus" in lb.columns else ["PAID"] * len(lb)

        def _row_style(row):
            status = lb_status[row.name]
            if status == "UNPAID":
                return ["color: #6B7280"] * len(row)
            if row.name == 0:
                return ["background-color: rgba(212,160,23,0.15); font-weight:700"] * len(row)
            return [""] * len(row)

        st.dataframe(
            display.style.apply(_row_style, axis=1),
            use_container_width=True, hide_index=True,
        )

with col_right:
    # Prize Split
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
                _h, _a = _m["home_team"], _m["away_team"]
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
            st.markdown(
                '<div class="card"><span style="color:#9CA3AF">No upcoming events scheduled.</span></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="card"><span style="color:#9CA3AF">Draw not yet run.</span></div>',
            unsafe_allow_html=True,
        )

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
