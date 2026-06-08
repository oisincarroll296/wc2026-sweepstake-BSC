"""Reusable UI helpers for the dashboard."""
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

_IST = timezone(timedelta(hours=1))
_TS_COLS = {"Timestamp", "ScheduledTime", "ExecutedTime"}


def _fmt_iso(v: str) -> str:
    try:
        dt = datetime.fromisoformat(str(v)).astimezone(_IST)
        return dt.strftime("%d %b %H:%M").lstrip("0")
    except Exception:
        return v


def load_css() -> None:
    css_path = Path(__file__).parent.parent / "assets" / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"<h1>{title}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<p style='color:#9CA3AF;margin-top:-0.5rem;'>{subtitle}</p>", unsafe_allow_html=True)


def metric_row(metrics: list[dict]) -> None:
    """metrics: list of {label, value, delta?}"""
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            delta = m.get("delta")
            st.metric(label=m["label"], value=m["value"], delta=delta)


def card(content_html: str, gold_border: bool = False) -> None:
    cls = "card-gold" if gold_border else "card"
    st.markdown(f'<div class="{cls}">{content_html}</div>', unsafe_allow_html=True)


def rank_badge(rank: int) -> str:
    if rank == 1:
        return '<span class="gold-badge">1st</span>'
    if rank == 2:
        return '<span class="silver-badge">2nd</span>'
    if rank == 3:
        return '<span class="bronze-badge">3rd</span>'
    return f"<span style='color:#9CA3AF'>#{rank}</span>"


def payment_tag(status: str) -> str:
    if status == "PAID":
        return '<span class="paid-tag">PAID</span>'
    return '<span class="unpaid-tag">UNPAID</span>'


def tier_color(tier: int) -> str:
    return {1: "#105AAC", 2: "#15803D", 3: "#A16207", 4: "#B91C1C"}.get(tier, "#9CA3AF")


def tier_badge(tier: int) -> str:
    color = tier_color(tier)
    return f'<span style="color:{color};font-weight:600">T{tier}</span>'


def empty_state(msg: str = "No data available yet.") -> None:
    st.markdown(
        f'<div class="card" style="text-align:center;color:#9CA3AF;padding:2rem">'
        f'<span style="font-size:2rem">⚽</span><br>{msg}</div>',
        unsafe_allow_html=True,
    )


def searchable_table(df: pd.DataFrame, search_placeholder: str = "Search…", key: str | None = None) -> None:
    """Render a DataFrame with an inline search filter."""
    if df.empty:
        empty_state()
        return
    df = df.copy()
    for col in _TS_COLS & set(df.columns):
        df[col] = df[col].apply(lambda v: _fmt_iso(str(v)) if v else v)
    query = st.text_input("", placeholder=search_placeholder, label_visibility="collapsed", key=key)
    if query:
        mask = df.apply(lambda col: col.astype(str).str.contains(query, case=False, na=False)).any(axis=1)
        df = df[mask]
    st.dataframe(df, use_container_width=True, hide_index=True)


def copyable_text(label: str, text: str) -> None:
    """Display text in a copyable code block with a label."""
    st.markdown(f"**{label}**")
    st.code(text, language=None)
