"""Player Portfolios — per-player deep-dive."""
import sys
from pathlib import Path
_p = str(Path(__file__).resolve().parent.parent.parent); sys.path.insert(0, _p) if _p not in sys.path else None

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from dashboard.data import (
    get_participants, get_assignments, get_match_stats, get_purchases,
    get_captains, get_predictions, get_statuses, get_tier_map,
    get_events, is_predictions_locked, get_goals_conceded_map, get_swap_offsets,
    get_eliminated_teams,
)
from dashboard.config import TIER_COLORS, PLOTLY_LAYOUT
from dashboard.components.ui import page_header, empty_state, tier_badge


page_header("Player Portfolios", "Per-player team breakdown and points")

participants = get_participants()
if not participants:
    empty_state("No participants yet.")
    st.stop()

# ── URL param: ?player=Name lets players bookmark their own page ───────────
url_player = st.query_params.get("player", "")
default_idx = participants.index(url_player) if url_player in participants else 0

player = st.selectbox("Select Player", participants, index=default_idx)
if not player:
    st.stop()

# Keep URL in sync so the current player is always bookmarkable
st.query_params["player"] = player

# Shareable link — derive the full URL from the request Host header
import urllib.parse as _urlparse
try:
    _host = st.context.headers.get("host", "localhost:8501")
except Exception:
    _host = "localhost:8501"
_share_url = f"http://{_host}/player_portfolios?player={_urlparse.quote(player)}"
with st.expander("📤 Share my portfolio link", expanded=False):
    st.markdown("Send this URL directly to your profile:")
    st.code(_share_url, language=None)

assignments  = get_assignments()
match_stats   = get_match_stats()
_elim_teams   = get_eliminated_teams()
_gc_map       = get_goals_conceded_map()
purchases    = get_purchases()
captains     = get_captains()
predictions  = get_predictions()
statuses     = get_statuses()
tier_map     = get_tier_map()
pred_locked  = is_predictions_locked()

from src.scoring_engine import (
    calculate_player_points, get_effective_teams, calculate_team_points,
)
from src.competition import purchases_to_scoring_format

scoring_purch = purchases_to_scoring_format(purchases)
swap_offsets  = get_swap_offsets()
eff   = get_effective_teams(player, assignments, scoring_purch)
result = calculate_player_points(
    player, assignments, match_stats, scoring_purch,
    captains, predictions, tier_map=tier_map, swap_offsets=swap_offsets,
)

# Payment status
status_val = "UNPAID"
if not statuses.empty and player in statuses["Player"].values:
    status_val = statuses.loc[statuses["Player"] == player, "Status"].iloc[0]

grand_total   = result.get("grand_total", 0.0)
base_total    = result.get("base_total", 0.0)
captain_info  = result.get("captain", {})
captain_bonus = captain_info.get("total", 0.0)
insurance_pts = result.get("insurance_bonus", 0.0)
special_bonus = result.get("special_bonus", 0.0)
pred_info     = result.get("predictions", {})
pred_total    = pred_info.get("total", 0.0)

# Compute group stage / knockout split from per-team points
_team_pts_all = result.get("team_points", {})
group_stage_pts = sum(v.get("group_stage", 0) for v in _team_pts_all.values())
knockout_pts    = sum(v.get("knockout", 0)     for v in _team_pts_all.values())

# ── Score strip ────────────────────────────────────────────────────────────
paid_icon = "✅" if status_val == "PAID" else "⚠️"
has_ins = not purchases.empty and not purchases[
    (purchases["Player"] == player) &
    (purchases["PurchaseType"] == "Insurance")
].empty

def _strip_box(label, value, color="#F5F5F5", prefix=""):
    return (
        f'<div style="background:#0D1B2A;border-radius:6px;padding:0.35rem 0.7rem;text-align:center">'
        f'<div style="color:#9CA3AF;font-size:0.68rem">{label}</div>'
        f'<div style="color:{color};font-weight:700;font-size:1.05rem">{prefix}{value:.0f}</div></div>'
    )

st.markdown(
    f'<div style="background:#1E2937;border:1px solid #2A3A4A;border-radius:10px;'
    f'padding:0.75rem 1rem;margin-bottom:0.75rem;display:flex;flex-wrap:wrap;gap:0.75rem;'
    f'align-items:center;justify-content:space-between">'
    f'<div><span style="color:#9CA3AF;font-size:0.75rem">TOTAL</span>'
    f'<div style="color:#D4A017;font-size:2rem;font-weight:800;line-height:1">{grand_total:.0f}</div></div>'
    f'<div style="display:flex;flex-wrap:wrap;gap:0.6rem">'
    + _strip_box("GROUP STAGE", group_stage_pts)
    + _strip_box("KNOCKOUT", knockout_pts)
    + _strip_box("CAPTAIN", captain_bonus, color="#6EE7B7", prefix="+")
    + _strip_box("PREDICTIONS", pred_total, color="#6EE7B7" if pred_total > 0 else "#9CA3AF", prefix="+")
    + f'</div>'
    f'<span style="color:#9CA3AF;font-size:0.82rem">{paid_icon} {status_val}</span>'
    f'</div>',
    unsafe_allow_html=True,
)
st.divider()

# Captain sets for this player
pre_cap_team = kn_cap_team = ""
if not captains.empty:
    pc = captains[(captains["Player"] == player) & (captains["CaptainType"] == "PreTournament")]
    kc = captains[(captains["Player"] == player) & (captains["CaptainType"] == "Knockout")]
    pre_cap_team = pc.iloc[0]["Team"] if not pc.empty else ""
    kn_cap_team  = kc.iloc[0]["Team"] if not kc.empty else ""

# Round Reached helper
ROUND_LABELS = {
    "GroupStage": "Eliminated (Groups)",
    "R32":        "Eliminated (Round of 32)",
    "R16":        "Round of 16",
    "QF":         "Quarter-Final",
    "SF":         "Semi-Final",
    "Final":      "Final",
    "Winner":     "Champion",
    "":           "Active",
}

def _round_reached(team: str) -> str:
    if match_stats.empty:
        return ""
    row = match_stats[match_stats["Team"] == team]
    if row.empty:
        return ""
    return str(row.iloc[0].get("RoundReached", "") or "")

def _is_eliminated(team: str) -> bool:
    return team in _elim_teams

_CHIP = (
    'background:{bg};color:{fg};font-size:0.65rem;border-radius:4px;'
    'padding:2px 5px;white-space:nowrap'
)
_GS_BG, _GS_FG   = "#253547", "#93C5FD"   # blue tint — group stage
_KO_BG, _KO_FG   = "#1A3325", "#6EE7B7"   # green tint — knockout
_PR_BG, _PR_FG   = "#2D1F3D", "#C4B5FD"   # purple — progression
_SP_BG, _SP_FG   = "#2D1A2A", "#F472B6"   # pink — special events

_ROUND_FULL = {
    "R32": "Round of 32", "R16": "Round of 16",
    "QF": "Quarter-final", "SF": "Semi-final",
    "Final": "Final", "Winner": "Winner",
}

def _pl(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"

def _breakdown_html(breakdown: dict) -> str:
    """Return an HTML string of coloured chips for the score breakdown."""
    gs_chips, ko_chips, prog_chips = [], [], []

    def chip(label, bg, fg):
        return f'<span style="{_CHIP.format(bg=bg, fg=fg)}">{label}</span>'

    GS_MAP = [
        ("GroupGoals",        1, "⚽", "goal"),
        ("GroupCleanSheets",  2, "🧤", "clean sheet"),
        ("GroupPenaltyWins",  3, "🎯", "penalty win"),
        ("GroupComebackWins", 3, "💪", "comeback win"),
    ]
    KO_MAP = [
        ("KnockoutGoals",        1, "⚽", "goal"),
        ("KnockoutCleanSheets",  2, "🧤", "clean sheet"),
        ("KnockoutPenaltyWins",  3, "🎯", "penalty win"),
        ("KnockoutComebackWins", 3, "💪", "comeback win"),
    ]

    for col, per, icon, word in GS_MAP:
        pts = breakdown.get(col, 0)
        if pts:
            count = int(pts // per)
            gs_chips.append(chip(f"{icon} {_pl(count, word)} +{pts:.0f}", _GS_BG, _GS_FG))

    if breakdown.get("GroupWinner"):
        gs_chips.append(chip("🏆 Group winner +3", _GS_BG, _GS_FG))

    for col, per, icon, word in KO_MAP:
        pts = breakdown.get(col, 0)
        if pts:
            count = int(pts // per)
            ko_chips.append(chip(f"{icon} {_pl(count, word)} +{pts:.0f}", _KO_BG, _KO_FG))

    for key, pts in breakdown.items():
        if key.startswith("Progression_") and pts:
            rnd = key.replace("Progression_", "")
            rnd_label = _ROUND_FULL.get(rnd, rnd)
            prog_chips.append(chip(f"📈 Reached {rnd_label} +{pts:.0f}", _PR_BG, _PR_FG))

    # Upset win chips
    tier_desc = {1: "1 tier higher", 2: "2 tiers higher", 3: "3 tiers higher"}
    upset_pts = {1: 15, 2: 30, 3: 50}
    for diff in [1, 2, 3]:
        for stage in ["Group", "Knockout"]:
            col = f"{stage}UpsetWins{diff}"
            pts = breakdown.get(col, 0)
            if pts:
                count = int(pts // upset_pts[diff])
                ko_chips.append(chip(
                    f"⚡ {_pl(count, 'upset win')} ({tier_desc[diff]}) +{pts:.0f}",
                    _KO_BG, _KO_FG,
                ))

    sp_chips = []
    for key, label, icon in [
        ("ShirtRemovals",   "shirt removal",       "👕"),
        ("GKGoals",         "goalkeeper goal",      "🥅"),
        ("RedCards",        "red card",             "🟥"),
        ("FirstEliminated", "first team eliminated","💀"),
    ]:
        pts = breakdown.get(key, 0)
        if pts:
            sp_chips.append(chip(f"{icon} {label} {pts:+.0f}", _SP_BG, _SP_FG))

    all_chips = gs_chips + ko_chips + prog_chips + sp_chips
    if not all_chips:
        return ""
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:0.3rem">'
        + "".join(all_chips)
        + "</div>"
    )

# ── Two-column layout ──────────────────────────────────────────────────────
col_teams, col_extras = st.columns([3, 2], gap="large")

with col_teams:
    st.subheader("Teams & Points")

    all_teams    = list(dict.fromkeys(eff["group_stage"] + eff["knockout"]))
    hist_teams   = result.get("historical_teams", [])
    stored_team_pts = result.get("team_points", {})

    def _team_card(team: str, is_historical: bool = False) -> None:
        tier  = tier_map.get(team, 1)
        rnd   = _round_reached(team)
        in_gs = team in eff["group_stage"]
        in_ko = team in eff["knockout"]
        tp    = stored_team_pts.get(team) or (
            calculate_team_points(team, match_stats, tier) if not match_stats.empty
            else {"group_stage": 0, "knockout": 0, "total": 0}
        )
        gs_pts    = tp.get("group_stage", 0)
        ko_pts    = tp.get("knockout", 0)
        sp_pts    = tp.get("special", 0)
        total_pts = tp.get("total", 0)
        eliminated = _is_eliminated(team)

        is_pre_cap = team == pre_cap_team
        is_ko_cap  = team == kn_cap_team
        cap_bonus, cap_tag = 0.0, ""
        if is_pre_cap:
            cap_bonus += captain_info.get("pre_tournament_bonus", 0)
            cap_tag = "★ Pre"
        if is_ko_cap:
            cap_bonus += captain_info.get("knockout_bonus", 0)
            cap_tag = (cap_tag + " + KO").lstrip(" + ") if cap_tag else "★ KO"

        tier_col   = TIER_COLORS.get(tier, "#9CA3AF")
        status_txt = ROUND_LABELS.get(rnd, "🟢 Active")
        text_alpha = "0.5" if (eliminated and not is_historical) else "1"
        bg_color   = "#17202A" if is_historical else "#1E2937"
        cap_html   = (
            f'<span style="color:#D4A017;font-size:0.68rem;font-weight:700;'
            f'background:rgba(212,160,23,0.15);border-radius:4px;padding:1px 5px">{cap_tag}</span>'
            if cap_tag else ""
        )
        bonus_html = (
            f'<span style="color:#6EE7B7;font-size:0.75rem;font-weight:600"> +{cap_bonus:.0f} cap</span>'
            if cap_bonus > 0 else ""
        )
        if is_historical:
            stage_label = f"Now: {status_txt}"
            pts_label   = "pts earned"
        elif eliminated:
            stage_label = status_txt
            pts_label   = "pts"
        else:
            stage_label = ("Group + KO" if in_gs and in_ko else "KO only" if in_ko else "Group")
            pts_label   = "pts"
        bd_html = _breakdown_html(tp.get("breakdown", {})) if not is_historical else ""
        ga = _gc_map.get(team, None)
        ga_html = (
            f'<span style="color:#F87171;font-size:0.65rem;background:#3A1515;border-radius:3px;'
            f'padding:1px 4px;margin-left:0.3rem">GA:{ga}</span>'
            if ga is not None and not is_historical else ""
        )

        st.markdown(
            f'<div style="background:{bg_color};border-left:3px solid {tier_col};border-radius:0 6px 6px 0;'
            f'padding:0.45rem 0.7rem;margin-bottom:0.35rem;opacity:{text_alpha}">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.3rem">'
            f'<div>'
            f'<span style="color:{tier_col};font-size:0.65rem;font-weight:700;background:{tier_col}22;'
            f'border-radius:3px;padding:0 4px;margin-right:0.3rem">T{tier}</span>'
            f'<span style="color:#F5F5F5;font-weight:600;font-size:0.9rem">{team}</span>'
            f'{ga_html} {cap_html}'
            f'<div style="color:#9CA3AF;font-size:0.7rem;margin-top:0.1rem">{stage_label}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="color:#F5F5F5;font-weight:700;font-size:1.0rem">{total_pts:.0f} {pts_label}</div>'
            f'<div style="color:#9CA3AF;font-size:0.7rem">Group {gs_pts:.0f} · Knockout {ko_pts:.0f}'
            f'{"· Special " + f"{sp_pts:+.0f}" if sp_pts else ""}{bonus_html}</div>'
            f'</div>'
            f'</div>'
            f'{bd_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if hist_teams:
        sub_curr, sub_hist = st.columns(2, gap="medium")
        with sub_curr:
            st.markdown(
                '<div style="color:#6EE7B7;font-size:0.78rem;font-weight:700;margin-bottom:0.4rem">'
                '↔ Current Teams</div>', unsafe_allow_html=True
            )
            for team in all_teams:
                _team_card(team)
        with sub_hist:
            st.markdown(
                '<div style="color:#9CA3AF;font-size:0.78rem;font-weight:700;margin-bottom:0.4rem">'
                '↩ Previous Teams (swapped away)</div>', unsafe_allow_html=True
            )
            for team in hist_teams:
                _team_card(team, is_historical=True)
    else:
        for team in all_teams:
            _team_card(team)

    # Bar chart — current teams only
    _chart_pts = [stored_team_pts.get(t, {}).get("total", 0) for t in all_teams]
    if hist_teams:
        _chart_pts_hist = [stored_team_pts.get(t, {}).get("total", 0) for t in hist_teams]
        _all_chart_teams = all_teams + hist_teams
        _all_chart_pts   = _chart_pts + _chart_pts_hist
        _all_chart_cols  = (
            [TIER_COLORS.get(tier_map.get(t, 1), "#9CA3AF") for t in all_teams]
            + ["#4B5563"] * len(hist_teams)
        )
    else:
        _all_chart_teams, _all_chart_pts, _all_chart_cols = (
            all_teams, _chart_pts,
            [TIER_COLORS.get(tier_map.get(t, 1), "#9CA3AF") for t in all_teams],
        )
    if any(p > 0 for p in _all_chart_pts):
        st.markdown("---")
        fig = go.Figure(go.Bar(
            x=_all_chart_teams,
            y=_all_chart_pts,
            marker_color=_all_chart_cols,
            hovertemplate="%{x}: %{y:.0f} pts<extra></extra>",
        ))
        _bar_layout = {**PLOTLY_LAYOUT}
        _bar_layout.update(
            title="Points by Team" + (" (grey = previous)" if hist_teams else ""),
            height=240, margin=dict(l=5, r=5, t=35, b=5),
        )
        fig.update_layout(**_bar_layout)
        st.plotly_chart(fig, use_container_width=True)

with col_extras:

    def _sel(ptype):
        if purchases.empty:
            return "—"
        rows = purchases[
            (purchases["Player"] == player) &
            (purchases["PurchaseType"] == ptype)
        ]
        return rows.iloc[0].get("Selection", "—") if not rows.empty else "—"

    # ── Captain Breakdown ──────────────────────────────────────────────────
    st.subheader("🎖️ Captain Bonus")
    pre_team = captain_info.get("pre_tournament_captain") or "—"
    pre_bonus = captain_info.get("pre_tournament_bonus", 0.0)
    ko_team   = captain_info.get("knockout_captain") or "—"
    ko_bonus  = captain_info.get("knockout_bonus", 0.0)
    pre_pts   = stored_team_pts.get(pre_team, {}).get("total", 0) if pre_team != "—" else 0
    ko_ko_pts = stored_team_pts.get(ko_team, {}).get("knockout", 0) if ko_team != "—" else 0

    for cap_type, team_name, base_pts, bonus_pts, note in [
        ("Pre-Tournament", pre_team, pre_pts, pre_bonus, "50% of team's total pts"),
        ("Knockout",       ko_team,  ko_ko_pts, ko_bonus,  "50% of team's KO pts only"),
    ]:
        bonus_col = "#6EE7B7" if bonus_pts > 0 else "#9CA3AF"
        st.markdown(
            f'<div class="card" style="margin-bottom:0.4rem">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
            f'<div><div style="color:#9CA3AF;font-size:0.72rem">{cap_type} Captain</div>'
            f'<div style="color:#F5F5F5;font-weight:700;font-size:0.95rem">{team_name}</div>'
            f'<div style="color:#9CA3AF;font-size:0.7rem">{base_pts:.0f} pts × 0.5 — {note}</div></div>'
            f'<div style="color:{bonus_col};font-weight:700;font-size:1.1rem">+{bonus_pts:.1f}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Ninth Team ────────────────────────────────────────────────────────
    st.subheader("9️⃣ Ninth Team")
    # KO-only teams (not in group stage roster) = ninth team / resurrection
    extra_ko_teams = [t for t in eff["knockout"] if t not in eff["group_stage"]]
    # Also check purchases Selection for explicitly-recorded ninth team
    _ninth_sel = _sel("NinthTeam")
    if _ninth_sel and _ninth_sel != "—" and _ninth_sel not in extra_ko_teams:
        extra_ko_teams = [_ninth_sel] + extra_ko_teams

    if extra_ko_teams:
        for _nt in extra_ko_teams:
            _nt_tier    = tier_map.get(_nt, 1)
            _nt_col     = TIER_COLORS.get(_nt_tier, "#9CA3AF")
            _nt_tp      = stored_team_pts.get(_nt, {})
            _nt_ko_pts  = _nt_tp.get("knockout", 0)
            _nt_gs_pts  = _nt_tp.get("group_stage", 0)
            _nt_total   = _nt_tp.get("total", 0)
            _nt_rnd     = _round_reached(_nt)
            _nt_status  = ROUND_LABELS.get(_nt_rnd, "🟢 Active")
            _nt_elim    = _is_eliminated(_nt)
            _nt_op      = "0.5" if _nt_elim else "1"
            st.markdown(
                f'<div style="background:#1E2937;border-left:4px solid {_nt_col};border-radius:0 6px 6px 0;'
                f'padding:0.5rem 0.75rem;margin-bottom:0.3rem;opacity:{_nt_op}">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                f'<div>'
                f'<span style="color:{_nt_col};font-size:0.65rem;font-weight:700;background:{_nt_col}22;'
                f'border-radius:3px;padding:0 4px;margin-right:0.3rem">T{_nt_tier}</span>'
                f'<span style="color:#F5F5F5;font-weight:700;font-size:0.95rem">{_nt}</span>'
                f'<div style="color:#9CA3AF;font-size:0.7rem;margin-top:0.1rem">KO only · {_nt_status}</div>'
                f'</div>'
                f'<div style="text-align:right">'
                f'<div style="color:#D4A017;font-weight:700;font-size:1.1rem">{_nt_total:.0f} pts</div>'
                f'<div style="color:#9CA3AF;font-size:0.7rem">Grp {_nt_gs_pts:.0f} · KO {_nt_ko_pts:.0f}</div>'
                f'</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="card" style="display:flex;justify-content:space-between;align-items:center">'
            '<span style="color:#9CA3AF">No ninth team purchased</span>'
            '<span style="color:#6B7280;font-size:0.75rem">€3 — adds a KO-only team</span></div>',
            unsafe_allow_html=True,
        )

    # ── Special Events ────────────────────────────────────────────────────
    if special_bonus != 0:
        st.divider()
        st.subheader("✨ Special Events")
        _sp_map = [
            ("ShirtRemovals",  "Shirt Removals",        "+25 each",  25,  False),
            ("GKGoals",        "Goalkeeper Goals",       "+75 each",  75,  False),
            ("RedCards",       "Red Cards",              "-5 each",   -5,  True),
            ("FirstEliminated","First Team Eliminated",  "+35",       35,  False),
        ]
        for _col, _label, _note, _per, _negative in _sp_map:
            if match_stats.empty:
                continue
            _totals = 0
            for _team in eff["group_stage"] + [t for t in eff["knockout"] if t not in eff["group_stage"]]:
                _row = match_stats[match_stats["Team"] == _team]
                if not _row.empty:
                    _v = int(float(_row.iloc[0].get(_col, 0) or 0))
                    _totals += _v
            if _totals == 0:
                continue
            _earned = _totals * _per
            _c = "#F87171" if _negative else "#6EE7B7"
            st.markdown(
                f'<div class="card" style="margin-bottom:0.35rem;display:flex;'
                f'justify-content:space-between;align-items:center">'
                f'<div><div style="color:#F5F5F5;font-weight:600;font-size:0.88rem">{_label}</div>'
                f'<div style="color:#9CA3AF;font-size:0.7rem">{_totals}× · {_note}</div></div>'
                f'<div style="color:{_c};font-weight:700;font-size:1.05rem">{_earned:+.0f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        sp_col = "#6EE7B7" if special_bonus > 0 else "#F87171"
        st.markdown(
            f'<div class="card-gold" style="display:flex;justify-content:space-between">'
            f'<span style="color:#D4A017;font-size:0.85rem">Total Special Bonus</span>'
            f'<span style="color:{sp_col};font-weight:700;font-size:1.1rem">{special_bonus:+.0f}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Predictions Breakdown ──────────────────────────────────────────────
    st.subheader("🔮 Predictions")
    if not pred_locked:
        st.markdown('<div class="card"><span style="color:#9CA3AF">🔒 Hidden until prediction lock</span></div>', unsafe_allow_html=True)
    else:
        if not predictions.empty and player in predictions["Player"].values:
            pred_row  = predictions[predictions["Player"] == player].iloc[0]
            pp_winner = str(pred_row.get("WorldCupWinner", "") or "").strip() or "—"
            pp_ru     = str(pred_row.get("RunnerUp",       "") or "").strip() or "—"
            pp_bronze = str(pred_row.get("BronzeMedal",    "") or "").strip() or "—"
            pp_golden = str(pred_row.get("GoldenBoot",     "") or "").strip() or "—"
            pp_dark   = str(pred_row.get("DarkHorse",      "") or "").strip() or "—"
        else:
            pp_winner = pp_ru = pp_bronze = pp_golden = pp_dark = "—"

        winner_bonus = pred_info.get("winner_bonus", 0.0)
        ru_bonus     = pred_info.get("runner_up_bonus", 0.0)
        bz_bonus     = pred_info.get("bronze_bonus", 0.0)
        gb_bonus     = pred_info.get("golden_boot_bonus", 0.0)
        dh_bonus     = pred_info.get("dark_horse_bonus", 0.0)

        # Dark horse current round
        dh_rnd = ""
        if pp_dark != "—" and not match_stats.empty:
            dh_rnd = _round_reached(pp_dark)

        DARK_HORSE_NEXT = {"": "QF (+15)", "QF": "SF (+30)", "SF": "Final (+40)", "Final": "Win (+50)"}

        # Fixed predictions (winner, runner-up, bronze, golden boot)
        for label, pick, earned, max_pts in [
            ("World Cup Winner", pp_winner, winner_bonus, 30),
            ("Runner-Up",        pp_ru,     ru_bonus,     20),
            ("Bronze Medal",     pp_bronze, bz_bonus,     15),
            ("Golden Boot",      pp_golden, gb_bonus,     25),
        ]:
            col_pts = "#6EE7B7" if earned > 0 else "#9CA3AF"
            status  = f"+{earned:.0f} ✓" if earned > 0 else f"0 / {max_pts}"
            st.markdown(
                f'<div class="card" style="margin-bottom:0.3rem">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<div><div style="color:#9CA3AF;font-size:0.7rem">{label}</div>'
                f'<div style="color:#F5F5F5;font-weight:600;font-size:0.88rem">{pick}</div></div>'
                f'<div style="color:{col_pts};font-weight:700;font-size:1.0rem">{status}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        # Dark horse with progressive milestone bars
        dh_next = DARK_HORSE_NEXT.get(dh_rnd, "") if dh_rnd in DARK_HORSE_NEXT else ""
        dh_status_txt = ROUND_LABELS.get(dh_rnd, "Active") if dh_rnd else "Group Stage / Not yet reached"
        dh_col = "#6EE7B7" if dh_bonus > 0 else "#9CA3AF"
        st.markdown(
            f'<div class="card" style="margin-bottom:0.3rem">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
            f'<div><div style="color:#9CA3AF;font-size:0.7rem">Dark Horse</div>'
            f'<div style="color:#F5F5F5;font-weight:600;font-size:0.88rem">{pp_dark}</div>'
            f'<div style="color:#9CA3AF;font-size:0.7rem">{dh_status_txt}</div>'
            f'{"<div style=color:#D4A017;font-size:0.7rem>Next: " + dh_next + "</div>" if dh_next else ""}'
            f'</div>'
            f'<div style="color:{dh_col};font-weight:700;font-size:1.0rem">+{dh_bonus:.0f}</div>'
            f'</div>'
            f'<div style="display:flex;gap:0.3rem;margin-top:0.4rem;flex-wrap:wrap">'
            + "".join(
                f'<span style="background:{"rgba(110,231,183,0.15)" if b <= dh_bonus else "#1E2937"};'
                f'color:{"#6EE7B7" if b <= dh_bonus else "#4B5563"};'
                f'font-size:0.65rem;border-radius:4px;padding:2px 6px">{rnd} +{b:.0f}</span>'
                for rnd, b in [("QF", 15), ("SF", 45), ("Final", 85), ("Win", 135)]
            ) +
            f'</div></div>',
            unsafe_allow_html=True,
        )

        total_pred_col = "#6EE7B7" if pred_total > 0 else "#9CA3AF"
        st.markdown(
            f'<div class="card-gold" style="display:flex;justify-content:space-between">'
            f'<span style="color:#D4A017;font-size:0.85rem">Total Prediction Bonus</span>'
            f'<span style="color:{total_pred_col};font-weight:700;font-size:1.1rem">+{pred_total:.0f}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── Mulligan History ───────────────────────────────────────────────────────
_mulligan_path = Path(__file__).resolve().parent.parent.parent / "data" / "mulligan_results.csv"
if _mulligan_path.exists():
    _mul_df = pd.read_csv(_mulligan_path, dtype=str).fillna("")
    _player_mulligans = _mul_df[_mul_df["Player"] == player]
    if not _player_mulligans.empty:
        st.divider()
        st.subheader("🎲 Mulligan Draw History")
        for _, _mr in _player_mulligans.iterrows():
            _prev = [t.strip() for t in str(_mr.get("PreviousTeams", "")).split("|") if t.strip()]
            _new  = [t.strip() for t in str(_mr.get("NewTeams", "")).split("|") if t.strip()]
            _removed = [t for t in _prev if t not in _new]
            _added   = [t for t in _new  if t not in _prev]
            st.markdown(
                '<div class="card" style="padding:0.6rem 0.75rem">'
                '<div style="color:#9CA3AF;font-size:0.72rem;margin-bottom:0.4rem">ORIGINAL TEAMS REPLACED</div>'
                + "".join(
                    f'<span style="background:#7f1d1d;color:#fca5a5;padding:0.15rem 0.5rem;'
                    f'border-radius:4px;font-size:0.82rem;margin:0.15rem;display:inline-block">{t}</span>'
                    for t in _removed
                )
                + '<div style="color:#9CA3AF;font-size:0.72rem;margin:0.4rem 0 0.2rem">NEW TEAMS RECEIVED</div>'
                + "".join(
                    f'<span style="background:#14532d;color:#86efac;padding:0.15rem 0.5rem;'
                    f'border-radius:4px;font-size:0.82rem;margin:0.15rem;display:inline-block">{t}</span>'
                    for t in _added
                )
                + "</div>",
                unsafe_allow_html=True,
            )

# ── Head-to-Head Comparison ────────────────────────────────────────────────
st.divider()
st.subheader("⚔️ Head-to-Head Comparison")

other_players = [p for p in participants if p != player]
h2h_opponent  = st.selectbox("Compare against", other_players, key="h2h_opponent") if other_players else None

if h2h_opponent:
    h2h_result = calculate_player_points(
        h2h_opponent, assignments, match_stats, scoring_purch,
        captains, predictions, tier_map=tier_map, swap_offsets=swap_offsets,
    )
    h2h_eff        = get_effective_teams(h2h_opponent, assignments, scoring_purch)
    h2h_teams      = list(dict.fromkeys(h2h_eff["group_stage"] + h2h_eff["knockout"]))
    h2h_team_pts   = h2h_result.get("team_points", {})
    h2h_grand      = h2h_result.get("grand_total", 0.0)
    h2h_cap_info   = h2h_result.get("captain", {})
    h2h_ins        = h2h_result.get("insurance_bonus", 0.0)
    h2h_spec       = h2h_result.get("special_bonus", 0.0)
    h2h_pred       = h2h_result.get("predictions", {}).get("total", 0.0)

    my_teams   = set(dict.fromkeys(eff["group_stage"] + eff["knockout"]))
    opp_teams  = set(h2h_teams)
    shared     = my_teams & opp_teams

    # Score banner
    my_col   = "#6EE7B7" if grand_total >= h2h_grand else "#9CA3AF"
    opp_col  = "#6EE7B7" if h2h_grand > grand_total  else "#9CA3AF"
    st.markdown(
        f'<div style="background:#1E2937;border-radius:10px;padding:0.75rem 1rem;'
        f'display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">'
        f'<div style="text-align:center">'
        f'<div style="color:#9CA3AF;font-size:0.72rem">{player}</div>'
        f'<div style="color:{my_col};font-size:2rem;font-weight:800">{grand_total:.0f}</div></div>'
        f'<div style="color:#9CA3AF;font-size:1.1rem">vs</div>'
        f'<div style="text-align:center">'
        f'<div style="color:#9CA3AF;font-size:0.72rem">{h2h_opponent}</div>'
        f'<div style="color:{opp_col};font-size:2rem;font-weight:800">{h2h_grand:.0f}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Stat comparison rows
    def _h2h_row(label, my_val, opp_val, fmt=".0f"):
        my_str  = f"{my_val:{fmt}}"
        opp_str = f"{opp_val:{fmt}}"
        my_c    = "#6EE7B7" if my_val > opp_val else ("#9CA3AF" if my_val == opp_val else "#F87171")
        opp_c   = "#6EE7B7" if opp_val > my_val else ("#9CA3AF" if my_val == opp_val else "#F87171")
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:0.2rem 0;border-bottom:1px solid #2A3A4A">'
            f'<span style="color:{my_c};font-weight:700;font-size:0.9rem">{my_str}</span>'
            f'<span style="color:#9CA3AF;font-size:0.78rem">{label}</span>'
            f'<span style="color:{opp_c};font-weight:700;font-size:0.9rem">{opp_str}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    _h2h_row("Team Points",    base_total,    h2h_result.get("base_total", 0))
    _h2h_row("Captain Bonus",  captain_bonus, h2h_cap_info.get("total", 0), fmt=".1f")
    _h2h_row("Special Events", special_bonus, h2h_spec)
    _h2h_row("Insurance",      insurance_pts, h2h_ins)
    _h2h_row("Predictions",    pred_total,    h2h_pred)
    _h2h_row("Total",          grand_total,   h2h_grand)

    if shared:
        st.markdown(
            f'<div style="margin-top:0.5rem;color:#9CA3AF;font-size:0.78rem">'
            f'Shared teams ({len(shared)}): {", ".join(sorted(shared))}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("No teams in common.")
