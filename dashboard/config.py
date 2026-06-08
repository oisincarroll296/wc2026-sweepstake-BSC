"""Shared config for the Streamlit dashboard."""
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR    = ROOT / "data"
EXPORTS_DIR = ROOT / "exports"

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "wc2026admin")

COLORS = {
    "gold":   "#D4A017",
    "navy":   "#0D1B2A",
    "navy2":  "#1E2937",
    "white":  "#F5F5F5",
    "silver": "#C0C0C0",
    "bronze": "#CD7F32",
    "t1":     "#105AAC",
    "t2":     "#15803D",
    "t3":     "#A16207",
    "t4":     "#B91C1C",
    "green":  "#6EE7B7",
    "muted":  "#9CA3AF",
}

TIER_COLORS = {1: "#105AAC", 2: "#15803D", 3: "#A16207", 4: "#B91C1C"}
TIER_LABELS = {1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4"}

RANK_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0D1B2A",
    plot_bgcolor="#1E2937",
    font=dict(color="#F5F5F5", family="sans-serif"),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(bgcolor="#1E2937", bordercolor="#2A3A4A"),
    xaxis=dict(gridcolor="#2A3A4A", linecolor="#2A3A4A"),
    yaxis=dict(gridcolor="#2A3A4A", linecolor="#2A3A4A"),
)
