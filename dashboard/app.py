"""World Cup 2026 Sweepstake — Streamlit app entry point."""
import sys
from pathlib import Path

# Ensure THIS project's root is always first in sys.path so its src/ package
# shadows any identically-named src/ in other World Cup directories.
_ROOT = Path(__file__).parent.parent
_root_str = str(_ROOT)
while _root_str in sys.path:
    sys.path.remove(_root_str)
sys.path.insert(0, _root_str)

# Purge any src.* modules that were loaded from a different project root so
# they get re-imported from the correct location on next access.
_wrong = [k for k in sys.modules if k == "src" or k.startswith("src.")
          if hasattr(sys.modules[k], "__file__") and sys.modules[k].__file__
          and not sys.modules[k].__file__.startswith(_root_str)]
for _k in _wrong:
    del sys.modules[_k]

import streamlit as st

st.set_page_config(
    page_title="WC 2026 Sweepstake",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

# Inject global CSS
_css = Path(__file__).parent / "assets" / "style.css"
if _css.exists():
    st.markdown(f"<style>{_css.read_text()}</style>", unsafe_allow_html=True)

pages = [
    st.Page("pages/home.py",               title="Home",               icon="🏠", default=True),
    st.Page("pages/leaderboard.py",        title="Leaderboard",        icon="🏆"),
    st.Page("pages/story.py",             title="Tournament News",    icon="📰"),
    st.Page("pages/player_portfolios.py",  title="My Portfolio",       icon="👤"),
    st.Page("pages/teams.py",              title="Teams",              icon="⚽"),
    st.Page("pages/bracket.py",            title="Bracket",            icon="🏟️"),
    st.Page("pages/predictions_centre.py", title="Predictions",        icon="🔮"),
    st.Page("pages/analytics.py",          title="Analytics",          icon="📊"),
    st.Page("pages/shop.py",               title="Shop & Purchases",   icon="🛒"),
    st.Page("pages/var_room.py",           title="VAR Room",           icon="🔍"),
    st.Page("pages/rules.py",              title="Rules",              icon="📋"),
    st.Page("pages/admin.py",              title="Admin",              icon="🔐"),
]

# ── Global player identity ────────────────────────────────────────────────
# Stored in session state so it persists across page navigations.
try:
    from dashboard.data import get_participants
    _players = sorted(get_participants())
except Exception:
    _players = []

if _players:
    with st.sidebar:
        st.markdown(
            '<div style="color:#9CA3AF;font-size:0.75rem;margin-bottom:0.2rem">'
            'Who are you?</div>',
            unsafe_allow_html=True,
        )
        _options = ["— select —"] + _players
        _current = st.session_state.get("viewer", "— select —")
        _idx = _options.index(_current) if _current in _options else 0
        _choice = st.selectbox(
            "viewer_select", _options, index=_idx,
            label_visibility="collapsed", key="viewer_select",
        )
        st.session_state["viewer"] = _choice if _choice != "— select —" else None

pg = st.navigation(pages)
pg.run()
