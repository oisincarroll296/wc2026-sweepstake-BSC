"""Tournament News — AI-generated newspaper-style narrative."""
import sys
import json
import re
import hashlib
import urllib.parse
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

from dashboard.data import (
    get_overall_leaderboard, get_assignments, get_match_stats,
    get_tier_map, get_captains, get_prize_pool,
    get_ko_winner_of, _resolve_ko_placeholder,
)
from dashboard.components.ui import page_header

_ROOT               = Path(__file__).parent.parent.parent
_FIXTURES_PATH      = _ROOT / "data" / "fixtures.csv"
_RESULTS_PATH       = _ROOT / "data" / "match_results.csv"
_PLAYERS_PATH       = _ROOT / "data" / "players.csv"
_SCORE_HISTORY_PATH = _ROOT / "data" / "score_history.csv"
_CACHE_PATH         = _ROOT / "data" / "story_cache.json"

_UPSET_BONUS = {1: 15, 2: 30, 3: 50}

# ── Palette ───────────────────────────────────────────────────────────────────
_BG     = "#F5F0E8"   # aged newsprint cream
_INK    = "#1A1008"
_RED    = "#8B0000"
_BORDER = "#1A1008"
_MID    = "#5C4033"
_LIGHT  = "#9E8B7A"
_GOLD   = "#D4A017"

# ── Flag CDN ──────────────────────────────────────────────────────────────────
_FLAG: dict[str, str] = {
    "Argentina":"ar","Australia":"au","Austria":"at","Belgium":"be",
    "Bosnia and Herzegovina":"ba","Brazil":"br","Canada":"ca","Cabo Verde":"cv",
    "Colombia":"co","Congo DR":"cd","Croatia":"hr","Curacao":"cw","Czechia":"cz",
    "Ecuador":"ec","Egypt":"eg","England":"gb-eng","France":"fr","Germany":"de",
    "Ghana":"gh","Haiti":"ht","IR Iran":"ir","Iraq":"iq","Japan":"jp","Jordan":"jo",
    "Korea Republic":"kr","Mexico":"mx","Morocco":"ma","Netherlands":"nl",
    "New Zealand":"nz","Norway":"no","Panama":"pa","Paraguay":"py","Portugal":"pt",
    "Qatar":"qa","Saudi Arabia":"sa","Scotland":"gb-sct","Senegal":"sn",
    "South Africa":"za","Spain":"es","Sweden":"se","Switzerland":"ch",
    "Cote d Ivoire":"ci","Tunisia":"tn","Tuerkiye":"tr","Uruguay":"uy",
    "USA":"us","Uzbekistan":"uz","Algeria":"dz",
}

def _flag_url(team: str, w: int = 40) -> str:
    c = _FLAG.get(team, "")
    return f"https://flagcdn.com/w{w}/{c}.png" if c else ""

def _flag_img(team: str, h: int = 20) -> str:
    u = _flag_url(team, 40)
    if not u:
        return f'<span style="font-size:{h}px;vertical-align:middle;margin-right:5px">🏴</span>'
    return (f'<img src="{u}" style="height:{h}px;border-radius:2px;vertical-align:middle;margin-right:5px"'
            f' title="{team}" onerror="this.style.display=\'none\'">')

# ── AI image generation via Pollinations.ai (free, no API key) ────────────────

def _ai_img_url(prompt: str, w: int = 400, h: int = 500) -> str:
    """Generate a deterministic AI image URL from Pollinations.ai."""
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % 99999
    enc  = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{enc}?width={w}&height={h}&nologo=true&seed={seed}&model=flux"

def _player_art_url(name: str, team: str, context: str = "") -> str:
    parts = [f"{name}", f"{team} national football team", "portrait", "dramatic stadium lighting", "photorealistic"]
    if context:
        parts.append(context)
    return _ai_img_url(" ".join(parts))


# ── Cache ─────────────────────────────────────────────────────────────────────

def _load_cache() -> dict | None:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_cache(data: dict) -> None:
    _CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Best day table ─────────────────────────────────────────────────────────────

def _build_best_day_table() -> list[dict]:
    if not _SCORE_HISTORY_PATH.exists():
        return []
    hist = pd.read_csv(_SCORE_HISTORY_PATH, dtype=str)
    if hist.empty or "Date" not in hist.columns:
        return []
    # Filter to players that belong to THIS competition only
    if _PLAYERS_PATH.exists():
        current = set(pd.read_csv(_PLAYERS_PATH, dtype=str)["Player"].dropna().tolist())
        hist = hist[hist["Player"].isin(current)]
    if hist.empty:
        return []
    hist["Date"]   = pd.to_datetime(hist["Date"], errors="coerce")
    hist["Points"] = pd.to_numeric(hist["Points"], errors="coerce").fillna(0)
    hist = hist.sort_values(["Player", "Date"])
    hist["prev"] = hist.groupby("Player")["Points"].shift(1)
    hist["gain"] = (hist["Points"] - hist["prev"]).fillna(0)
    best = hist[hist["gain"] > 0].nlargest(10, "gain")
    return [
        {"player": str(r["Player"]), "date": r["Date"].strftime("%d %b"), "gain": round(float(r["gain"]), 1)}
        for _, r in best.iterrows()
    ]


# ── Context builder ────────────────────────────────────────────────────────────

def _build_story_context(date_from: date | None = None, date_to: date | None = None) -> dict:
    fixtures = pd.read_csv(_FIXTURES_PATH, dtype=str)
    fixtures["match_number"] = pd.to_numeric(fixtures["match_number"], errors="coerce")
    fixtures["_date"] = pd.to_datetime(fixtures["match_date"], format="%d/%m/%Y", errors="coerce").dt.date

    # fixtures.csv stores KO rounds as "Winner match X" placeholders; resolve
    # to the real team name wherever that match has been played, so later
    # rounds don't narrate "Winner match 95 beat Winner match 96".
    _winner_of_story = get_ko_winner_of()
    fixtures["home_team"] = fixtures["home_team"].apply(
        lambda s: _resolve_ko_placeholder(s, _winner_of_story))
    fixtures["away_team"] = fixtures["away_team"].apply(
        lambda s: _resolve_ko_placeholder(s, _winner_of_story))

    results = pd.read_csv(_RESULTS_PATH, dtype=str)
    for col in ["match_number","home_goals","away_goals","extra_time",
                "comeback_home","comeback_away","home_hat_tricks","away_hat_tricks",
                "home_red_cards","away_red_cards","home_shirt_off","away_shirt_off",
                "home_gk_goals","away_gk_goals","home_first_eliminated","away_first_eliminated"]:
        if col in results.columns:
            results[col] = pd.to_numeric(results[col], errors="coerce").fillna(0).astype(int)

    stats       = get_match_stats()
    tier_map    = get_tier_map()
    assignments = get_assignments()
    lb          = get_overall_leaderboard()
    captains_df = get_captains()
    players_df  = pd.read_csv(_PLAYERS_PATH, dtype=str).fillna("") if _PLAYERS_PATH.exists() else pd.DataFrame()

    try:
        prize_info = get_prize_pool()
        prize_pool = prize_info.get("current_pot", prize_info.get("total", 0))
    except Exception:
        prize_pool = 0

    ownership: dict[str, list[str]] = {}
    for player, teams in assignments.items():
        for team in teams:
            ownership.setdefault(team, []).append(player)

    pre_captains: dict[str, str] = {}
    if not captains_df.empty and "Player" in captains_df.columns:
        for _, row in captains_df.iterrows():
            p, ptc = str(row.get("Player","")), str(row.get("PreTournamentCaptain","") or "")
            if ptc and ptc not in ("nan",""):
                pre_captains[p] = ptc

    predictions: dict[str, dict] = {}
    pay_status: dict[str, str] = {}
    if not players_df.empty:
        pcols = ["WorldCupWinner","RunnerUp","BronzeMedal","GoldenBoot","DarkHorse"]
        for _, row in players_df.iterrows():
            p = str(row.get("Player",""))
            pay_status[p] = str(row.get("Status","UNPAID"))
            preds = {c: str(row.get(c,"") or "") for c in pcols
                     if str(row.get(c,"") or "") not in ("","nan")}
            if preds:
                predictions[p] = preds

    all_played = pd.merge(results, fixtures, on="match_number", how="inner").sort_values("match_number")
    played = all_played.copy()
    if date_from:
        played = played[played["_date"] >= date_from]
    if date_to:
        played = played[played["_date"] <= date_to]

    match_narratives, upsets, hat_tricks, special_events = [], [], [], []
    featured_teams: set[str] = set()

    for _, m in played.iterrows():
        home, away = str(m.get("home_team","")), str(m.get("away_team",""))
        hg, ag     = int(m.get("home_goals",0)), int(m.get("away_goals",0))
        match_num  = int(m.get("match_number",0))

        entry: dict = {
            "match": match_num,
            "date": str(m.get("match_date","")),
            "group": str(m.get("group","")),
            "home": home, "away": away,
            "score": f"{hg}–{ag}",
            "home_owners": ownership.get(home,[]),
            "away_owners": ownership.get(away,[]),
        }

        winner = loser = None
        if hg > ag:   winner, loser = home, away
        elif ag > hg: winner, loser = away, home

        if winner and loser:
            wt, lt = tier_map.get(winner,0), tier_map.get(loser,0)
            if wt > lt:
                bonus = _UPSET_BONUS.get(min(wt-lt,3), 0)
                upsets.append({
                    "match": match_num, "winner": winner, "winner_tier": wt,
                    "loser": loser, "loser_tier": lt, "score": f"{hg}–{ag}",
                    "bonus_pts_each_owner": bonus,
                    "winner_owners": ownership.get(winner,[]),
                    "loser_owners":  ownership.get(loser,[]),
                    "date": str(m.get("match_date","")),
                })
                featured_teams.update([winner, loser])

        match_events: list[str] = []
        for side, team in (("home",home),("away",away)):
            rc  = int(m.get(f"{side}_red_cards",0))
            ht  = int(m.get(f"{side}_hat_tricks",0))
            so_ = int(m.get(f"{side}_shirt_off",0))
            gkg = int(m.get(f"{side}_gk_goals",0))
            fe  = int(m.get(f"{side}_first_eliminated",0))
            opp = away if side=="home" else home
            if ht:
                hat_tricks.append({"team":team,"match":match_num,"opponent":opp,
                    "score":f"{hg}–{ag}","owners":ownership.get(team,[]),"date":str(m.get("match_date",""))})
                match_events.append(f"{team} hat trick vs {opp} (+10 pts)")
                featured_teams.add(team)
            if rc:
                special_events.append({"type":"red_card","team":team,"count":rc,
                    "match":match_num,"owners":ownership.get(team,[]),"opponent":opp,
                    "score":f"{hg}–{ag}","date":str(m.get("match_date",""))})
                match_events.append(f"{team} {rc} red card(s) vs {opp} (-{rc*5} pts)")
            if so_:
                special_events.append({"type":"shirt_removal","team":team,
                    "match":match_num,"owners":ownership.get(team,[]),"opponent":opp,
                    "score":f"{hg}–{ag}","date":str(m.get("match_date",""))})
                match_events.append(f"{team} shirt removal vs {opp} (+25 pts)")
            if gkg:
                special_events.append({"type":"gk_goal","team":team,
                    "match":match_num,"owners":ownership.get(team,[]),"opponent":opp,
                    "score":f"{hg}–{ag}","date":str(m.get("match_date",""))})
                match_events.append(f"{team} GK GOAL vs {opp} (+75 pts!)")
                featured_teams.add(team)
            if fe:
                special_events.append({"type":"first_eliminated","team":team,
                    "match":match_num,"owners":ownership.get(team,[]),"opponent":opp,
                    "score":f"{hg}–{ag}","date":str(m.get("match_date",""))})
                match_events.append(f"{team} FIRST ELIMINATED (+35 pts for owners)")
        if int(m.get("comeback_home",0)):
            match_events.append(f"{home} comeback win (+3 bonus pts)")
        if int(m.get("comeback_away",0)):
            match_events.append(f"{away} comeback win (+3 bonus pts)")
        pw = str(m.get("penalty_winner","") or "")
        if pw and pw not in ("0","nan",""):
            match_events.append(f"Penalty shootout: {pw} wins")
        if abs(hg-ag) >= 3 and winner:
            featured_teams.update([home, away])
        if match_events:
            entry["notable_events"] = match_events
        match_narratives.append(entry)

    standings: list[dict] = []
    if not lb.empty:
        for _, row in lb.iterrows():
            p = str(row.get("Player",""))
            standings.append({
                "rank":       int(row.get("Rank",0)),
                "player":     p,
                "paid":       pay_status.get(p,"UNPAID") == "PAID",
                "total_pts":  round(float(row.get("TotalPoints",0)),1),
                "captain":    pre_captains.get(p,"not set"),
                "teams":      assignments.get(p,[]),
                "predictions":predictions.get(p,{}),
            })

    top_teams: list[dict] = []
    if not stats.empty:
        goal_col = next((c for c in ["GroupGoals","Goals","TotalGoals"] if c in stats.columns), None)
        if goal_col:
            ts = (stats.assign(_g=pd.to_numeric(stats[goal_col],errors="coerce").fillna(0))
                  .query("_g > 0").sort_values("_g",ascending=False).head(10))
            for _, row in ts.iterrows():
                team = str(row["Team"])
                top_teams.append({
                    "team":   team,
                    "goals":  int(float(row.get(goal_col,0))),
                    "tier":   tier_map.get(team,0),
                    "owners": ownership.get(team,[]),
                })
            if top_teams:
                featured_teams.add(top_teams[0]["team"])

    total_goals = int(played["home_goals"].sum() + played["away_goals"].sum())
    n_matches   = len(played)
    n_all       = len(all_played)

    period_label = "Full tournament so far"
    if date_from and date_to:
        period_label = f"{date_from.strftime('%d %b')} - {date_to.strftime('%d %b %Y')}"
    elif date_from:
        period_label = f"From {date_from.strftime('%d %b %Y')}"
    elif date_to:
        period_label = f"Up to {date_to.strftime('%d %b %Y')}"

    n_players  = len(standings)
    unpaid_top = [s for s in standings if not s["paid"] and s["rank"] <= max(1, n_players//2)]

    # Upcoming fixtures that involve at least one owned team
    played_nums = set(all_played["match_number"].dropna().astype(int).tolist())
    upcoming_df = (
        fixtures[~fixtures["match_number"].isin(played_nums)]
        .sort_values("match_number")
    )
    upcoming_owned = upcoming_df[
        upcoming_df["home_team"].isin(ownership) | upcoming_df["away_team"].isin(ownership)
    ].head(10)
    upcoming_fixtures = [
        {
            "match":       int(r["match_number"]),
            "date":        str(r.get("match_date","")),
            "home":        str(r.get("home_team","")),
            "away":        str(r.get("away_team","")),
            "home_owners": ownership.get(str(r.get("home_team","")), []),
            "away_owners": ownership.get(str(r.get("away_team","")), []),
        }
        for _, r in upcoming_owned.iterrows()
    ]

    # ── Slim the context to keep token count manageable ──────────────────────
    # Only include matches that have something notable; summarise the rest
    notable_matches = [m for m in match_narratives if m.get("notable_events")]
    # Also include high-scoring matches not already captured
    high_score = [
        m for m in match_narratives
        if m not in notable_matches
        and sum(int(x) for x in m.get("score","0–0").replace("–","-").split("-") if x.isdigit()) >= 5
    ]
    notable_matches = (notable_matches + high_score)[:20]
    other_n = len(match_narratives) - len(notable_matches)

    # Slim standings: drop verbose teams/predictions lists
    slim_standings = [
        {k: v for k, v in s.items() if k in ("rank","player","paid","total_pts","captain")}
        for s in standings
    ]
    slim_unpaid = [
        {k: v for k, v in s.items() if k in ("rank","player","paid","total_pts")}
        for s in unpaid_top
    ]

    return {
        "sweepstake_info": (
            f"{n_players} friends, each owning teams across 4 FIFA tiers. "
            "Points: Goal 1pt, Clean sheet 2pt, Win 3pt, "
            "Upset vs 1 tier higher +15pt / 2 tiers +30pt / 3 tiers +50pt, "
            "Hat trick 10pt, Shirt removal 25pt, GK goal 75pt, Red card -5pt. "
            "Captain earns x1.5 their points. Only PAID players win prizes."
        ),
        "period":               period_label,
        "matches_in_period":    n_matches,
        "total_matches_played": n_all,
        "goals_in_period":      total_goals,
        "avg_goals_per_game":   round(total_goals/n_matches,2) if n_matches else 0,
        "prize_pool":           prize_pool,
        "current_standings":    slim_standings,
        "unpaid_players_in_top_half": slim_unpaid,
        "match_results":        notable_matches,
        "other_matches_no_events": other_n,
        "upsets":               upsets[:10],
        "hat_tricks":           hat_tricks,
        "special_events":       special_events,
        "top_scoring_teams":    [{k: v for k, v in t.items() if k != "owners"} for t in top_teams[:8]],
        "featured_teams":       sorted(featured_teams)[:8],
        "upcoming_owned_fixtures": upcoming_fixtures[:6],
        "ownership_summary":    {t: owners for t, owners in ownership.items() if owners},
    }


# ── LLM ───────────────────────────────────────────────────────────────────────

def _generate_story(context: dict, api_key: str, topic: str = "", suggestions: str = "") -> dict:
    from groq import Groq
    client = Groq(api_key=api_key)

    extras = []
    if topic.strip():
        extras.append(f"ANGLE: {topic.strip()}")
    if suggestions.strip():
        extras.append(f"SPECIFIC POINTS TO INCLUDE:\n{suggestions.strip()}")
    extras_block = ("\n\n" + "\n\n".join(extras)) if extras else ""

    n_players = len(context.get("current_standings", []))
    system = (
        f"You are a sharp tabloid football journalist writing the front page of a private "
        f"World Cup 2026 sweepstake newspaper. Your audience is {n_players} friends. "
        "You write like a passionate sports tabloid — vivid, dramatic, specific, occasionally cheeky. "
        "Always connect on-pitch events to their sweepstake consequences (who owns the team, points earned). "
        "CRITICAL: Never invent or hallucinate match results, fixtures, or scorelines. "
        "Only reference facts present in the DATA block."
    )

    user = f"""Write a complete newspaper edition covering: {context['period']}.
{extras_block}

DATA:
<data>
{json.dumps(context, indent=2)}
</data>

OUTPUT — respond ONLY with a single valid JSON object, no markdown fences:

{{
  "headline": "ALL-CAPS FRONT-PAGE HEADLINE max 10 words punchy and dramatic",
  "subheadline": "One dramatic sentence expanding the headline",
  "lead_paragraph": "The single most dramatic moment. 4-5 sentences. Name scorelines, teams, sweepstake owners.",
  "sections": [
    {{"title": "SECTION TITLE IN CAPS", "content": "4-5 sentences. One distinct theme. No repeated facts across sections."}},
    {{"title": "...", "content": "..."}},
    {{"title": "...", "content": "..."}},
    {{"title": "...", "content": "..."}},
    {{"title": "...", "content": "..."}}
  ],
  "player_spotlight": {{
    "name": "Full player name notable in the data",
    "team": "Their national team",
    "achievement": "One-line stat or moment",
    "narrative": "3-4 sentences dramatically. Name their sweepstake owners."
  }},
  "image_subjects": [
    {{"name": "player or team name", "team": "national team", "context": "what they did e.g. scored hat trick"}},
    {{"name": "...", "team": "...", "context": "..."}}
  ],
  "sweepstake_digest": "4-5 sentences: who leads, who is climbing, name unpaid players doing well and suggest they pay up",
  "pull_quote": "One vivid standalone sentence for a big pull quote",
  "looking_ahead": "2-3 sentences. ONLY reference fixtures listed in upcoming_owned_fixtures. Name the sweepstake owners who have skin in the game. If upcoming_owned_fixtures is empty, comment on a standings battle instead. NEVER mention a fixture not in the data."
}}

RULES:
- 5 sections covering DIFFERENT themes from: key match results, goals and attacking play, sweepstake standings drama, dark horse watch, comeback stories, group stage battles, any interesting angle
- DO NOT write sections about upsets or special events (hat tricks, red cards, shirt removals) — those are shown as graphics separately
- Name sweepstake players when their teams do something notable
- Use real scorelines only — never invent facts
- NEVER reference a fixture, team, or scoreline not present in the DATA block
- looking_ahead MUST only reference matches in upcoming_owned_fixtures — do not invent fixtures
- No repeated information across sections
- player_spotlight must be the single most notable player from the data
- image_subjects: list 2-3 subjects to generate AI artwork for (player names or team moments)
- Tone: passionate tabloid football journalist
"""

    _models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    raw = None
    last_err = None
    for _model in _models:
        try:
            resp = client.chat.completions.create(
                model=_model,
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                max_tokens=2500,
                temperature=0.75,
                response_format={"type":"json_object"},
            )
            raw = resp.choices[0].message.content
            break
        except Exception as _e:
            last_err = _e
            _e_str = str(_e).lower()
            if ("429" in str(_e) or "413" in str(_e)
                    or "rate_limit" in _e_str or "decommissioned" in _e_str
                    or "too large" in _e_str or "tokens" in _e_str):
                continue
            raise
    if raw is None:
        raise last_err
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"headline":"STORY GENERATED","subheadline":"","lead_paragraph":raw,
                "sections":[],"player_spotlight":{},"featured_players":[],
                "sweepstake_digest":"","pull_quote":"","looking_ahead":""}


# ── Render helpers ─────────────────────────────────────────────────────────────

def _hr() -> None:
    st.markdown(
        f'<hr style="border:0;border-top:2px solid {_BORDER};margin:1.2rem 0 0.8rem">',
        unsafe_allow_html=True,
    )

def _thin_rule() -> None:
    st.markdown(
        f'<hr style="border:0;border-top:1px solid {_BORDER}55;margin:0.5rem 0">',
        unsafe_allow_html=True,
    )

def _section_banner(title: str) -> None:
    st.markdown(
        f'<div style="background:{_BORDER};color:white;font-size:0.7rem;font-weight:900;'
        f'letter-spacing:0.14em;padding:0.35rem 0.8rem;margin-bottom:0.6rem">{title}</div>',
        unsafe_allow_html=True,
    )

def _stat_box(value: str, label: str, color: str = "#8B0000") -> str:
    return (
        f'<div style="border-top:3px solid {color};padding:0.7rem 0.5rem;text-align:center;'
        f'background:white;border-radius:3px;border:1px solid {_BORDER}22;border-top:3px solid {color}">'
        f'<div style="font-size:1.8rem;font-weight:900;color:{color};line-height:1">{value}</div>'
        f'<div style="font-size:0.65rem;color:{_MID};text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-top:0.15rem">{label}</div>'
        f'</div>'
    )

def _score_card(home: str, away: str, hg: int, ag: int, events: list | None = None) -> str:
    hf = _flag_img(home, 22)
    af = _flag_img(away, 22)
    wh = "font-weight:800" if hg > ag else "opacity:0.55"
    wa = "font-weight:800" if ag > hg else "opacity:0.55"
    ev_html = ""
    if events:
        ev_html = (f'<div style="font-size:0.63rem;color:{_MID};margin-top:4px;line-height:1.5">'
                   + "<br>".join(events[:3]) + "</div>")
    return (
        f'<div style="background:white;border:1px solid {_BORDER}33;border-radius:5px;'
        f'padding:0.55rem 0.7rem;margin-bottom:0.5rem">'
        f'<div style="display:flex;align-items:center;justify-content:space-between">'
        f'<span style="color:{_INK};{wh};font-size:0.82rem">{hf}{home}</span>'
        f'<span style="color:{_RED};font-weight:900;font-size:1.15rem;padding:0 0.5rem">{hg}–{ag}</span>'
        f'<span style="color:{_INK};{wa};font-size:0.82rem;text-align:right">{away}{af}</span>'
        f'</div>{ev_html}</div>'
    )

def _upset_card(u: dict) -> str:
    wf = _flag_img(u["winner"], 22)
    lf = _flag_img(u["loser"], 22)
    owners = ", ".join(u.get("winner_owners",[]))
    return (
        f'<div style="background:#FFF3E0;border-left:4px solid #E65100;'
        f'border-radius:0 5px 5px 0;padding:0.55rem 0.85rem;margin-bottom:0.5rem">'
        f'<div style="font-size:0.6rem;font-weight:900;letter-spacing:0.1em;'
        f'color:#E65100;margin-bottom:0.25rem">UPSET · T{u["winner_tier"]} BEATS T{u["loser_tier"]} · +{u["bonus_pts_each_owner"]}pts</div>'
        f'<div style="color:{_INK};font-size:0.88rem;font-weight:600">'
        f'{wf}{u["winner"]} <span style="color:#E65100">{u["score"]}</span> {lf}{u["loser"]}</div>'
        f'<div style="font-size:0.68rem;color:{_MID};margin-top:0.2rem">'
        f'Owners: {owners or "—"} · {u.get("date","")}</div>'
        f'</div>'
    )

def _special_event_card(ev: dict) -> str:
    t      = ev.get("type","")
    team   = ev.get("team","")
    owners = ", ".join(ev.get("owners",[]))
    opp    = ev.get("opponent","")
    score  = ev.get("score","")
    flag   = _flag_img(team, 20)

    configs = {
        "red_card":         ("#CC0000","#FFF5F5","🟥","RED CARD",f"-{ev.get('count',1)*5} pts"),
        "shirt_removal":    ("#B45309","#FFFBF0","🎽","SHIRT OFF!","+25 pts"),
        "gk_goal":          ("#166534","#F0FFF4","🥅","GK SCORES!","+75 pts"),
        "hat_trick":        ("#8B0000","#FFF5F5","⚽⚽⚽","HAT TRICK!","+10 pts"),
        "first_eliminated": ("#5C4033","#F5F0E8","💀","ELIMINATED!","+35 pts"),
    }
    cfg = configs.get(t, ("#333","#fff","","EVENT","+0 pts"))
    border_col, bg_col, emoji, label, pts = cfg
    return (
        f'<div style="background:{bg_col};border-left:4px solid {border_col};'
        f'border-radius:0 5px 5px 0;padding:0.5rem 0.85rem;margin-bottom:0.45rem">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<span style="font-size:0.62rem;font-weight:900;letter-spacing:0.1em;color:{border_col}">'
        f'{emoji} {label}</span>'
        f'<span style="font-size:0.7rem;font-weight:700;color:{border_col}">{pts}</span>'
        f'</div>'
        f'<div style="color:{_INK};font-size:0.85rem;font-weight:600;margin-top:0.2rem">'
        f'{flag}{team} vs {opp} ({score})</div>'
        f'<div style="font-size:0.68rem;color:{_MID};margin-top:0.15rem">'
        f'Owners: {owners or "—"} · {ev.get("date","")}</div>'
        f'</div>'
    )


# ── Main render ────────────────────────────────────────────────────────────────

# Themes that have dedicated graphic sections — skip LLM text sections for these
_GRAPHIC_THEMES = {"UPSET","SPECIAL","RED CARD","HAT TRICK","HAT-TRICK","SHIRT OFF","SHIRT REMOVAL","GK GOAL"}

def _is_graphic_theme(title: str) -> bool:
    tu = title.upper()
    return any(w in tu for w in _GRAPHIC_THEMES)


def _render_newspaper(story: dict, meta: dict, context: dict, best_days: list) -> None:
    ft        = context.get("featured_teams", [])
    upsets    = context.get("upsets", [])
    specials  = context.get("special_events", [])
    top_teams = context.get("top_scoring_teams", [])
    standings = context.get("current_standings", [])
    matches   = context.get("match_results", [])
    hat_tricks= context.get("hat_tricks", [])
    prize     = context.get("prize_pool", 0)
    img_subjs = story.get("image_subjects", [])
    spotlight = story.get("player_spotlight", {})
    sections  = story.get("sections", [])

    today_str = datetime.now().strftime("%A, %d %B %Y").upper()

    # ── Full cream background via CSS ──────────────────────────────────────
    st.markdown(
        f"""<style>
        [data-testid="stMain"] > div,
        [data-testid="stMainBlockContainer"],
        .block-container {{
            background-color: {_BG} !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )

    # ── Masthead ───────────────────────────────────────────────────────────
    flag_strip = "".join(
        f'<img src="{_flag_url(t,40)}" '
        f'style="height:20px;border-radius:2px;margin:0 2px;vertical-align:middle" title="{t}"'
        f' onerror="this.style.display=\'none\'">'
        for t in ft[:12] if _flag_url(t, 40)
    )
    st.markdown(
        f'<div style="font-family:Georgia,serif">'
        f'<div style="border-top:4px solid {_BORDER};border-bottom:4px solid {_BORDER};'
        f'padding:0.6rem 0 0.4rem;text-align:center">'
        f'<div style="font-size:clamp(1.8rem,5vw,3rem);font-weight:900;color:{_INK};'
        f'letter-spacing:0.05em;line-height:1">THE SWEEPSTAKE GAZETTE</div>'
        f'<div style="font-size:0.65rem;color:{_MID};letter-spacing:0.08em;margin-top:0.2rem">'
        f'WC 2026 · OFFICIAL SWEEPSTAKE RECORD</div>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'flex-wrap:wrap;gap:0.3rem;padding:0.3rem 0;border-bottom:1px solid {_BORDER}66">'
        f'<span style="font-size:0.65rem;color:{_MID}">Edition: {meta.get("period","?")}</span>'
        f'<span>{flag_strip}</span>'
        f'<span style="font-size:0.65rem;color:{_MID}">{today_str}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Prize pool + Top 3 ─────────────────────────────────────────────────
    top3   = standings[:3]
    medals = ["🥇","🥈","🥉"]
    podium_parts = []
    for i, s in enumerate(top3):
        paid_badge = (
            '<span style="background:#166534;color:white;font-size:0.55rem;'
            'padding:1px 4px;border-radius:3px;margin-left:3px">PAID</span>'
            if s.get("paid") else
            f'<span style="background:{_RED};color:white;font-size:0.55rem;'
            f'padding:1px 4px;border-radius:3px;margin-left:3px">UNPAID</span>'
        )
        podium_parts.append(
            f'<div style="text-align:center;flex:1;padding:0 0.5rem">'
            f'<div style="font-size:1.4rem">{medals[i]}</div>'
            f'<div style="font-size:0.8rem;font-weight:700;color:{_INK}">{s["player"]}{paid_badge}</div>'
            f'<div style="font-size:0.78rem;color:{_RED};font-weight:900">{s["total_pts"]} pts</div>'
            f'</div>'
        )
    st.markdown(
        f'<div style="background:white;border:2px solid {_BORDER};border-radius:6px;'
        f'padding:0.9rem 1rem;margin:0.6rem 0;font-family:Georgia,serif">'
        f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:0.8rem">'
        f'<div style="flex:0 0 auto;text-align:center;padding-right:1rem;'
        f'border-right:2px solid {_BORDER}33">'
        f'<div style="font-size:0.6rem;font-weight:700;letter-spacing:0.1em;color:{_MID};margin-bottom:0.2rem">PRIZE POOL</div>'
        f'<div style="font-size:1.7rem;font-weight:900;color:{_RED}">€{prize}</div>'
        f'</div>'
        f'<div style="flex:1;display:flex;justify-content:space-evenly">'
        f'{"".join(podium_parts)}'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # ── Stat boxes ─────────────────────────────────────────────────────────
    n_m = context.get("matches_in_period", 0)
    n_g = context.get("goals_in_period", 0)
    n_u = len(upsets)
    n_s = len(specials) + len(hat_tricks)
    b1, b2, b3, b4 = st.columns(4)
    b1.markdown(_stat_box(str(n_m), "Matches Played",  "#8B0000"),  unsafe_allow_html=True)
    b2.markdown(_stat_box(str(n_g), "Goals Scored",    "#166534"),  unsafe_allow_html=True)
    b3.markdown(_stat_box(str(n_u), "Upsets",          "#B45309"),  unsafe_allow_html=True)
    b4.markdown(_stat_box(str(n_s), "Special Events",  "#1e3a5f"),  unsafe_allow_html=True)

    _hr()

    # ── Headline ───────────────────────────────────────────────────────────
    headline    = story.get("headline","").upper()
    subheadline = story.get("subheadline","")
    st.markdown(
        f'<div style="font-family:Georgia,serif;text-align:center;padding:0.6rem 0 0.8rem;'
        f'border-bottom:2px solid {_BORDER}">'
        f'<div style="font-size:clamp(1.5rem,4vw,2.4rem);font-weight:900;color:{_INK};'
        f'line-height:1.15;letter-spacing:0.01em">{headline}</div>'
        f'<div style="color:{_RED};font-size:1rem;font-style:italic;margin-top:0.4rem">{subheadline}</div>'
        f'<div style="color:{_MID};font-size:0.68rem;margin-top:0.3rem">'
        f'By Your Sweepstake Correspondent'
        + (f' · <em>{meta.get("topic","")}</em>' if meta.get("topic") else "") +
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Lead + pull quote ───────────────────────────────────────────────────
    lead = story.get("lead_paragraph","")
    pull = story.get("pull_quote","")
    cl, cp = st.columns([3,2])
    with cl:
        if lead:
            st.markdown(
                f'<p style="font-family:Georgia,serif;font-size:1.05rem;line-height:1.9;'
                f'font-weight:600;color:{_INK};margin:0.8rem 0 0">{lead}</p>',
                unsafe_allow_html=True,
            )
    with cp:
        if pull:
            st.markdown(
                f'<div style="background:white;border-top:4px solid {_RED};'
                f'border-bottom:4px solid {_RED};padding:1rem;margin-top:0.8rem">'
                f'<div style="font-size:0.6rem;font-weight:900;letter-spacing:0.1em;'
                f'color:{_MID};margin-bottom:0.5rem">PULL QUOTE</div>'
                f'<div style="font-family:Georgia,serif;font-size:1.05rem;font-style:italic;'
                f'color:{_INK};line-height:1.65">"{pull}"</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Featured team graphic strip (flags + badges, no external images) ────────
    # Show hat trick teams, top scorers, and upset winners as graphic cards
    featured_cards: list[dict] = []
    seen_teams: set[str] = set()

    for ht in hat_tricks:
        t = ht.get("team","")
        if t and t not in seen_teams:
            featured_cards.append({"team":t,"label":"HAT TRICK ⚽⚽⚽","color":"#8B0000",
                                   "detail":f"vs {ht.get('opponent','')} ({ht.get('score','')})"})
            seen_teams.add(t)

    for u in upsets[:2]:
        t = u.get("winner","")
        if t and t not in seen_teams:
            featured_cards.append({"team":t,"label":f"UPSET +{u['bonus_pts_each_owner']}pts ⚡","color":"#E65100",
                                   "detail":f"T{u['winner_tier']} beats T{u['loser_tier']} · {u['score']}"})
            seen_teams.add(t)

    if top_teams and top_teams[0]["team"] not in seen_teams:
        t = top_teams[0]
        featured_cards.append({"team":t["team"],"label":f"TOP SCORERS {t['goals']} ⚽","color":"#166534",
                               "detail":f"Owners: {', '.join(t.get('owners',[]))}"})
        seen_teams.add(t["team"])

    featured_cards = featured_cards[:4]

    if featured_cards:
        _hr()
        _section_banner("TEAMS IN THE NEWS")
        fc_cols = st.columns(len(featured_cards))
        for col, card in zip(fc_cols, featured_cards):
            flag_u = _flag_url(card["team"], 80)
            flag_html = (
                f'<img src="{flag_u}" style="width:60px;border-radius:4px;display:block;margin:0 auto 0.5rem"'
                f' onerror="this.outerHTML=\'<div style=&quot;width:60px;height:38px;background:{card["color"]}22;'
                f'border-radius:4px;display:flex;align-items:center;justify-content:center;'
                f'margin:0 auto 0.5rem;font-size:1.5rem&quot;>⚽</div>\'">'
            ) if flag_u else f'<div style="font-size:1.5rem;margin-bottom:0.5rem">⚽</div>'
            col.markdown(
                f'<div style="background:white;border-top:3px solid {card["color"]};'
                f'border:1px solid {_BORDER}22;border-top:3px solid {card["color"]};'
                f'border-radius:4px;padding:0.75rem 0.5rem;text-align:center;'
                f'font-family:Georgia,serif">'
                f'{flag_html}'
                f'<div style="font-size:0.82rem;font-weight:700;color:{_INK}">{card["team"]}</div>'
                f'<div style="font-size:0.6rem;font-weight:900;color:{card["color"]};'
                f'letter-spacing:0.08em;margin:0.25rem 0">{card["label"]}</div>'
                f'<div style="font-size:0.65rem;color:{_MID}">{card["detail"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Story sections (skip themes that have dedicated graphic sections) ───────
    _hr()
    rendered = 0
    for sec in sections:
        title   = sec.get("title","")
        content = sec.get("content","")
        if not content or _is_graphic_theme(title):
            continue
        if rendered > 0:
            _hr()
        rendered += 1
        _section_banner(title)
        st.markdown(
            f'<p style="font-family:Georgia,serif;font-size:0.93rem;'
            f'line-height:1.85;color:{_INK};margin:0">{content}</p>',
            unsafe_allow_html=True,
        )
        # Score cards after results/match sections
        if any(w in title.upper() for w in ["RESULT","MATCH","SCORE","WIN","FIXTURE","GOAL"]):
            notable = [m for m in matches
                       if m.get("notable_events") or
                       abs(int(m.get("score","0-0").replace("–","-").split("-")[0])
                           -int(m.get("score","0-0").replace("–","-").split("-")[1]))>=3]
            if notable:
                c1, c2 = st.columns(2)
                for j, m in enumerate(notable[:8]):
                    s = m.get("score","0–0").replace("–","-")
                    parts = s.split("-")
                    hg_, ag_ = (int(parts[0]),int(parts[1])) if len(parts)==2 else (0,0)
                    card = _score_card(m["home"], m["away"], hg_, ag_, m.get("notable_events"))
                    (c1 if j%2==0 else c2).markdown(card, unsafe_allow_html=True)

    # ── Special events ──────────────────────────────────────────────────────
    all_specials: list[dict] = [
        {"type":"hat_trick","team":h["team"],"owners":h["owners"],
         "opponent":h.get("opponent",""),"score":h.get("score",""),"date":h.get("date","")}
        for h in hat_tricks
    ] + specials

    if all_specials:
        _hr()
        _section_banner("SPECIAL EVENTS")
        ec1, ec2 = st.columns(2)
        for j, ev in enumerate(all_specials):
            (ec1 if j%2==0 else ec2).markdown(_special_event_card(ev), unsafe_allow_html=True)

    # ── Upsets ─────────────────────────────────────────────────────────────
    if upsets:
        _hr()
        _section_banner("UPSET WATCH")
        uc1, uc2 = st.columns(2)
        for j, u in enumerate(upsets):
            (uc1 if j%2==0 else uc2).markdown(_upset_card(u), unsafe_allow_html=True)

    # ── Player spotlight ────────────────────────────────────────────────────
    if spotlight and spotlight.get("name"):
        pname    = spotlight.get("name","")
        pteam    = spotlight.get("team","")
        pachieve = spotlight.get("achievement","")
        pnarr    = spotlight.get("narrative","")
        _hr()
        _section_banner("PLAYER SPOTLIGHT")
        pcol_img, pcol_text = st.columns([1,2])
        with pcol_img:
            flag_u = _flag_url(pteam, 80)
            st.markdown(
                f'<div style="background:white;border:2px solid {_BORDER};border-radius:6px;'
                f'padding:1.2rem 0.8rem;text-align:center;font-family:Georgia,serif">'
                + (f'<img src="{flag_u}" style="width:70px;border-radius:4px;margin-bottom:0.6rem"'
                   f' onerror="this.outerHTML=\'<div style=&quot;font-size:2rem;margin-bottom:0.6rem&quot;>🏴</div>\'">'
                   if flag_u else '<div style="font-size:2rem;margin-bottom:0.6rem">🏴</div>')
                + f'<div style="font-size:0.65rem;font-weight:900;letter-spacing:0.1em;color:{_RED}">SPOTLIGHT</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with pcol_text:
            st.markdown(
                f'<div style="font-family:Georgia,serif">'
                f'<div style="font-size:1.5rem;font-weight:900;color:{_INK}">{pname}</div>'
                f'<div style="font-size:0.78rem;color:{_MID};margin:0.2rem 0 0.6rem">'
                f'{_flag_img(pteam,18)}{pteam} · <em>{pachieve}</em></div>'
                f'<p style="font-size:0.92rem;line-height:1.8;color:{_INK};margin:0">{pnarr}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Hottest single day ──────────────────────────────────────────────────
    if best_days:
        _hr()
        _section_banner("HOTTEST SINGLE DAY — MOST POINTS EARNED IN ONE DAY")
        fire = ["🔥🔥🔥","🔥🔥🔥","🔥🔥","🔥🔥","🔥🔥","🔥","🔥","🔥","🔥","🔥"]
        rows_html = ""
        for i, d in enumerate(best_days):
            bg = f"background-color:{_RED}10;" if i == 0 else ""
            rows_html += (
                f'<tr style="{bg}">'
                f'<td style="padding:0.4rem 0.6rem;font-size:1rem;text-align:center">{fire[min(i,9)]}</td>'
                f'<td style="padding:0.4rem 0.6rem;font-size:0.78rem;font-weight:700;color:{_MID}">{i+1}</td>'
                f'<td style="padding:0.4rem 0.6rem;font-size:0.9rem;font-weight:700;color:{_INK}">{d["player"]}</td>'
                f'<td style="padding:0.4rem 0.6rem;font-size:0.78rem;color:{_MID}">{d["date"]}</td>'
                f'<td style="padding:0.4rem 0.6rem;font-size:1rem;font-weight:900;color:{_RED};text-align:right">+{d["gain"]}</td>'
                f'</tr>'
            )
        st.markdown(
            f'<div style="background:white;border:1px solid {_BORDER}33;border-radius:5px;overflow:hidden;'
            f'font-family:Georgia,serif">'
            f'<table style="width:100%;border-collapse:collapse">'
            f'<thead><tr style="background:{_BORDER};color:white">'
            f'<th style="padding:0.35rem 0.6rem;text-align:center;font-size:0.65rem;letter-spacing:0.08em"></th>'
            f'<th style="padding:0.35rem 0.6rem;text-align:left;font-size:0.65rem;letter-spacing:0.08em">#</th>'
            f'<th style="padding:0.35rem 0.6rem;text-align:left;font-size:0.65rem;letter-spacing:0.08em">PLAYER</th>'
            f'<th style="padding:0.35rem 0.6rem;text-align:left;font-size:0.65rem;letter-spacing:0.08em">DATE</th>'
            f'<th style="padding:0.35rem 0.6rem;text-align:right;font-size:0.65rem;letter-spacing:0.08em">PTS GAINED</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table></div>',
            unsafe_allow_html=True,
        )
        # Show latest score snapshot date so any staleness is immediately visible
        try:
            _sh = pd.read_csv(_SCORE_HISTORY_PATH, dtype=str)
            _latest_sh = pd.to_datetime(_sh["Date"], errors="coerce").max()
            if pd.notna(_latest_sh):
                st.caption(f"Score history through {_latest_sh.strftime('%d %b')}")
        except Exception:
            pass

    # ── Top goalscorers + Sweepstake digest ────────────────────────────────
    _hr()
    tc1, tc2 = st.columns([3,2])

    with tc1:
        _section_banner("TOP GOALSCORERS BY TEAM")
        if top_teams:
            max_g = top_teams[0]["goals"] if top_teams else 1
            bar_rows = ""
            for t in top_teams[:8]:
                tf  = _flag_img(t["team"], 18)
                pct = round(t["goals"] / max_g * 100)
                ow  = ", ".join(t.get("owners",[]))
                tier_label = f"T{t['tier']}" if t.get("tier") else ""
                bar_rows += (
                    f'<div style="margin-bottom:0.55rem">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px">'
                    f'<span style="font-size:0.82rem;color:{_INK};font-weight:600">{tf}{t["team"]}'
                    f'<span style="font-size:0.6rem;color:{_MID};margin-left:4px">{tier_label}</span></span>'
                    f'<span style="font-size:0.9rem;font-weight:900;color:{_RED}">{t["goals"]} ⚽</span>'
                    f'</div>'
                    f'<div style="background:{_BORDER}22;border-radius:2px;height:7px">'
                    f'<div style="background:{_RED};width:{pct}%;height:7px;border-radius:2px"></div></div>'
                    f'<div style="font-size:0.62rem;color:{_MID};margin-top:1px">Owners: {ow}</div>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="background:white;border:1px solid {_BORDER}22;'
                f'border-radius:5px;padding:0.8rem;font-family:Georgia,serif">{bar_rows}</div>',
                unsafe_allow_html=True,
            )

    with tc2:
        _section_banner("SWEEPSTAKE DIGEST")
        digest = story.get("sweepstake_digest","")
        if digest:
            st.markdown(
                f'<p style="font-family:Georgia,serif;font-size:0.88rem;line-height:1.8;'
                f'color:{_INK};margin:0 0 0.8rem">{digest}</p>',
                unsafe_allow_html=True,
            )
        _thin_rule()
        rows_html = ""
        for s in standings[:7]:
            paid_badge = (
                '<span style="background:#166534;color:white;font-size:0.52rem;'
                'padding:1px 3px;border-radius:2px;margin-left:3px">✓</span>'
                if s.get("paid") else
                f'<span style="background:{_RED};color:white;font-size:0.52rem;'
                f'padding:1px 3px;border-radius:2px;margin-left:3px">!</span>'
            )
            rows_html += (
                f'<tr>'
                f'<td style="color:{_LIGHT};font-size:0.72rem;padding:0.25rem 0.3rem;'
                f'text-align:center;border-bottom:1px solid {_BORDER}18">{s["rank"]}</td>'
                f'<td style="color:{_INK};font-size:0.78rem;font-weight:600;padding:0.25rem 0.3rem;'
                f'border-bottom:1px solid {_BORDER}18">{s["player"]}{paid_badge}</td>'
                f'<td style="color:{_RED};font-size:0.82rem;font-weight:900;padding:0.25rem 0.3rem;'
                f'text-align:right;border-bottom:1px solid {_BORDER}18">{s["total_pts"]}</td>'
                f'</tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;font-family:Georgia,serif">'
            f'<thead><tr>'
            f'<th style="color:{_MID};font-size:0.6rem;padding:0.2rem 0.3rem;text-align:center">#</th>'
            f'<th style="color:{_MID};font-size:0.6rem;padding:0.2rem 0.3rem;text-align:left">PLAYER</th>'
            f'<th style="color:{_MID};font-size:0.6rem;padding:0.2rem 0.3rem;text-align:right">PTS</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )

    # ── Looking ahead ───────────────────────────────────────────────────────
    looking = story.get("looking_ahead","")
    if looking:
        _hr()
        st.markdown(
            f'<div style="font-family:Georgia,serif;background:white;'
            f'border-top:3px solid {_INK};padding:0.75rem 1rem">'
            f'<span style="font-size:0.62rem;font-weight:900;letter-spacing:0.14em;color:{_RED}">'
            f'LOOKING AHEAD &nbsp;</span>'
            f'<span style="font-size:0.9rem;color:{_MID}">{looking}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Footer ──────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="font-family:Georgia,serif;text-align:center;padding:0.6rem 0 0.2rem;'
        f'border-top:1px solid {_BORDER}44;font-size:0.62rem;color:{_MID};margin-top:0.8rem">'
        f'Generated {meta.get("generated_at","?")} · '
        f'{meta.get("matches_covered","?")} matches covered · '
        f'The Sweepstake Gazette © 2026</div>',
        unsafe_allow_html=True,
    )


# ── Page ──────────────────────────────────────────────────────────────────────

page_header("Tournament News", "AI-generated newspaper from live match data")

try:
    _api_key  = st.secrets.get("GROQ_API_KEY", "")
    _admin_pw = st.secrets.get("ADMIN_PASSWORD", "wc2026admin")
except Exception:
    _api_key  = ""
    _admin_pw = "wc2026admin"
_cache    = _load_cache()
_is_admin = st.session_state.get("_story_admin", False)

# ── Admin login ────────────────────────────────────────────────────────────────
with st.sidebar:
    if not _is_admin:
        with st.expander("Admin", expanded=False):
            _pw = st.text_input("Password", type="password", key="story_pw")
            if st.button("Unlock", key="story_unlock"):
                if _pw == _admin_pw:
                    st.session_state["_story_admin"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("Admin mode")
        if st.button("Lock", key="story_lock"):
            st.session_state["_story_admin"] = False
            st.rerun()

# ── Admin newsroom ─────────────────────────────────────────────────────────────
_date_from: date | None = None
_date_to:   date | None = None
_topic            = ""
_suggestions      = ""
_generate_clicked = False

if _is_admin:
    st.markdown(
        f'<div style="color:{_GOLD};font-weight:700;font-size:1rem;'
        f'letter-spacing:0.05em;margin-bottom:0.25rem">📰 NEWSROOM</div>',
        unsafe_allow_html=True,
    )
    _today = date.today()
    _rc1, _rc2, _rc3 = st.columns([2,1,1])
    with _rc1:
        _period_choice = st.radio(
            "Time period",
            ["Full tournament","Last 3 days","Last 7 days","Custom"],
            horizontal=True, key="story_period",
        )
        if _period_choice == "Last 3 days":
            _date_from = _today - timedelta(days=3)
        elif _period_choice == "Last 7 days":
            _date_from = _today - timedelta(days=7)
        elif _period_choice == "Custom":
            _dc1, _dc2 = st.columns(2)
            _date_from = _dc1.date_input("From", value=_today-timedelta(days=7), key="story_from")
            _date_to   = _dc2.date_input("To",   value=_today,                   key="story_to")
    with _rc2:
        _topic = st.text_input("Angle", placeholder="e.g. red card chaos", key="story_topic")
    with _rc3:
        st.write("")
        st.write("")
        _generate_clicked = st.button(
            "Generate" if not _cache else "Regenerate",
            type="primary", use_container_width=True,
            disabled=not _api_key,
            help="Add GROQ_API_KEY to Streamlit secrets" if not _api_key else "",
        )

    _suggestions = st.text_area(
        "Specific points / players to include (one per line)",
        placeholder=(
            "Messi scored the hat trick for Argentina vs Algeria (match 19)\n"
            "Highlight unpaid players doing well and push them to pay up\n"
            "Focus on the biggest upsets"
        ),
        height=100, key="story_suggestions",
    )

    if _cache:
        st.caption(
            f"Last: **{_cache.get('generated_at','?')}** · "
            f"{_cache.get('matches_covered','?')} matches · "
            f"Period: {_cache.get('period','?')}"
            + (f" · _{_cache.get('topic','')}_" if _cache.get("topic") else "")
        )
    st.divider()

# ── Generation ─────────────────────────────────────────────────────────────────
if _generate_clicked:
    with st.spinner("Crunching data and writing the story…"):
        try:
            st.cache_data.clear()   # ensure leaderboard + stats are fresh from disk
            ctx       = _build_story_context(date_from=_date_from, date_to=_date_to)
            story_out = _generate_story(ctx, _api_key, topic=_topic, suggestions=_suggestions)
            _cache = {
                "generated_at":    datetime.now().strftime("%d %b %Y at %H:%M"),
                "matches_covered": ctx["total_matches_played"],
                "period":          ctx["period"],
                "topic":           _topic.strip(),
                "story":           story_out,
                "context":         ctx,
                # best_days is intentionally NOT cached — always computed fresh from local data
            }
            _save_cache(_cache)
            st.rerun()
        except Exception as exc:
            st.error(f"Generation failed: {exc}")

# ── Display ────────────────────────────────────────────────────────────────────
if _cache and "story" in _cache and "context" in _cache:
    _render_newspaper(
        story     = _cache["story"],
        meta      = _cache,
        context   = _cache["context"],
        best_days = _build_best_day_table(),   # always fresh from local score_history.csv
    )
elif _cache and "story" in _cache:
    try:
        ctx = _build_story_context()
        _render_newspaper(
            story=_cache["story"], meta=_cache,
            context=ctx, best_days=_build_best_day_table(),
        )
    except Exception as _e:
        st.warning(f"Story render error: {_e}")
        st.markdown(str(_cache["story"]))
else:
    if _is_admin:
        st.info("Configure settings above and hit **Generate** to publish the first edition.")
    else:
        st.info("The first edition hasn't been published yet — check back soon.")
