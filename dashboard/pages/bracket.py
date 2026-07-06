"""Tournament Bracket — FIFA-style knockout bracket + group stage draw."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _p) if _p not in sys.path else None

from datetime import datetime
from dataclasses import dataclass, field

import streamlit as st

from dashboard.data import (
    get_match_stats, get_assignments, get_tier_map, get_teams,
    get_fixtures, get_match_results,
)
from dashboard.config import TIER_COLORS
from dashboard.components.ui import empty_state

# ── Page heading ──────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="font-family:system-ui,-apple-system,sans-serif;font-size:1.75rem;'
    'font-weight:800;color:#0f172a;margin-bottom:0.1rem">FIFA World Cup Schedule</h1>',
    unsafe_allow_html=True,
)

# ── Shared data ───────────────────────────────────────────────────────────────
match_stats = get_match_stats()
assignments = get_assignments()
tier_map    = get_tier_map()
teams_df    = get_teams()
fixtures_df = get_fixtures()
results_df  = get_match_results()

_owner_map: dict[str, list[str]] = {}
for _player, _teams_list in assignments.items():
    for _t in _teams_list:
        _owner_map.setdefault(_t, []).append(_player)

TIER_LABELS = {1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4"}

# ── Bracket constants ─────────────────────────────────────────────────────────
CARD_H   = 130     # px: height of one match card
CARD_W   = 210     # px: width (wide enough for full owner names)
BASE     = 154     # px: one R32 slot (card + gap)
TOTAL_H  = 16 * BASE          # 2464 px total bracket height
COL_W    = CARD_W + 16        # column width
CONN_W   = 52                 # px: connector column width between rounds
LINE_CLR = "#5aa34f"

# Visual order of match numbers in each round (top to bottom in the bracket)
BRACKET_SLOTS: list[list[int]] = [
    [74, 77, 73, 75, 83, 84, 81, 82, 76, 78, 79, 80, 86, 88, 85, 87],
    [89, 90, 93, 94, 91, 92, 95, 96],
    [97, 98, 99, 100],
    [101, 102],
    [104],
]
ROUND_LABELS = ["Last 32", "Last 16", "Quarter-finals", "Semi-finals", "Final"]
DAY_ABBR     = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

# flagcdn.com country codes for <img> flags (renders reliably in browsers)
_FLAG_CDN: dict[str, str] = {
    "Germany": "de",       "Paraguay": "py",      "France": "fr",
    "Sweden": "se",        "South Africa": "za",  "Canada": "ca",
    "Netherlands": "nl",   "Morocco": "ma",        "Portugal": "pt",
    "Croatia": "hr",       "Spain": "es",          "Austria": "at",
    "Switzerland": "ch",   "Algeria": "dz",        "Argentina": "ar",
    "Cabo Verde": "cv",    "Colombia": "co",        "Ghana": "gh",
    "Australia": "au",     "Egypt": "eg",           "USA": "us",
    "Bosnia and Herzegovina": "ba",                 "Belgium": "be",
    "Senegal": "sn",        "Brazil": "br",          "Japan": "jp",
    "England": "gb-eng",   "Congo DR": "cd",        "Mexico": "mx",
    "Ecuador": "ec",        "Cote d Ivoire": "ci",  "Norway": "no",
    "Scotland": "gb-sct",  "Uruguay": "uy",
}

def _flag_img(team: str, h: int = 14) -> str:
    code = _FLAG_CDN.get(team, "")
    if not code:
        return '<span style="display:inline-block;width:20px"></span>'
    url = f"https://flagcdn.com/w40/{code}.png"
    return (
        f'<img src="{url}" '
        f'style="height:{h}px;width:auto;border-radius:2px;'
        f'vertical-align:middle;flex-shrink:0;margin-right:1px" '
        f'onerror="this.style.display=\'none\'">'
    )


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class MatchInfo:
    match_number: int
    team1:   str
    flag1:   str
    team2:   str
    flag2:   str
    status:  str      # "Scheduled" | "Completed"
    day:     str
    time_str: str
    date_str: str
    venue:   str
    winner:  str = ""
    score1:  str = ""
    score2:  str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _parse_date(s: str) -> datetime | None:
    s = str(s).strip()
    try:
        return datetime.strptime(s, "%d/%m/%Y")
    except ValueError:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def _fmt_date(s: str) -> tuple[str, str]:
    d = _parse_date(s)
    if not d:
        return "—", "—"
    return DAY_ABBR[d.weekday()], f"{d.day} {d.strftime('%b').upper()}"


def _team_ref(raw: str, winner_of: dict, loser_of: dict) -> tuple[str, str]:
    """Resolve 'Winner match X' → real team name + flag, or placeholder label + '○'."""
    s = str(raw or "").strip()
    if not s or s in ("nan", "None"):
        return "TBD", "○"
    if s.startswith("Winner match "):
        mn = int(s.split()[-1])
        if mn in winner_of:
            t = winner_of[mn]
            return t, "🏳"
        if 73 <= mn <= 88:    label = f"W-32-{mn - 72}"
        elif 89 <= mn <= 96:  label = f"W-16-{mn - 88}"
        elif 97 <= mn <= 100: label = f"W-QF-{mn - 96}"
        else:                  label = f"W{mn}"
        return label, "○"
    if s.startswith("Runner-up match "):
        mn = int(s.split()[-1])
        if mn in loser_of:
            t = loser_of[mn]
            return t, "🏳"
        if 101 <= mn <= 102: label = f"L-SF-{mn - 100}"
        else:                 label = f"L{mn}"
        return label, "○"
    return s, "🏳"


def _build_matches(fixtures_df, results_df) -> dict[int, MatchInfo]:
    result_rows: dict[int, object] = {}
    for _, r in results_df.iterrows():
        try:
            mn = int(r["match_number"])
        except (ValueError, TypeError):
            continue
        if mn >= 73:
            result_rows[mn] = r

    winner_of: dict[int, str] = {}
    loser_of:  dict[int, str] = {}

    def _resolve(raw: str) -> str:
        """Resolve 'Winner match X' / 'Runner-up match X' using already-built dicts."""
        s = str(raw or "").strip()
        if s.startswith("Winner match "):
            try:
                return winner_of.get(int(s.split()[-1]), s)
            except ValueError:
                return s
        if s.startswith("Runner-up match "):
            try:
                return loser_of.get(int(s.split()[-1]), s)
            except ValueError:
                return s
        return s

    # Process in sorted order so R32 winners are known before R16 fixtures are read
    for mn in sorted(result_rows.keys()):
        r    = result_rows[mn]
        fix_r = fixtures_df[fixtures_df["match_number"] == mn]
        if fix_r.empty:
            continue
        fix  = fix_r.iloc[0]
        home = _resolve(str(fix["home_team"]))
        away = _resolve(str(fix["away_team"]))
        hg   = int(r["home_goals"])
        ag   = int(r["away_goals"])
        pw   = str(r.get("penalty_winner", "") or "").strip()
        pw   = None if pw in ("nan", "None", "") else pw
        if pw == "home" or (not pw and hg > ag):
            winner_of[mn], loser_of[mn] = home, away
        elif pw == "away" or (not pw and ag > hg):
            winner_of[mn], loser_of[mn] = away, home

    out: dict[int, MatchInfo] = {}
    for _, fix in fixtures_df.iterrows():
        try:
            mn = int(fix["match_number"])
        except (ValueError, TypeError):
            continue
        if mn < 73:
            continue

        team1, flag1 = _team_ref(_resolve(str(fix["home_team"])), winner_of, loser_of)
        team2, flag2 = _team_ref(_resolve(str(fix["away_team"])), winner_of, loser_of)
        day, date    = _fmt_date(str(fix.get("match_date", "")))
        time_        = str(fix.get("kickoff_time", "00:00"))[:5]
        venue        = str(fix.get("venue", "")).strip()
        if venue in ("nan", "None", ""):
            venue = "TBD"
        venue = (venue.replace(" Stadium", "")
                      .replace("New York New Jersey", "NY/NJ")
                      .replace("San Francisco Bay Area", "SF Bay Area")
                      .replace("BC Place Vancouver", "Vancouver"))

        status = "Completed" if mn in result_rows else "Scheduled"
        s1 = s2 = ""
        if mn in result_rows:
            r  = result_rows[mn]
            s1 = str(int(r["home_goals"]))
            s2 = str(int(r["away_goals"]))

        out[mn] = MatchInfo(
            match_number=mn, team1=team1, flag1=flag1,
            team2=team2, flag2=flag2, status=status,
            day=day, time_str=time_, date_str=date, venue=venue,
            winner=winner_of.get(mn, ""), score1=s1, score2=s2,
        )
    return out


# ── Match card renderer ───────────────────────────────────────────────────────
def _card_html(m: MatchInfo | None) -> str:
    if m is None:
        return (
            f'<div style="width:{CARD_W}px;height:{CARD_H}px;'
            f'background:#e5e7eb;border-radius:6px;opacity:0.3"></div>'
        )

    is_ph1    = m.flag1 == "○"
    is_ph2    = m.flag2 == "○"
    completed = m.status == "Completed"
    stat_col  = "#5aa34f" if not completed else "#94a3b8"

    owners1 = _owner_map.get(m.team1, [])
    owners2 = _owner_map.get(m.team2, [])
    tier1   = tier_map.get(m.team1, 0)
    tier2   = tier_map.get(m.team2, 0)
    tcol1   = TIER_COLORS.get(tier1, "#94a3b8") if not is_ph1 else "#d1d5db"
    tcol2   = TIER_COLORS.get(tier2, "#94a3b8") if not is_ph2 else "#d1d5db"

    def _row(name, is_ph, won, tier_col, tier_num, owners):
        if is_ph:
            return (
                f'<div style="border-left:4px solid #d1d5db;border-radius:0 4px 4px 0;'
                f'background:#f9fafb;padding:3px 6px;margin:2px 0">'
                f'<div style="display:flex;align-items:center;justify-content:space-between">'
                f'<div style="display:flex;align-items:center;gap:5px">'
                f'<span style="color:#d1d5db;font-size:11px;line-height:1">○</span>'
                f'<span style="color:#9ca3af;font-size:10.5px">{name}</span>'
                f'</div>'
                f'<span style="font-size:7.5px;color:#d1d5db;font-weight:700">?</span>'
                f'</div>'
                f'<div style="font-size:7px;color:#d1d5db;margin-top:1px">awaiting result</div>'
                f'</div>'
            )

        op  = "1" if (not completed or won) else "0.28"
        fw  = "700" if won else "600"
        nm  = (name[:22] + "…") if len(name) > 22 else name
        # tier background: colour at ~12% opacity (hex 1e ≈ 12%)
        bg  = f"{tier_col}1e"
        tier_badge = (
            f'<span style="background:{tier_col};color:#fff;font-size:8px;'
            f'font-weight:800;border-radius:3px;padding:1px 5px;'
            f'flex-shrink:0;letter-spacing:0.2px">T{tier_num}</span>'
        ) if tier_num else ""
        flag_html = _flag_img(name)
        owner_txt = " · ".join(owners) if owners else "—"
        return (
            f'<div style="border-left:4px solid {tier_col};border-radius:0 4px 4px 0;'
            f'background:{bg};padding:3px 6px;margin:2px 0;opacity:{op}">'
            # name row: flag | name | tier badge
            f'<div style="display:flex;align-items:center;'
            f'justify-content:space-between;gap:4px">'
            f'<div style="display:flex;align-items:center;gap:5px;min-width:0;flex:1">'
            f'{flag_html}'
            f'<span style="color:#111;font-weight:{fw};font-size:11px;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{nm}</span>'
            f'</div>'
            f'{tier_badge}'
            f'</div>'
            # owner row
            f'<div style="font-size:7.5px;color:#4f46e5;margin-top:2px;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'font-weight:500">{owner_txt}</div>'
            f'</div>'
        )

    if completed and m.score1 and m.score2:
        sep = (
            f'<div style="text-align:center;font-weight:700;font-size:11px;'
            f'color:#111;border-top:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb;'
            f'padding:1px 0;margin:1px 0">{m.score1} – {m.score2}</div>'
        )
    else:
        sep = '<div style="height:1px;background:#e5e7eb;margin:2px 0"></div>'

    venue_s = (m.venue[:30] + "…") if len(m.venue) > 30 else m.venue

    return (
        f'<div style="width:{CARD_W}px;height:{CARD_H}px;background:white;'
        f'border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,0.10);'
        f'padding:5px 7px;font-family:system-ui,-apple-system,sans-serif;'
        f'box-sizing:border-box;overflow:hidden">'
        # ── Header row: day · time · date (single line)
        f'<div style="text-align:center;font-size:10px;font-weight:600;'
        f'color:#374151;margin-bottom:4px;white-space:nowrap;letter-spacing:0.3px">'
        f'{m.day} · {m.time_str} · {m.date_str}</div>'
        # ── Team rows
        + _row(m.team1, is_ph1, m.winner == m.team1, tcol1, tier1, owners1)
        + sep
        + _row(m.team2, is_ph2, m.winner == m.team2, tcol2, tier2, owners2)
        # ── Venue (only for scheduled — score row already uses the space)
        + (
            f'<div style="color:#9ca3af;font-size:7px;margin-top:3px;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
            f'📍 {venue_s}</div>'
            if not completed else ""
        )
        + f'</div>'
    )


# ── Bracket HTML builder ──────────────────────────────────────────────────────
def _bracket_html(all_matches: dict[int, MatchInfo]) -> str:
    n_rounds = len(BRACKET_SLOTS)
    pad_top  = 28
    total_w  = n_rounds * COL_W + (n_rounds - 1) * CONN_W + 8

    parts = [
        f'<div style="overflow-x:auto;background:#f8f9fb;border-radius:10px;'
        f'padding:{pad_top + 8}px 16px 24px;font-family:system-ui,sans-serif">'
        f'<div style="position:relative;height:{TOTAL_H + pad_top}px;'
        f'width:{total_w}px;min-width:{total_w}px">'
    ]

    for ri, (round_label, mn_list) in enumerate(zip(ROUND_LABELS, BRACKET_SLOTS)):
        n       = len(mn_list)
        slot_h  = BASE * (2 ** ri)
        col_x   = ri * (COL_W + CONN_W)

        # Round label
        parts.append(
            f'<div style="position:absolute;top:0;left:{col_x}px;'
            f'width:{COL_W}px;text-align:center;color:#374151;font-size:11px;'
            f'font-weight:700;letter-spacing:0.3px;text-transform:uppercase">'
            f'{round_label}</div>'
        )

        for si, mn in enumerate(mn_list):
            m        = all_matches.get(mn)
            card_top = pad_top + si * slot_h + (slot_h - CARD_H) // 2

            parts.append(
                f'<div style="position:absolute;top:{card_top}px;left:{col_x}px">'
                + _card_html(m)
                + '</div>'
            )

            # Connector: drawn for even si (top of each pair)
            if ri < n_rounds - 1 and si % 2 == 0 and si + 1 < n:
                cy_top  = pad_top + si * slot_h + slot_h // 2
                cy_bot  = pad_top + (si + 1) * slot_h + slot_h // 2
                mid_y   = (cy_top + cy_bot) // 2

                arm_x   = col_x + CARD_W
                junc_x  = arm_x + CONN_W // 2
                reach_x = col_x + COL_W + CONN_W

                parts += [
                    # Top horizontal arm
                    f'<div style="position:absolute;top:{cy_top - 1}px;left:{arm_x}px;'
                    f'width:{junc_x - arm_x}px;height:2px;background:{LINE_CLR}"></div>',
                    # Bottom horizontal arm
                    f'<div style="position:absolute;top:{cy_bot - 1}px;left:{arm_x}px;'
                    f'width:{junc_x - arm_x}px;height:2px;background:{LINE_CLR}"></div>',
                    # Vertical joining line
                    f'<div style="position:absolute;top:{cy_top}px;left:{junc_x - 1}px;'
                    f'width:2px;height:{cy_bot - cy_top}px;background:{LINE_CLR}"></div>',
                    # Horizontal arm to next column
                    f'<div style="position:absolute;top:{mid_y - 1}px;left:{junc_x - 1}px;'
                    f'width:{reach_x - junc_x + 1}px;height:2px;background:{LINE_CLR}"></div>',
                ]

    parts.append('</div></div>')
    return ''.join(parts)


# ── 3rd Place card ────────────────────────────────────────────────────────────
def _third_place_html(all_matches: dict[int, MatchInfo]) -> str:
    m = all_matches.get(103)
    if not m:
        return ""
    return (
        f'<div style="background:#f8f9fb;border-radius:10px;'
        f'padding:12px 16px;font-family:system-ui,sans-serif">'
        f'<div style="color:#374151;font-size:11px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.3px;margin-bottom:8px">'
        f'3rd Place Playoff</div>'
        + _card_html(m)
        + '</div>'
    )


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_ko, tab_group = st.tabs(["Knockout Stage", "Group Stage Draw"])

# ══════════════════════════════════════════════════════════════════════════════
# KNOCKOUT STAGE
# ══════════════════════════════════════════════════════════════════════════════
with tab_ko:
    _group_done = (
        not match_stats.empty
        and (match_stats["RoundReached"] == "GroupStage").sum() >= 16
    )

    all_matches = _build_matches(fixtures_df, results_df)

    if not all_matches:
        empty_state("Fixture data not available.")
    elif not _group_done:
        st.info(
            "The knockout bracket will appear once the group stage is complete "
            "and all 32 qualifiers are known.",
            icon="🏟️",
        )
        # Still show R32 if fixtures are populated
        _r32_populated = any(
            not str(fixtures_df.loc[fixtures_df["match_number"] == mn, "home_team"].values[0]
                    if mn in fixtures_df["match_number"].values else "").startswith("Winner")
            for mn in range(73, 89)
        )
        if _r32_populated:
            st.markdown("**Round of 32 — known fixtures:**")
            st.markdown(_bracket_html(all_matches), unsafe_allow_html=True)
    else:
        st.markdown(_bracket_html(all_matches), unsafe_allow_html=True)

        # 3rd place
        _3p = _third_place_html(all_matches)
        if _3p:
            col_3p, _ = st.columns([1, 3])
            with col_3p:
                st.markdown(_3p, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# GROUP STAGE DRAW
# ══════════════════════════════════════════════════════════════════════════════
with tab_group:
    # Tier colour legend
    _leg = st.columns(4)
    for _i, (_tier, _label) in enumerate(TIER_LABELS.items()):
        _clr = TIER_COLORS.get(_tier, "#9CA3AF")
        with _leg[_i]:
            st.markdown(
                f'<span style="background:{_clr};color:#fff;border-radius:4px;'
                f'padding:3px 10px;font-size:0.75rem;font-weight:700">{_label}</span>',
                unsafe_allow_html=True,
            )
    st.markdown("---")

    ROUND_STATUS_LABELS = {
        "GroupStage": "Eliminated (Groups)",
        "R16": "Eliminated (R16)", "QF": "Eliminated (QF)",
        "SF": "Eliminated (SF)", "Final": "Runner-up", "Winner": "Champion",
    }

    def _team_card_gs(team: str, compact: bool = False) -> str:
        _tier  = tier_map.get(team, 1)
        _bg    = TIER_COLORS.get(_tier, "#1E2937")
        _owners = _owner_map.get(team, [])
        _owner_txt = "  ·  ".join(_owners) if _owners else "—"
        _pad = "0.3rem 0.6rem" if compact else "0.4rem 0.7rem"
        return (
            f'<div style="background:{_bg}22;border-left:4px solid {_bg};border-radius:4px;'
            f'padding:{_pad};margin-bottom:0.3rem">'
            f'<div style="color:#F1F5F9;font-weight:700;font-size:{"0.82rem" if compact else "0.9rem"}">'
            f'{team}</div>'
            f'<div style="color:#94A3B8;font-size:0.62rem;margin-top:1px">{_owner_txt}</div>'
            f'</div>'
        )

    def _elim_wrap(card_html: str) -> str:
        return (
            '<div style="position:relative;opacity:0.55">'
            + card_html
            + '<div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;'
            'align-items:center;justify-content:flex-end;padding-right:0.5rem;pointer-events:none">'
            '<span style="color:#EF4444;font-size:2rem;font-weight:900;line-height:1;opacity:0.9">✕</span>'
            '</div></div>'
        )

    if teams_df.empty:
        empty_state("No team data available.")
    else:
        _groups: dict[str, list] = {}
        for _, _row in teams_df.iterrows():
            _g = str(_row.get("Group", "")).strip()
            if _g and _g.lower() not in ("nan", ""):
                _groups.setdefault(_g, []).append(_row)

        if not _groups:
            empty_state("Group assignments not available yet.")
        else:
            _gl = sorted(_groups.keys())
            for _rs in range(0, len(_gl), 3):
                _cols = st.columns(3)
                for _ci, _g in enumerate(_gl[_rs:_rs + 3]):
                    with _cols[_ci]:
                        st.markdown(
                            f'<div style="color:#D4A017;font-weight:700;font-size:0.95rem;'
                            f'border-bottom:1px solid #2A3A4A;padding-bottom:0.2rem;'
                            f'margin-bottom:0.4rem">Group {_g}</div>',
                            unsafe_allow_html=True,
                        )
                        _team_rows = sorted(_groups[_g], key=lambda r: int(r.get("Tier", 4)))
                        for _tr in _team_rows:
                            _team = str(_tr["Team"])
                            _rnd = ""
                            if not match_stats.empty:
                                _ms = match_stats[match_stats["Team"] == _team]
                                if not _ms.empty:
                                    _rnd = str(_ms.iloc[0].get("RoundReached", "") or "").strip()
                            _card = _team_card_gs(_team, compact=True)
                            if _rnd == "GroupStage":
                                _card = _elim_wrap(_card)
                            st.markdown(_card, unsafe_allow_html=True)
