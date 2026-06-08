"""The VAR Room — transparency centre with full audit trail."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import (
    get_purchases, get_statuses, get_events, get_audit_log,
)
from dashboard.components.ui import page_header, searchable_table, empty_state

_ROOT = Path(__file__).parent.parent.parent
EXPORTS = _ROOT / "exports"


def _load_csv(name: str) -> pd.DataFrame:
    path = _ROOT / "data" / name
    if path.exists():
        try:
            return pd.read_csv(path, dtype=str).fillna("")
        except Exception:
            pass
    path2 = EXPORTS / name
    if path2.exists():
        try:
            return pd.read_csv(path2, dtype=str).fillna("")
        except Exception:
            pass
    return pd.DataFrame()


page_header("🔍 The VAR Room", "Full transparency — every transaction, draw, and decision")

tabs = st.tabs([
    "Payment Ledger", "Prize Pool", "Event Timeline",
    "Audit Log", "Draw History", "Random Seeds", "Transaction History",
])

# ── 1. Payment Ledger ──────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("💳 Payment Ledger")
    df = get_purchases()
    if not df.empty:
        from src.competition import PRICES as _PRICES
        disp = df.copy()
        disp.insert(2, "Amount", disp["PurchaseType"].map(_PRICES).fillna(0.0).apply(lambda x: f"€{x:.0f}"))
        show_cols = [c for c in ["Player", "PurchaseType", "Amount", "Selection", "Reference", "Timestamp"] if c in disp.columns]
        searchable_table(disp[show_cols], "Search player or purchase type…", key="tbl_payment_ledger")
    else:
        empty_state("No payment data yet.")

# ── 2. Prize Pool Breakdown ────────────────────────────────────────────────
with tabs[1]:
    st.subheader("💰 Prize Pool Breakdown")
    from dashboard.data import get_prize_pool
    pool = get_prize_pool()
    st.metric("Total Pot",   f"€{pool.get('current_pot',0):.2f}")
    st.metric("1st Prize",   f"€{pool.get('first_prize',0):.2f}")
    st.metric("2nd Prize",   f"€{pool.get('second_prize',0):.2f}")
    st.metric("3rd Prize",   f"€{pool.get('third_prize',0):.2f}")
    st.divider()
    # Per-type breakdown
    p = get_purchases()
    from src.competition import PRICES
    rows = []
    for ptype, price in PRICES.items():
        cnt = int((p["PurchaseType"] == ptype).sum()) if not p.empty else 0
        rows.append({"Type": ptype, "Count": cnt, "Total": f"€{cnt * price:.0f}"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── 3. Event Timeline ──────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("📅 Event Timeline")
    ev = get_events()
    if ev.empty:
        empty_state("No events recorded.")
    else:
        from dashboard.components.ui import _fmt_iso, _TS_COLS
        disp_ev = ev.copy()
        for _c in _TS_COLS & set(disp_ev.columns):
            disp_ev[_c] = disp_ev[_c].apply(lambda v: _fmt_iso(str(v)) if v else v)
        st.dataframe(disp_ev, use_container_width=True, hide_index=True)

# ── 4. Audit Log ──────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("📋 Audit Log")
    audit = get_audit_log()
    if audit.empty:
        empty_state("No audit entries yet.")
    else:
        searchable_table(audit.iloc[::-1].reset_index(drop=True), "Search events, players, actions…", key="tbl_audit_log")

# ── 5. Draw History ───────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("🎲 Draw History")
    audit = get_audit_log()
    sub = st.tabs(["Initial Draw", "Mulligan Draws", "Ninth Team Draws", "Resurrection Draws"])
    with sub[0]:
        st.caption("The original team allocation draw.")
        from dashboard.data import get_assignments
        alloc = get_assignments()
        if alloc:
            draw_rows = []
            for player, teams in sorted(alloc.items()):
                draw_rows.append({"Player": player, "Teams": ", ".join(teams)})
            st.dataframe(pd.DataFrame(draw_rows), use_container_width=True, hide_index=True)
        else:
            empty_state("Draw not yet completed.")
    with sub[1]:
        if not audit.empty:
            df = audit[audit["Event"] == "MULLIGAN_DRAW"].reset_index(drop=True) if "Event" in audit.columns else pd.DataFrame()
        else:
            df = pd.DataFrame()
        # Also try exports file as fallback
        if df.empty:
            df = _load_csv("mulligan_results.csv") if (EXPORTS / "mulligan_results.csv").exists() else pd.DataFrame()
        searchable_table(df, key="tbl_mulligan") if not df.empty else empty_state("No mulligan draws recorded.")
    with sub[2]:
        if not audit.empty:
            df = audit[audit["Event"] == "NINTH_TEAM_DRAW"].reset_index(drop=True) if "Event" in audit.columns else pd.DataFrame()
        else:
            df = pd.DataFrame()
        if df.empty:
            df = _load_csv("ninth_team_results.csv") if (EXPORTS / "ninth_team_results.csv").exists() else pd.DataFrame()
        searchable_table(df, key="tbl_ninth_team") if not df.empty else empty_state("No ninth team draws recorded.")
    with sub[3]:
        if not audit.empty:
            df = audit[audit["Event"] == "RESURRECTION_DRAW"].reset_index(drop=True) if "Event" in audit.columns else pd.DataFrame()
        else:
            df = pd.DataFrame()
        if df.empty:
            df = _load_csv("resurrection_results.csv") if (EXPORTS / "resurrection_results.csv").exists() else pd.DataFrame()
        searchable_table(df, key="tbl_resurrection") if not df.empty else empty_state("No resurrection draws recorded.")

# ── 6. Random Seeds ───────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("🎯 Draw Seeds")
    st.caption(
        "Every random draw uses a seed so results can be verified and reproduced. "
        "The seed is recorded in the Event Timeline above."
    )
    ev = get_events()
    if not ev.empty:
        draw_ev = ev[ev["EventType"].isin(["INITIAL_DRAW","MULLIGAN_DRAW","NINTH_TEAM_DRAW","RESURRECTION_DRAW"])] if "EventType" in ev.columns else pd.DataFrame()
        if not draw_ev.empty:
            from dashboard.components.ui import _fmt_iso
            show = draw_ev[["EventType", "ExecutedTime", "RandomSeed"]].copy() if all(c in draw_ev.columns for c in ["EventType","ExecutedTime","RandomSeed"]) else draw_ev.copy()
            if "ExecutedTime" in show.columns:
                show["ExecutedTime"] = show["ExecutedTime"].apply(lambda v: _fmt_iso(str(v)) if v else v)
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            empty_state("No draw events recorded yet.")
    else:
        empty_state("No events recorded yet.")

# ── 7. Transaction History ─────────────────────────────────────────────────
with tabs[6]:
    st.subheader("📑 Transaction History")
    p = get_purchases()
    if p.empty:
        empty_state("No transactions recorded.")
    else:
        searchable_table(p.iloc[::-1].reset_index(drop=True), "Search player or purchase type…", key="tbl_transactions")
