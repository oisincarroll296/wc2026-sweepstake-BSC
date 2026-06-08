# World Cup 2026 Sweepstake - Project Notes

## Live App
**https://fellas-wc2026-sweepstake.streamlit.app/**

Private GitHub repo: `oisincarroll296/wc2026-sweepstake`  
Push to `master` → Streamlit Cloud auto-redeploys in ~30 s.

---

## Architecture

This is a **Python + Streamlit** application. The Excel/VBA approach was replaced entirely.

### Source files

| File | Purpose |
|------|---------|
| `src/team_database.py` | 48-team loader (teams.csv) |
| `src/allocation_engine.py` | Draw engine + tier-aware balancing |
| `src/scoring_engine.py` | Full points calculator (teams, captains, insurance, predictions) |
| `src/competition.py` | Competition logic layer |

### Dashboard files

| File | Purpose |
|------|---------|
| `dashboard/app.py` | Streamlit entry point — registers all pages |
| `dashboard/data.py` | All cached data loaders + `save_match_result_and_recalculate()` |
| `dashboard/config.py` | `TIER_COLORS`, `COLORS` constants |
| `dashboard/components/ui.py` | Shared UI helpers (`page_header`, `empty_state`, etc.) |
| `dashboard/pages/home.py` | Overview: prize pool, countdown, top team, recent log |
| `dashboard/pages/prize_leaderboard.py` | PAID players only, includes Potential column |
| `dashboard/pages/overall_leaderboard.py` | All 13 players, payment status |
| `dashboard/pages/player_portfolios.py` | Per-player portfolio, H2H comparison, insurance status |
| `dashboard/pages/analytics.py` | Charts: goals, form, remaining potential, insurance tracker, captains |
| `dashboard/pages/bracket.py` | Knockout bracket coloured by tier, all owners listed |
| `dashboard/pages/admin.py` | Password-protected: result entry, who-benefits panel |
| `dashboard/pages/predictions_centre.py` | Prediction picks overview |

### Data files (all committed to git — private repo)

| File | Purpose |
|------|---------|
| `data/teams.csv` | 48-team database with tier + strength scores |
| `data/allocation.csv` | `Player,Team` — 13 players × 8 teams each |
| `data/match_stats.csv` | Per-team stats: goals, CS, penalty/comeback wins, RoundReached |
| `data/match_results.csv` | Raw match-by-match result entries |
| `data/fixtures.csv` | Full fixture list with match numbers |
| `data/purchases.csv` | Purchase ledger — columns: `Player, PurchaseType, Selection, Reference, Timestamp` |
| `data/players.csv` | One row per player: Status, PaidTimestamp, PreTournamentCaptain, KnockoutCaptain, WorldCupWinner, GoldenBoot, DarkHorse |
| `data/events.csv` | Draw events (INITIAL_DRAW, GROUP_STAGE_CLOSE, etc.) |
| `data/audit_log.csv` | Full action audit trail |
| `data/score_history.csv` | Historical score snapshots (`Date,Player,Points`) |
| `data/deadlines.json` | Editable deadline timestamps |

---

## Team Database

- **Source**: FIFA official draw pots (December 2025)
- **48 teams** across 4 tiers of 12
- **Tier assignment**: ranked by FIFA position among the 48 qualifiers
- **Strength Score** = `101 - FIFA Rank`

### Teams by Tier

**Tier 1** (FIFA ranks 1-11, 13): Spain, Argentina, France, England, Brazil, Portugal, Netherlands, Belgium, Germany, Croatia, Morocco, Colombia

**Tier 2** (ranks 14-27 excl gaps): USA, Mexico, Uruguay, Switzerland, Japan, Senegal, Iran, South Korea, Ecuador, Austria, Australia, Canada

**Tier 3** (ranks 29-50 excl gaps): Norway, Panama, Sweden, Egypt, Algeria, Scotland, Turkey, Paraguay, Tunisia, Ivory Coast, Czech Republic, Uzbekistan

**Tier 4** (ranks 51-86 excl gaps): Qatar, Saudi Arabia, South Africa, DR Congo, Jordan, Iraq, Cape Verde, Ghana, Bosnia and Herzegovina, Curacao, Haiti, New Zealand

---

## Allocation Rules

- 13 participants, 8 teams each (2 per tier)
- Each team appears 2-3 times across all participants
- Balance threshold: max portfolio - min portfolio <= 20 pts
- Balancing uses iterative tier-aware swapping (max 1000 iterations)

---

## Scoring Engine (`src/scoring_engine.py`)

### Match points

| Event | Points |
|-------|--------|
| Goal scored | 1 pt |
| Clean sheet | 2 pts |
| Penalty shootout win | 3 pts |
| Comeback win (not pens) | 3 pts |
| Group stage winner | 3 pts |

### Progression bonuses (cumulative per round cleared)

| Tier | R16 | QF | SF | Final | Winner |
|------|-----|----|----|-------|--------|
| T1   | 2   | 4  | 8  | 12    | 20     |
| T2   | 4   | 8  | 12 | 18    | 28     |
| T3   | 8   | 15 | 20 | 32    | 46     |
| T4   | 12  | 25 | 30 | 45    | 65     |

### Captain bonuses
- **Pre-Tournament captain**: +0.5 × team's total points (all stages)
- **Knockout captain**: +0.5 × team's knockout points only
- Same team cannot be both captains

### Insurance
- `+25 pts` per Tier 1 team eliminated before R16 (max +50 if both out)
- Only original 8-team allocation counts (not Ninth/Resurrection)

### Dark Horse bonuses (cumulative)
| Round reached | Bonus |
|--------------|-------|
| QF           | +15   |
| SF           | +30   |
| Final        | +40   |
| Winner       | +50   |

### Prediction Pack bonuses
- WC Winner correct: +30 pts
- Golden Boot correct: +25 pts

### Round order
`GroupStage → R16 → QF → SF → Final → Winner`

---

## Purchase Types

`purchases.csv` columns: `Player, PurchaseType, Amount, Selection, Reference, Timestamp, Status`

| PurchaseType | Amount | Selection field |
|-------------|--------|-----------------|
| `BuyIn` | €5 | (empty) |
| `PredictionPack` | €5 | (empty) |
| `Mulligan` | €3 | (empty) |
| `NinthTeam` | €3 | Team name e.g. `"Japan"` |
| `Resurrection` | €5 | `"EliminatedTeam->ReplacementTeam"` |
| `Insurance` | €2 | (empty) |

> **Important**: PurchaseType casing must match exactly — the scoring engine does case-sensitive lookups.

---

## Rule Decisions (final)

| Rule | Decision |
|------|----------|
| Insurance bonus | +25 pts per Tier 1 team eliminated before R16 (max +50 if both out) |
| Mulligan | Full redraw of all 8 teams; must pass all allocation rules |
| Buy-in deadline | Before last group game kicks off |
| Payment references | `"PLAYER - BUY IN, PREDICTION PACK"` |
| Prize Leaderboard | PAID players only (eligible for prizes) |
| Overall Leaderboard | All players, shows payment status |
| Dark Horse | Must be Tier 3 or 4; cannot be a team the player owns |
| Ninth Team | Random surviving unowned team; adds to knockout roster only |
| Resurrection | Same tier, surviving, unowned replacement; once only |
| Tiebreaker 1 | Most goals scored by owned teams |
| Tiebreaker 2 | Most owned teams reaching QF+ |
| Tiebreaker 3 | Coin toss (seeded random) |
| Comeback Win | Won in normal/extra time after being behind; NOT penalty wins |
| Prediction lock | 1 hour before opening match |

---

## Prices

| Purchase | Cost |
|----------|------|
| Buy In | €5 |
| Prediction Pack | €5 |
| Mulligan | €3 |
| Ninth Team | €3 |
| Resurrection | €5 |
| Insurance | €2 |

---

## Colour Scheme

| Element | RGB |
|---------|-----|
| Header BG | 13, 27, 42 (near-black) |
| Header FG | 212, 160, 23 (gold) |
| Tier 1 | 16, 90, 172 (blue) |
| Tier 2 | 21, 128, 61 (green) |
| Tier 3 | 161, 98, 7 (amber) |
| Tier 4 | 185, 28, 28 (red) |
| Score BG | 30, 41, 59 (dark blue) |

---

## Day-to-day workflow (entering results)

1. Run locally: `streamlit run dashboard/app.py`
2. Admin page → Results Entry → enter match scores
3. Push to GitHub:
   ```powershell
   git add data/
   git commit -m "Update scores: 2026-MM-DD"
   git push
   ```
4. Streamlit Cloud redeploys in ~30 s.

Admin password: set in Streamlit Cloud Secrets as `ADMIN_PASSWORD` (default: `wc2026admin`).

---

## Tests

```powershell
pytest tests/ -v
```

Key test files:
- `tests/test_scoring_engine.py` — unit tests for scoring functions
- `tests/test_rules_alignment.py` — 100 rule-alignment tests
- `tests/test_event_engine.py` — draw event tests (ninth team, resurrection, etc.)

All 589 tests pass as of last run.
