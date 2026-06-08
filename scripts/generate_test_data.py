"""Generate fake QF-stage test data for dashboard demonstration."""
import sys, random, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

random.seed(2026)

DATA = ROOT / "data"

# ── QF scenario ──────────────────────────────────────────────────────────────
# 8 teams in QF, 8 eliminated in R16, rest out in group stage / R32
QF_TEAMS  = {"Spain", "France", "Argentina", "Brazil", "England", "Germany", "Morocco", "Norway"}
# Colombia eliminated in group stage — triggers insurance for Harry (who owns Colombia + has insurance)
R16_TEAMS = {"Netherlands", "Belgium", "Portugal", "Croatia", "USA", "Japan", "Uruguay", "South Korea"}
GROUP_WINNERS = {
    "Mexico", "Switzerland", "Brazil", "Germany", "Spain", "France", "Argentina",
    "England", "Belgium", "Portugal", "Netherlands",
    "Norway",  # Norway won Group I — the big upset
}

ROUNDS = {t: "QF" for t in QF_TEAMS}
for t in R16_TEAMS:
    ROUNDS[t] = "R16"

# ── Load teams ────────────────────────────────────────────────────────────────
teams_df = pd.read_csv(DATA / "teams.csv")

def rng(lo, hi): return random.randint(lo, hi)

# ── Build match_stats ─────────────────────────────────────────────────────────
rows = []
for _, row in teams_df.iterrows():
    team = str(row["Team"])
    tier = int(row.get("Tier", 4))
    reached = ROUNDS.get(team, "GroupStage")
    gwinner = 1 if team in GROUP_WINNERS else 0

    # Group stage stats (3 matches)
    if reached == "QF":
        gg, gcs = rng(7, 13), rng(1, 3)
        kg, kcs = rng(3, 6), rng(1, 2)
        gpw, gcw = (rng(0,1) if tier>=3 else 0), rng(0, 1)
        kpw, kcw = 0, rng(0, 1)
    elif reached == "R16":
        gg, gcs = rng(5, 10), rng(1, 3)
        kg, kcs = rng(1, 3), rng(0, 1)
        gpw, gcw = (rng(0,1) if tier>=3 else 0), rng(0, 1)
        kpw, kcw = 0, 0
    else:
        gg, gcs = rng(1, 7), rng(0, 2)
        kg, kcs = 0, 0
        gpw, gcw = 0, 0
        kpw, kcw = 0, 0
        gwinner = 0

    # Norway is the T3 dark horse — give her a scrappy run
    if team == "Norway":
        gg, gcs = 5, 2
        kg, kcs = 3, 1
        gpw, gcw = 0, 1
        kpw, kcw = 1, 0  # penalty win in R16!
        gwinner = 1

    rows.append({
        "Team": team,
        "GroupGoals": gg, "GroupCleanSheets": gcs,
        "GroupPenaltyWins": gpw, "GroupComebackWins": gcw,
        "GroupWinner": gwinner,
        "KnockoutGoals": kg, "KnockoutCleanSheets": kcs,
        "KnockoutPenaltyWins": kpw, "KnockoutComebackWins": kcw,
        "RoundReached": reached,
    })

ms = pd.DataFrame(rows)
ms.to_csv(DATA / "match_stats.csv", index=False)
print(f"✓ match_stats.csv — {len(ms)} teams")

# ── Player status + picks — all in players.csv ────────────────────────────────
now = "2026-06-01T10:00:00+01:00"
players_path = DATA / "players.csv"
players_df = pd.read_csv(players_path, dtype=str).fillna("")
players_df["Status"] = "PAID"
players_df["PaidTimestamp"] = now

# Captain + prediction picks (must match players in the CSV)
PICKS = {
    "Guilly":  dict(PreTournamentCaptain="Spain",     KnockoutCaptain="England",   WorldCupWinner="Spain",     GoldenBoot="Lamine Yamal",  DarkHorse="Norway"),
    "Campo":   dict(PreTournamentCaptain="France",    KnockoutCaptain="Germany",   WorldCupWinner="France",    GoldenBoot="Mbappe",         DarkHorse="Norway"),
    "Aod":     dict(PreTournamentCaptain="Brazil",    KnockoutCaptain="Spain",     WorldCupWinner="Brazil",    GoldenBoot="Vinicius Jr",    DarkHorse="Czech Republic"),
    "Moorsey": dict(PreTournamentCaptain="Argentina", KnockoutCaptain="Morocco",   WorldCupWinner="Argentina", GoldenBoot="Lionel Messi",   DarkHorse="Morocco"),
    "Harry":   dict(PreTournamentCaptain="Argentina", KnockoutCaptain="England",   WorldCupWinner="Argentina", GoldenBoot="Lionel Messi",   DarkHorse="Algeria"),
    "Jack C":  dict(PreTournamentCaptain="Argentina", KnockoutCaptain="France",    WorldCupWinner="Argentina", GoldenBoot="Julián Álvarez", DarkHorse="Panama"),
    "Oisin C": dict(PreTournamentCaptain="Morocco",   KnockoutCaptain="Norway",    WorldCupWinner="Morocco",   GoldenBoot="Hakimi",         DarkHorse="Algeria"),
    "Ronan":   dict(PreTournamentCaptain="Brazil",    KnockoutCaptain="Spain",     WorldCupWinner="Brazil",    GoldenBoot="Rodrygo",        DarkHorse="Scotland"),
    "Oisin E": dict(PreTournamentCaptain="England",   KnockoutCaptain="France",    WorldCupWinner="England",   GoldenBoot="Harry Kane",     DarkHorse="Norway"),
    "Wheelo":  dict(PreTournamentCaptain="Portugal",  KnockoutCaptain="Norway",    WorldCupWinner="Portugal",  GoldenBoot="Ronaldo",        DarkHorse="Czech Republic"),
    "Mcgree":  dict(PreTournamentCaptain="Belgium",   KnockoutCaptain="Germany",   WorldCupWinner="France",    GoldenBoot="Mbappe",         DarkHorse="Panama"),
    "Ian":     dict(PreTournamentCaptain="France",    KnockoutCaptain="Argentina", WorldCupWinner="France",    GoldenBoot="Mbappe",         DarkHorse="Egypt"),
}
pick_cols = ["PreTournamentCaptain", "KnockoutCaptain", "WorldCupWinner", "GoldenBoot", "DarkHorse"]
for col in pick_cols:
    if col not in players_df.columns:
        players_df[col] = ""
for player, picks in PICKS.items():
    mask = players_df["Player"] == player
    for col, val in picks.items():
        players_df.loc[mask, col] = val

players_df.to_csv(players_path, index=False)
PLAYERS = players_df["Player"].tolist()
print(f"✓ players.csv — {len(players_df)} players marked PAID with picks")

# ── Purchases (no Amount, no Status) ─────────────────────────────────────────
purchases = []

# Everyone buys in
for p in PLAYERS:
    purchases.append({
        "Player": p, "PurchaseType": "BuyIn", "Selection": "",
        "Reference": f"{p} - BUY IN", "Timestamp": "2026-06-01T10:00:00+01:00",
    })

# Most buy prediction pack
pack_players = [p for p in PLAYERS if p not in {"Lobber"}]
for p in pack_players:
    purchases.append({
        "Player": p, "PurchaseType": "PredictionPack", "Selection": "",
        "Reference": f"{p} - PREDICTION PACK", "Timestamp": "2026-06-01T11:00:00+01:00",
    })

# Some buy insurance (Tier 1 owners who might get hit)
insurance_players = ["Aod", "Oisin C", "Moorsey", "Guilly", "Campo", "Harry", "Wheelo"]
for p in insurance_players:
    purchases.append({
        "Player": p, "PurchaseType": "Insurance", "Selection": "",
        "Reference": f"{p} - INSURANCE", "Timestamp": "2026-06-02T09:00:00+01:00",
    })

# A few mulligans taken before tournament
for p in ["Jack C", "Lobber"]:
    purchases.append({
        "Player": p, "PurchaseType": "Mulligan", "Selection": "",
        "Reference": f"{p} - MULLIGAN", "Timestamp": "2026-06-08T15:00:00+01:00",
    })

# Some ninth teams (post group stage) — Selection = team drawn
ninth_draws = {"Oisin E": "Sweden", "Harry": "Austria", "Ronan": "Senegal"}
for p, team in ninth_draws.items():
    purchases.append({
        "Player": p, "PurchaseType": "NinthTeam", "Selection": team,
        "Reference": f"{p} - NINTH TEAM", "Timestamp": "2026-06-28T16:00:00+01:00",
    })

# One resurrection — Selection = "EliminatedTeam->ReplacementTeam"
purchases.append({
    "Player": "Mcgree", "PurchaseType": "Resurrection", "Selection": "Colombia->Austria",
    "Reference": "Mcgree - RESURRECTION", "Timestamp": "2026-06-28T18:00:00+01:00",
})

pd.DataFrame(purchases).to_csv(DATA / "purchases.csv", index=False)
print(f"✓ purchases.csv — {len(purchases)} purchase records")

# ── Lock predictions via deadlines.json ───────────────────────────────────────
deadlines_path = ROOT / "data" / "deadlines.json"
if deadlines_path.exists():
    with open(deadlines_path) as f:
        dl = json.load(f)
else:
    dl = {}
dl["prediction_lock"] = "2026-06-11T19:00:00+01:00"
dl["buy_in_deadline"] = "2026-06-27T21:00:00+01:00"
with open(deadlines_path, "w") as f:
    json.dump(dl, f, indent=2)
print("✓ deadlines.json — prediction_lock and buy_in_deadline set")

# ── Events ────────────────────────────────────────────────────────────────────
events = [
    {"EventID": "EVT001", "EventType": "INITIAL_DRAW",      "Status": "EXECUTED",  "RandomSeed": 2026, "ScheduledTime": "2026-06-07T18:00:00+01:00", "ExecutedTime": "2026-06-07T18:05:00+01:00"},
    {"EventID": "EVT002", "EventType": "GROUP_STAGE_CLOSE",  "Status": "EXECUTED",  "RandomSeed": "",   "ScheduledTime": "2026-06-27T21:00:00+01:00", "ExecutedTime": "2026-06-27T21:30:00+01:00"},
    {"EventID": "EVT003", "EventType": "NINTH_TEAM_DRAW",    "Status": "EXECUTED",  "RandomSeed": 42,   "ScheduledTime": "2026-06-28T16:00:00+01:00", "ExecutedTime": "2026-06-28T16:10:00+01:00"},
    {"EventID": "EVT004", "EventType": "RESURRECTION_DRAW",  "Status": "EXECUTED",  "RandomSeed": 99,   "ScheduledTime": "2026-06-28T18:00:00+01:00", "ExecutedTime": "2026-06-28T18:05:00+01:00"},
    {"EventID": "EVT005", "EventType": "TOURNAMENT_COMPLETE","Status": "SCHEDULED", "RandomSeed": "",   "ScheduledTime": "2026-07-19T20:00:00+01:00", "ExecutedTime": ""},
]
pd.DataFrame(events).to_csv(DATA / "events.csv", index=False)
print(f"✓ events.csv — {len(events)} events")

# ── Audit log snippet ─────────────────────────────────────────────────────────
audit = [
    {"Timestamp": "2026-06-07T18:05:00+01:00", "Event": "INITIAL_DRAW",     "Player": "ALL",     "Action": "DRAW",    "Result": "OK — 13 players allocated"},
    {"Timestamp": "2026-06-07T18:10:00+01:00", "Event": "BUYIN_LOCK",       "Player": "ALL",     "Action": "LOCK",    "Result": "OK — 13 paid"},
    {"Timestamp": "2026-06-11T19:00:00+01:00", "Event": "PREDICTION_LOCK",  "Player": "ALL",     "Action": "LOCK",    "Result": "OK — 12 packs submitted"},
    {"Timestamp": "2026-06-27T21:30:00+01:00", "Event": "GROUP_STAGE_CLOSE","Player": "ALL",     "Action": "CLOSE",   "Result": "OK — 32 teams qualify"},
    {"Timestamp": "2026-06-28T16:10:00+01:00", "Event": "NINTH_TEAM_DRAW",  "Player": "Oisin E", "Action": "ASSIGN",  "Result": "Sweden assigned"},
    {"Timestamp": "2026-06-28T16:10:00+01:00", "Event": "NINTH_TEAM_DRAW",  "Player": "Harry",   "Action": "ASSIGN",  "Result": "Austria assigned"},
    {"Timestamp": "2026-06-28T16:10:00+01:00", "Event": "NINTH_TEAM_DRAW",  "Player": "Ronan",   "Action": "ASSIGN",  "Result": "Senegal assigned"},
    {"Timestamp": "2026-06-28T18:05:00+01:00", "Event": "RESURRECTION_DRAW","Player": "Mcgree",  "Action": "ASSIGN",  "Result": "Colombia (T2) → Austria"},
]
pd.DataFrame(audit).to_csv(DATA / "audit_log.csv", index=False)
print(f"✓ audit_log.csv — {len(audit)} records")

# ── A few match results (to show the system works) ────────────────────────────
sample_results = [
    # Group C: Brazil 3-0 Morocco, Scotland 1-2 Brazil, Morocco 4-0 Haiti
    {"match_number": 7,  "home_goals": 3, "away_goals": 1, "extra_time": 0, "penalty_winner": "", "comeback_home": 0, "comeback_away": 0},
    {"match_number": 29, "home_goals": 4, "away_goals": 0, "extra_time": 0, "penalty_winner": "", "comeback_home": 0, "comeback_away": 0},
    {"match_number": 49, "home_goals": 1, "away_goals": 2, "extra_time": 0, "penalty_winner": "", "comeback_home": 1, "comeback_away": 0},
    # Group H: Spain 3-0 Cabo Verde
    {"match_number": 14, "home_goals": 3, "away_goals": 0, "extra_time": 0, "penalty_winner": "", "comeback_home": 0, "comeback_away": 0},
    # Group I: France 2-0 Senegal
    {"match_number": 17, "home_goals": 2, "away_goals": 0, "extra_time": 0, "penalty_winner": "", "comeback_home": 0, "comeback_away": 0},
]
pd.DataFrame(sample_results).to_csv(DATA / "match_results.csv", index=False)
print(f"✓ match_results.csv — {len(sample_results)} results entered")

# ── Score history (cumulative points by gameweek for line chart) ──────────────
FINAL_SCORES = {
    "Campo":   176, "Oisin E": 175, "Oisin C": 173, "Guilly": 169,
    "Harry":   155, "Moorsey": 151, "Ronan":   147, "Aod":    143,
    "Ian":     132, "Jack C":  128, "Lobber":  117, "Wheelo": 109, "Mcgree": 98,
}
gameweeks  = ["2026-06-11", "2026-06-18", "2026-06-25", "2026-07-01", "2026-07-09"]
gw_weights = [0.28, 0.44, 0.59, 0.74, 1.00]

history_rows = []
for player in PLAYERS:
    final = FINAL_SCORES.get(player, 120)
    seed_p = sum(ord(c) for c in player)
    rng_p  = random.Random(2026 + seed_p)
    for gw_date, weight in zip(gameweeks, gw_weights):
        jitter = rng_p.uniform(-0.03, 0.03)
        cum_pts = round(final * max(0.0, weight + jitter), 1)
        history_rows.append({"Date": gw_date, "Player": player, "Points": cum_pts})

pd.DataFrame(history_rows).to_csv(DATA / "score_history.csv", index=False)
print(f"✓ score_history.csv — {len(history_rows)} rows ({len(PLAYERS)} players × {len(gameweeks)} gameweeks)")

print("\n✅ Done! Dashboard is ready for QF-stage demo.")
print(f"   QF teams: {sorted(QF_TEAMS)}")
