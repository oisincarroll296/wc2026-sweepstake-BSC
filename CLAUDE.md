# Sweepstake (Generic) — Project Notes

This is a **generalised fork** of the World Cup 2026 Sweepstake (`c:\World Cup`).

Key differences from the original:
1. **Variable player count** — `config.yaml` sets `participants`; `teams_per_tier` is computed automatically.
2. **Budget system** — each player gets an add-on spending allowance (configured in `config.yaml`).

All other rules, scoring, and architecture are identical to the original.

---

## Quick-start

1. Edit `config.yaml`:
   - Set `participants` to your player count.
   - Set `budget_per_player` to the add-on allowance (0 to disable).
2. Add players to `data/players.csv` (one row per player, `Status` = `UNPAID`).
3. Run the Initial Draw from the Admin page.

```powershell
streamlit run dashboard/app.py
```

---

## Teams-per-tier formula

```
teams_per_tier = max(1, round(24 / n_players))
```

| Players | Teams/tier | Total teams |
|---------|-----------|-------------|
| 6       | 4         | 16          |
| 8       | 3         | 12          |
| 10–13   | 2         | 8           |
| 16–24   | 1–2       | 4–8         |

---

## Budget system

- Configured in `config.yaml` under `sweepstake.budget_per_player` and `sweepstake.addon_costs`.
- `BuyIn` is **not** deducted from the budget.
- Add-on costs (default): PredictionPack €5, Mulligan €3, NinthTeam €3, Resurrection €3, Insurance €2.
- Budget overview shown in Admin → Purchases tab.
- Players can go over budget — the admin sees a warning but it is not hard-blocked.

### `config.yaml` budget section

```yaml
sweepstake:
  budget_per_player: 10
  addon_costs:
    PredictionPack: 5
    Mulligan: 3
    NinthTeam: 3
    Resurrection: 3
    Insurance: 2
```

---

## Architecture

Same as the original. See the original CLAUDE.md for full details.

### Source files

| File | Purpose |
|------|---------|
| `src/team_database.py` | 48-team loader (teams.csv) |
| `src/allocation_engine.py` | Draw engine + variable tier allocation |
| `src/scoring_engine.py` | Full points calculator |
| `src/competition.py` | Competition logic layer |

### Data files

| File | Purpose |
|------|---------|
| `data/teams.csv` | 48-team database with tier + strength scores |
| `data/allocation.csv` | `Player,Team` rows after the Initial Draw |
| `data/players.csv` | One row per player: Status, picks, Budget column |
| `data/purchases.csv` | Purchase ledger — `Player, PurchaseType, Selection, Reference, Timestamp` |
| `data/match_stats.csv` | Per-team stats |
| `data/match_results.csv` | Raw match-by-match results |
| `data/fixtures.csv` | Full fixture list |
| `data/events.csv` | Draw events |
| `data/audit_log.csv` | Full action audit trail |
| `data/score_history.csv` | Historical score snapshots |
| `data/deadlines.json` | Editable deadline timestamps |

---

## config.yaml reference

| Key | Default | Description |
|-----|---------|-------------|
| `sweepstake.participants` | 13 | Number of players |
| `sweepstake.budget_per_player` | 10 | Add-on budget per player (0 = disabled) |
| `sweepstake.addon_costs.*` | various | Cost per purchase type |
| `sweepstake.balance_threshold` | 20 | Max portfolio spread |
| `sweepstake.max_balance_iterations` | 1000 | Balancing iterations |

---

## Tests

```powershell
pytest tests/ -v
```

Note: some tests reference 13-player constants from the original project. Update
`tests/test_allocation_engine.py` fixture if you change the player count significantly.
