"""Rules — official competition rules and scoring system."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from dashboard.components.ui import page_header

page_header("Rules", "Official competition rules and scoring system")

tab_scoring, tab_purchases, tab_captains, tab_prizes, tab_tiebreakers, tab_full = st.tabs([
    "⚽ Scoring", "🛒 Purchases", "🎖️ Captains", "🏆 Prizes", "⚖️ Tiebreakers", "📄 Full Rules",
])

# ── SCORING ───────────────────────────────────────────────────────────────────
with tab_scoring:
    st.subheader("Match Events")
    st.markdown("""
| Event | Points |
|---|---|
| Goal Scored | +1 |
| Clean Sheet | +2 |
| Win | +3 |
| Penalty Shootout Win | +3 |
| Comeback Win | +3 |
| Hat Trick | +10 |
| Group Winner | +3 |
""")
    st.caption("**Win**: any win (normal time, extra time, or penalties). **Comeback Win**: won after going behind in normal/extra time — does not apply to penalty wins. Win and Comeback Win bonuses stack. Hat trick bonuses also stack with win.")

    st.subheader("Tournament Progression")
    st.caption("Each bonus is awarded **for reaching** that round. Bonuses are cumulative — a team reaching the QF earns the R32 + R16 + QF bonuses.")
    st.markdown("""
| Round | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|---|---|
| Round of 32 | +1 | +2 | +5 | +8 |
| Round of 16 | +2 | +4 | +8 | +12 |
| Quarter Final | +4 | +8 | +15 | +25 |
| Semi Final | +8 | +12 | +20 | +30 |
| Final | +12 | +18 | +32 | +45 |
| Winner | +20 | +28 | +46 | +65 |
""")

    with st.expander("Example: Tier 3 team wins the World Cup"):
        st.markdown("5 + 8 + 15 + 20 + 32 + 46 = **126 progression points**, plus all match stats on top.")

    st.subheader("Upset Win Bonuses")
    st.caption("Awarded per win against a team in a higher tier — auto-calculated from results.")
    st.markdown("""
| Win Against | Bonus |
|---|---|
| Beat a team **1 tier above** (e.g. Tier 3 beats Tier 2) | +15 |
| Beat a team **2 tiers above** (e.g. Tier 4 beats Tier 2) | +30 |
| Beat a team **3 tiers above** (e.g. Tier 4 beats Tier 1) | +50 |
""")

    st.subheader("Special Event Bonuses")
    st.caption("Manually entered by the admin with proof where noted.")
    st.markdown("""
| Event | Points |
|---|---|
| Player removes shirt to celebrate *(proof required)* | +25 |
| Goalkeeper scores a goal | +75 |
| Red card received | −15 |
| First team knocked out of the tournament | +35 *(to owners)* |
""")

    st.subheader("Prediction Pack Bonuses")
    st.markdown("""
| Prediction | Points |
|---|---|
| World Cup Winner correct | +30 |
| Runner-Up (2nd place) correct | +20 |
| Bronze Medal (3rd place) correct | +15 |
| Golden Boot correct | +25 |
| First Knocked Out correct | +20 |
| Dark Horse reaches QF | +15 |
| Dark Horse reaches SF | +30 |
| Dark Horse reaches Final | +40 |
| Dark Horse wins tournament | +50 |
""")
    st.caption("Dark Horse bonuses are cumulative. A Dark Horse that wins earns 15+30+40+50 = **135 pts** total.")

# ── PURCHASES ─────────────────────────────────────────────────────────────────
with tab_purchases:
    st.markdown(
        '<div style="background:#1A2535;border:1px solid #2A3A4A;border-radius:8px;'
        'padding:0.85rem 1.1rem;margin-bottom:1.1rem">'
        '<div style="color:#D4A017;font-weight:700;font-size:0.92rem;margin-bottom:0.45rem">'
        '💳 How to Buy an Add-On</div>'
        '<div style="color:#E5E7EB;font-size:0.84rem;line-height:1.65">'
        '1. Send the money to the <strong style="color:#D4A017">Shared Revolut Pocket</strong> '
        'and include what you\'re buying in the transaction message<br>'
        '2. <strong>Ninth Team</strong>  — teams are randomly drawn, &amp; <strong>Resurrection</strong> you choose'
        '<br>'
        '3. <strong>Prediction Pack</strong> — send your picks (World Cup winner, Golden Boot, Dark Horse, etc.) '
        'in a separate message<br>'
        '4. <strong>Captains</strong> — send your Pre-Tournament and Knockout captain picks separately'
        '</div></div>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Buy In — €5</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'Entry into the competition. Required to receive prizes. '
            'You still appear on the Overall Leaderboard without it, but are excluded from prize money.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Prediction Pack — €5</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'Unlocks six predictions: World Cup Winner (+30), Runner-Up (+20), '
            'Bronze Medal (+15), Golden Boot (+25), Dark Horse (up to +135 cumulative), '
            'and First Knocked Out (+20). '
            '<strong style="color:#D4A017">Lock: 19 June</strong> (before first group stage games kick off).</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Mulligan — €3</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'Complete redraw of all 8 teams before the tournament starts. '
            'Must satisfy all allocation rules. Multiple allowed per player. '
            'All mulligans processed in batches depending on how many are bought.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Complete Redraw — €6</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'Full redraw of all 8 teams. Includes tier-balancing. '
            '<strong style="color:#D4A017">Must be completed before the first game kicks off.</strong></p></div>',
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Insurance — €2</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'If either of your original Tier 1 teams is eliminated in the '
            '<strong>Group Stage or Round of 32</strong>, '
            'you receive <strong>+25 points</strong>. Triggers for each team knocked out early '
            '(max +50 if both Tier 1 teams exit before R16). '
            'R16 or later does not qualify.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Ninth Team — €3</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'After the Group Stage, receive one random surviving team you don\'t already own. '
            'Added to your roster for knockout rounds only. '
            'Can be selected as Knockout Captain.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="card"><h4 style="color:#D4A017;margin:0">Resurrection — €5</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.4rem 0 0">'
            'You <strong>choose which of your eliminated teams</strong> gets swapped out. '
            'A replacement is randomly drawn from surviving teams of the same tier. '
            'Replacement earns knockout points only. Maximum one per player.</p></div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("Dark Horse Rules")
    st.markdown("""
- Must be a **Tier 3 or Tier 4** team
- Cannot be a team you already own

| Achievement | Bonus |
|---|---|
| Reaches Quarter Final | +15 |
| Reaches Semi Final | +30 |
| Reaches Final | +40 |
| Wins Tournament | +50 |

Bonuses are cumulative. A Dark Horse that reaches the Final earns **15 + 30 + 40 = 85 pts**. World Cup winner earns **135 pts**.
""")

# ── CAPTAINS ──────────────────────────────────────────────────────────────────
with tab_captains:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="card-gold"><h4 style="color:#D4A017;margin:0">Pre-Tournament Captain</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.5rem 0 0">Free · Must be one of your original 8 teams · '
            'Selected before the opening match</p>'
            '<p style="color:#F5F5F5;margin:0.5rem 0 0">'
            'That team earns <strong>1.5× every point it scores</strong> across the entire tournament — '
            'goals, clean sheets, wins, hat tricks, penalty/comeback wins, upset bonuses, '
            'progression bonuses, and special events all multiplied. '
            'The +50% bonus is applied to the team\'s total points earned in both the group stage and knockout rounds.</p></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            '<div class="card-gold"><h4 style="color:#D4A017;margin:0">Knockout Captain</h4>'
            '<p style="color:#9CA3AF;font-size:0.88rem;margin:0.5rem 0 0">Free · Any surviving team you own · '
            'Selected before the Round of 32</p>'
            '<p style="color:#F5F5F5;margin:0.5rem 0 0">'
            'That team earns <strong>1.5× every point it scores in the knockout rounds</strong> (Round of 32 onward) — '
            'goals, clean sheets, wins, hat tricks, penalty/comeback wins, upset bonuses, and '
            'progression bonuses all multiplied. '
            'Special event bonuses (shirt removals, GK goals, red cards, first eliminated) are excluded from this multiplier. '
            'Cannot be the same team as your Pre-Tournament Captain.</p></div>',
            unsafe_allow_html=True,
        )

    st.info("Captain selections remain hidden until the relevant deadline has passed. A Resurrection replacement does NOT inherit captain status from the team it replaces.")

# ── PRIZES ────────────────────────────────────────────────────────────────────
with tab_prizes:
    st.markdown("100% of all money collected goes into the prize pool.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="card-gold" style="text-align:center"><h2 style="color:#D4A017;margin:0">🥇 50%</h2><p style="color:#9CA3AF;margin:0">1st Place</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card" style="text-align:center"><h2 style="color:#C0C0C0;margin:0">🥈 30%</h2><p style="color:#9CA3AF;margin:0">2nd Place</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="card" style="text-align:center"><h2 style="color:#CD7F32;margin:0">🥉 20%</h2><p style="color:#9CA3AF;margin:0">3rd Place</p></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("""
**Prize Leaderboard** — Paid players only. These are the standings that determine prize money.

**Overall Leaderboard** — All 14 players. Players without a Buy In are shown greyed out and cannot win prizes.
""")

# ── TIEBREAKERS ───────────────────────────────────────────────────────────────
with tab_tiebreakers:
    st.markdown("Applied in order when two or more players finish level on points:")
    for i, (title, desc) in enumerate([
        ("Most Total Goals Scored", "Across all owned teams throughout the tournament."),
        ("Most Teams Reaching QF+", "Count of owned teams that reached the Quarter Final or better."),
        ("Lowest Original Portfolio Strength", "Based on the original draw only. Ninth Teams and Resurrection replacements ignored."),
        ("Random Draw", "Conducted with a logged, reproducible random seed for full transparency."),
    ], 1):
        st.markdown(
            f'<div class="card" style="display:flex;gap:1rem;align-items:flex-start">'
            f'<span style="color:#D4A017;font-size:1.4rem;font-weight:700;min-width:1.5rem">{i}</span>'
            f'<div><p style="color:#F5F5F5;font-weight:600;margin:0">{title}</p>'
            f'<p style="color:#9CA3AF;font-size:0.85rem;margin:0.15rem 0 0">{desc}</p></div></div>',
            unsafe_allow_html=True,
        )

# ── FULL RULES ────────────────────────────────────────────────────────────────
with tab_full:
    _ROOT = Path(__file__).parent.parent.parent
    _RULES = _ROOT / "RULES.md"
    if _RULES.exists():
        with st.expander("View full rules document", expanded=False):
            st.markdown(_RULES.read_text(encoding="utf-8"))
    else:
        st.warning("Rules file not found.")
