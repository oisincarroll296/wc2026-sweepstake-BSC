#!/usr/bin/env python3
"""
WC 2026 Sweepstake — Monte Carlo fairness simulation.

Runs 20 independent World Cup outcomes with a realistic mix of participant
purchases and measures whether the scoring system is fair and competitive.

Results are saved to simulations/results/.
Run from the project root:
    python simulations/simulate.py
"""

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
RESULTS_DIR = ROOT / "simulations" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

import pandas as pd
import numpy as np

from src.team_database import load_teams
from src.allocation_engine import generate_allocations
from src.scoring_engine import (
    calculate_player_points, PROGRESSION_BONUSES, DARK_HORSE_BONUSES,
    CAPTAIN_MULTIPLIER, INSURANCE_BONUS,
    PREDICTION_WINNER_BONUS, PREDICTION_GOLDEN_BOOT_BONUS,
)
from src.competition import purchases_to_scoring_format

# ── Constants ────────────────────────────────────────────────────────────────

PARTICIPANTS = [
    "Alice", "Bob", "Carol", "David", "Emma",
    "Frank", "Grace", "Henry", "Iris", "Jack",
    "Kate", "Liam", "Mia",
]
N = 20   # number of simulations

# Probabilities of each purchase type (per player, independent)
P_PACK        = 0.70   # prediction pack
P_INSURANCE   = 0.55   # insurance
P_NINTH       = 0.45   # ninth team
P_RESURRECTION= 0.25   # resurrection

# ---------------------------------------------------------------------------
# Tournament simulation
# ---------------------------------------------------------------------------

def _poisson(rate: float, rng: random.Random) -> int:
    """Knuth Poisson sampler."""
    L = math.exp(-max(0.05, rate))
    k, p = 0, 1.0
    while p > L:
        p *= rng.random()
        k += 1
    return k - 1


def simulate_tournament(seed: int, teams_df: pd.DataFrame) -> pd.DataFrame:
    """Return a full match_stats DataFrame for one simulated tournament."""
    rng = random.Random(seed)
    strengths = dict(zip(teams_df["Team"], teams_df["StrengthScore"].astype(float)))
    groups_map: dict[str, list[str]] = (
        teams_df.groupby("Group")["Team"].apply(list).to_dict()
    )

    stats: dict[str, dict] = {
        t: {
            "Team": t,
            "GroupGoals": 0, "GroupCleanSheets": 0,
            "GroupPenaltyWins": 0, "GroupComebackWins": 0,
            "GroupWinner": 0, "RoundReached": "GroupStage",
            "KnockoutGoals": 0, "KnockoutCleanSheets": 0,
            "KnockoutPenaltyWins": 0, "KnockoutComebackWins": 0,
        }
        for t in teams_df["Team"]
    }

    # ── Group stage (round-robin within each group) ──────────────────────────
    group_standings: dict[str, list[str]] = {}

    for group, members in sorted(groups_map.items()):
        gscores: dict[str, dict] = {t: {"pts": 0, "gd": 0} for t in members}

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                t1, t2 = members[i], members[j]
                g1 = _poisson(strengths[t1] / 27.0, rng)
                g2 = _poisson(strengths[t2] / 27.0, rng)

                stats[t1]["GroupGoals"] += g1
                stats[t2]["GroupGoals"] += g2
                gscores[t1]["gd"] += g1 - g2
                gscores[t2]["gd"] += g2 - g1

                if g1 > g2:
                    gscores[t1]["pts"] += 3
                elif g2 > g1:
                    gscores[t2]["pts"] += 3
                else:
                    gscores[t1]["pts"] += 1
                    gscores[t2]["pts"] += 1

                if g2 == 0:
                    stats[t1]["GroupCleanSheets"] += 1
                if g1 == 0:
                    stats[t2]["GroupCleanSheets"] += 1

                # Comeback wins (~10% of decisive matches)
                if g1 > g2 and rng.random() < 0.10:
                    stats[t1]["GroupComebackWins"] += 1
                elif g2 > g1 and rng.random() < 0.10:
                    stats[t2]["GroupComebackWins"] += 1

        ranked = sorted(
            members,
            key=lambda t: (-gscores[t]["pts"], -gscores[t]["gd"]),
        )
        group_standings[group] = ranked
        stats[ranked[0]]["GroupWinner"] = 1

    # ── Determine R16 qualifiers ──────────────────────────────────────────────
    # Top 2 from each group (24) + best 8 third-place teams (8) = 32
    r16: list[str] = []
    third_place: list[tuple[str, int, int]] = []  # (team, pts, gd)

    for group, ranked in group_standings.items():
        r16.extend([ranked[0], ranked[1]])
        g = ranked[2]
        gscores2 = {t: {"pts": 0, "gd": 0} for t in [g]}
        # Re-derive pts for 3rd place (approximation: position rank is sufficient)
        third_place.append((g, 3 - group_standings[group].index(g), 0))

    third_place.sort(key=lambda x: -x[1])
    for t, _, _ in third_place[:8]:
        r16.append(t)

    for t in r16:
        stats[t]["RoundReached"] = "R16"

    # ── Knockout rounds ────────────────────────────────────────────────────────
    def _ko_match(a: str, b: str) -> str:
        sa, sb = strengths[a], strengths[b]
        # Dampen favourite probability to allow upsets
        raw = sa / (sa + sb)
        prob_a = raw * 0.80 + 0.10  # compress toward 50%

        for team in (a, b):
            rate = strengths[team] / 38.0
            stats[team]["KnockoutGoals"]      += _poisson(rate, rng)
            stats[team]["KnockoutCleanSheets"] += (1 if rng.random() < 0.27 else 0)
            stats[team]["KnockoutPenaltyWins"] += (1 if rng.random() < 0.07 else 0)
            stats[team]["KnockoutComebackWins"]+= (1 if rng.random() < 0.09 else 0)

        return a if rng.random() < prob_a else b

    def _run_round(teams: list[str], label: str) -> list[str]:
        rng.shuffle(teams)
        winners = [_ko_match(teams[i], teams[i + 1]) for i in range(0, len(teams), 2)]
        for t in winners:
            stats[t]["RoundReached"] = label
        return winners

    qf = _run_round(list(r16),   "QF")    # 32→16
    sf = _run_round(qf,           "SF")    # 16→8
    fn = _run_round(sf,           "Final") # 8→4
    # Championship final: 2 of the 4 play for gold
    rng.shuffle(fn)
    champion = _ko_match(fn[0], fn[1])
    stats[champion]["RoundReached"] = "Winner"
    # fn[2] and fn[3] play 3rd-place; their RoundReached stays "Final"

    return pd.DataFrame(list(stats.values()))


# ---------------------------------------------------------------------------
# Participant data builders
# ---------------------------------------------------------------------------

def make_statuses(participants: list[str]) -> pd.DataFrame:
    return pd.DataFrame([
        {"Player": p, "Status": "PAID", "PaidTimestamp": "2026-06-01T00:00:00+00:00"}
        for p in participants
    ])


def make_purchases(
    participants: list[str],
    allocation,
    match_stats: pd.DataFrame,
    tier_map: dict[str, int],
    rng: random.Random,
) -> pd.DataFrame:
    ts = "2026-06-01T00:00:00+00:00"
    rows: list[dict] = []
    surviving = set(
        match_stats.loc[match_stats["RoundReached"] != "GroupStage", "Team"].tolist()
    )
    eliminated = set(
        match_stats.loc[match_stats["RoundReached"] == "GroupStage", "Team"].tolist()
    )

    for p in participants:
        rows.append({"Player": p, "PurchaseType": "BUYIN", "Status": "PROCESSED",
                     "Timestamp": ts, "Reference": f"{p} - BUY IN", "Selection": ""})

        if rng.random() < P_PACK:
            rows.append({"Player": p, "PurchaseType": "PACK", "Status": "PROCESSED",
                         "Timestamp": ts, "Reference": f"{p} - PREDICTION PACK", "Selection": ""})

        if rng.random() < P_INSURANCE:
            rows.append({"Player": p, "PurchaseType": "INSURANCE", "Status": "PROCESSED",
                         "Timestamp": ts, "Reference": f"{p} - INSURANCE", "Selection": ""})

        base_owned = set(allocation.assignments.get(p, []))

        if rng.random() < P_NINTH:
            candidates = [t for t in surviving if t not in base_owned]
            if candidates:
                chosen = rng.choice(candidates)
                rows.append({"Player": p, "PurchaseType": "NINTH", "Status": "PROCESSED",
                             "Timestamp": ts, "Reference": f"{p} - NINTH TEAM",
                             "Selection": chosen})

        if rng.random() < P_RESURRECTION:
            elim_owned = [t for t in base_owned if t in eliminated]
            if elim_owned:
                elim = rng.choice(elim_owned)
                etier = tier_map.get(elim, 1)
                repl_candidates = [
                    t for t in surviving
                    if tier_map.get(t) == etier and t not in base_owned
                ]
                if repl_candidates:
                    repl = rng.choice(repl_candidates)
                    rows.append({"Player": p, "PurchaseType": "RESURRECTION",
                                 "Status": "PROCESSED",
                                 "Timestamp": ts, "Reference": f"{p} - RESURRECTION",
                                 "Selection": f"{elim}->{repl}"})

    return pd.DataFrame(rows)


def make_captains(participants: list[str], allocation, rng: random.Random) -> pd.DataFrame:
    rows: list[dict] = []
    for p in participants:
        teams = allocation.assignments.get(p, [])
        if not teams:
            continue
        rows.append({"Player": p, "CaptainType": "PreTournament",
                     "Team": rng.choice(teams)})
        if rng.random() < 0.80:
            rows.append({"Player": p, "CaptainType": "Knockout",
                         "Team": rng.choice(teams)})
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Player", "CaptainType", "Team"]
    )


def make_predictions(
    participants: list[str],
    allocation,
    match_stats: pd.DataFrame,
    purchases: pd.DataFrame,
    tier_map: dict[str, int],
    rng: random.Random,
) -> pd.DataFrame:
    pack_buyers = set(
        purchases.loc[purchases["PurchaseType"] == "PACK", "Player"].tolist()
    )
    winner_rows = match_stats[match_stats["RoundReached"] == "Winner"]
    actual_winner = winner_rows.iloc[0]["Team"] if not winner_rows.empty else ""
    all_teams = match_stats["Team"].tolist()
    t34 = [t for t in all_teams if tier_map.get(t, 1) >= 3]

    rows: list[dict] = []
    for p in pack_buyers:
        owned = set(allocation.assignments.get(p, []))
        wc_pick = actual_winner if rng.random() < 0.12 else rng.choice(all_teams)
        gb_pick = rng.choice(all_teams)
        dh_candidates = [t for t in t34 if t not in owned]
        dh_pick = rng.choice(dh_candidates) if dh_candidates else ""
        rows.append({"Player": p, "WorldCupWinner": wc_pick,
                     "GoldenBoot": gb_pick, "DarkHorse": dh_pick})

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Player", "WorldCupWinner", "GoldenBoot", "DarkHorse"]
    )


def make_tournament_results(match_stats: pd.DataFrame, tier_map: dict) -> dict:
    winner_rows = match_stats[match_stats["RoundReached"] == "Winner"]
    winner = winner_rows.iloc[0]["Team"] if not winner_rows.empty else ""

    tmp = match_stats.copy()
    tmp["TotalGoals"] = tmp["GroupGoals"].astype(float) + tmp["KnockoutGoals"].astype(float)
    gb_winner = tmp.sort_values("TotalGoals", ascending=False).iloc[0]["Team"]

    dh_rounds = {
        str(r["Team"]): str(r["RoundReached"])
        for _, r in match_stats.iterrows()
        if tier_map.get(str(r["Team"]), 1) >= 3
    }
    return {
        "world_cup_winner": winner,
        "golden_boot_winner": gb_winner,
        "dark_horse_rounds": dh_rounds,
    }


# ---------------------------------------------------------------------------
# Score analysis helpers
# ---------------------------------------------------------------------------

def _gini(values: list[float]) -> float:
    """Gini coefficient for a list of scores (0=equal, 1=max inequality)."""
    v = sorted(values)
    n = len(v)
    if n == 0 or sum(v) == 0:
        return 0.0
    cum = sum((2 * i - n - 1) * x for i, x in enumerate(v, 1))
    return cum / (n * sum(v))


def breakdown_tier_contributions(
    participants: list[str],
    allocation,
    match_stats: pd.DataFrame,
    tier_map: dict,
) -> dict[str, float]:
    """Average points contributed per player by each tier."""
    from src.scoring_engine import calculate_team_points
    tier_pts: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
    for p in participants:
        for team in allocation.assignments.get(p, []):
            tier = tier_map.get(team, 1)
            pts = calculate_team_points(team, match_stats, tier)["total"]
            tier_pts[tier].append(pts)
    return {f"T{k}": round(sum(v) / len(v), 2) if v else 0.0 for k, v in tier_pts.items()}


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------

def run_all() -> None:
    teams_df = load_teams()
    tier_map = dict(zip(teams_df["Team"], teams_df["Tier"].astype(int)))

    print(f"Running {N} simulations for {len(PARTICIPANTS)} participants …\n")

    master_seed = 42
    allocation_rng = random.Random(master_seed)
    random.seed(master_seed)
    allocation = generate_allocations(PARTICIPANTS)
    random.seed(None)

    all_rows: list[dict] = []   # one row per (sim, player) for summary
    per_sim_meta: list[dict] = []

    for sim_id in range(1, N + 1):
        sim_seed = master_seed * 1000 + sim_id
        sim_rng  = random.Random(sim_seed)

        match_stats = simulate_tournament(sim_seed, teams_df)
        winner_row  = match_stats[match_stats["RoundReached"] == "Winner"]
        wc_winner   = winner_row.iloc[0]["Team"] if not winner_row.empty else "Unknown"
        winner_tier = tier_map.get(wc_winner, 0)

        purchases  = make_purchases(PARTICIPANTS, allocation, match_stats, tier_map, sim_rng)
        captains   = make_captains(PARTICIPANTS, allocation, sim_rng)
        predictions = make_predictions(PARTICIPANTS, allocation, match_stats, purchases, tier_map, sim_rng)
        statuses   = make_statuses(PARTICIPANTS)
        t_results  = make_tournament_results(match_stats, tier_map)

        scoring_purch = purchases_to_scoring_format(purchases)

        # Score every player
        player_scores: list[dict] = []
        for p in PARTICIPANTS:
            result = calculate_player_points(
                p, allocation.assignments, match_stats,
                scoring_purch, captains, predictions,
                tournament_results=t_results, tier_map=tier_map,
            )
            player_scores.append({
                "Sim":         sim_id,
                "Player":      p,
                "Total":       round(result.get("grand_total", 0), 1),
                "Base":        round(result.get("base_total", 0), 1),
                "CaptainBonus":round(result.get("captain", {}).get("total", 0), 1),
                "InsBonus":    round(result.get("insurance_bonus", 0), 1),
                "PredBonus":   round(result.get("predictions", {}).get("total", 0), 1),
                "HasPack":     int(not purchases[(purchases["Player"]==p) & (purchases["PurchaseType"]=="PACK")].empty),
                "HasInsurance":int(not purchases[(purchases["Player"]==p) & (purchases["PurchaseType"]=="INSURANCE")].empty),
                "HasNinth":    int(not purchases[(purchases["Player"]==p) & (purchases["PurchaseType"]=="NINTH")].empty),
                "HasRes":      int(not purchases[(purchases["Player"]==p) & (purchases["PurchaseType"]=="RESURRECTION")].empty),
            })

        player_scores.sort(key=lambda x: -x["Total"])
        for rank, row in enumerate(player_scores, 1):
            row["Rank"] = rank
        all_rows.extend(player_scores)

        scores = [r["Total"] for r in player_scores]
        tier_avgs = breakdown_tier_contributions(PARTICIPANTS, allocation, match_stats, tier_map)

        meta = {
            "Sim":         sim_id,
            "Seed":        sim_seed,
            "WC_Winner":   wc_winner,
            "WinnerTier":  winner_tier,
            "Score_1st":   scores[0],
            "Score_Last":  scores[-1],
            "Score_Range": round(scores[0] - scores[-1], 1),
            "Score_Mean":  round(sum(scores) / len(scores), 1),
            "Score_Std":   round(float(np.std(scores)), 1),
            "Gini":        round(_gini(scores), 3),
            **tier_avgs,
        }
        per_sim_meta.append(meta)

        # Save per-sim leaderboard
        sim_df = pd.DataFrame(player_scores)
        sim_df.to_csv(RESULTS_DIR / f"sim_{sim_id:02d}.csv", index=False)

        print(f"  Sim {sim_id:02d}  WC winner: {wc_winner:<22} (T{winner_tier})  "
              f"1st: {scores[0]:5.1f}  last: {scores[-1]:5.1f}  "
              f"range: {scores[0]-scores[-1]:5.1f}")

    # ── Aggregate summary ─────────────────────────────────────────────────────
    summary_df = pd.DataFrame(per_sim_meta)
    summary_df.to_csv(RESULTS_DIR / "summary.csv", index=False)

    all_df = pd.DataFrame(all_rows)
    all_df.to_csv(RESULTS_DIR / "all_scores.csv", index=False)

    # ── Analysis report ───────────────────────────────────────────────────────
    report = _build_report(summary_df, all_df, allocation, tier_map)
    report_path = ROOT / "simulations" / "report.txt"
    report_path.write_text(report, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "=" * 72)
    print(report)
    print(f"\nReport saved -> {report_path}")
    print(f"Results saved → {RESULTS_DIR}/")


def _build_report(summary: pd.DataFrame, all_df: pd.DataFrame, allocation, tier_map: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 72)
    add("WC 2026 SWEEPSTAKE — SCORING FAIRNESS REPORT")
    add(f"20 simulations · {len(PARTICIPANTS)} participants · mixed purchase profiles")
    add("=" * 72)

    # 1. Tournament outcomes
    add("\n── 1. TOURNAMENT OUTCOMES ──────────────────────────────────────────")
    tier_wins = summary["WinnerTier"].value_counts().sort_index()
    for tier, cnt in tier_wins.items():
        add(f"   T{tier} World Cup winner:  {cnt:2d} / {N} simulations ({cnt/N*100:.0f}%)")
    winners = summary["WC_Winner"].value_counts()
    add(f"\n   Most common WC winner: {winners.index[0]} ({winners.iloc[0]}x)")

    # 2. Score distribution
    add("\n── 2. SCORE DISTRIBUTION ───────────────────────────────────────────")
    add(f"   Avg 1st place score   : {summary['Score_1st'].mean():.1f} pts")
    add(f"   Avg last place score  : {summary['Score_Last'].mean():.1f} pts")
    add(f"   Avg score range       : {summary['Score_Range'].mean():.1f} pts  "
        f"(min {summary['Score_Range'].min():.0f}  max {summary['Score_Range'].max():.0f})")
    add(f"   Avg within-sim std dev: {summary['Score_Std'].mean():.1f} pts")
    add(f"   Avg Gini coefficient  : {summary['Gini'].mean():.3f}  "
        f"(0=equal, 0.15+=high inequality)")

    # 3. Tier contribution
    add("\n── 3. AVERAGE POINTS PER TEAM BY TIER ─────────────────────────────")
    for col in ["T1", "T2", "T3", "T4"]:
        avg = summary[col].mean()
        add(f"   {col} avg pts per team: {avg:.1f}")
    t1_avg = summary["T1"].mean()
    t4_avg = summary["T4"].mean()
    add(f"\n   T1 / T4 ratio per team: {t1_avg / max(t4_avg, 0.1):.1f}x  "
        f"(T1 earns {t1_avg/max(t4_avg,0.1):.1f}x more than T4 on average)")

    # 4. Bonus component analysis
    add("\n── 4. BONUS COMPONENT ANALYSIS ─────────────────────────────────────")
    avg_total   = all_df["Total"].mean()
    avg_base    = all_df["Base"].mean()
    avg_captain = all_df["CaptainBonus"].mean()
    avg_ins     = all_df["InsBonus"].mean()
    avg_pred    = all_df["PredBonus"].mean()
    add(f"   Avg total score       : {avg_total:.1f} pts")
    add(f"   Avg base (match stats): {avg_base:.1f} pts  ({avg_base/avg_total*100:.0f}% of total)")
    add(f"   Avg captain bonus     : {avg_captain:.1f} pts  ({avg_captain/avg_total*100:.0f}% of total)")
    add(f"   Avg insurance bonus   : {avg_ins:.1f} pts  ({avg_ins/avg_total*100:.0f}% of total)")
    add(f"   Avg prediction bonus  : {avg_pred:.1f} pts  ({avg_pred/avg_total*100:.0f}% of total)")

    # 5. Add-in value analysis
    add("\n── 5. PURCHASE VALUE ANALYSIS ──────────────────────────────────────")
    for col, name, cost in [
        ("HasPack",      "Prediction Pack (€5)", 5),
        ("HasInsurance", "Insurance (€2)",        2),
        ("HasNinth",     "Ninth Team (€3)",       3),
        ("HasRes",       "Resurrection (€5)",     5),
    ]:
        buyers   = all_df[all_df[col] == 1]["Total"].mean()
        nonbuyers= all_df[all_df[col] == 0]["Total"].mean()
        uplift   = buyers - nonbuyers
        add(f"   {name:<28}  buyers avg: {buyers:.1f}  non-buyers: {nonbuyers:.1f}  "
            f"uplift: {uplift:+.1f} pts")

    # 6. Insurance payoff rate
    add("\n── 6. INSURANCE PAYOFF ANALYSIS ────────────────────────────────────")
    ins_payers = all_df[all_df["HasInsurance"] == 1]
    ins_paid   = ins_payers[ins_payers["InsBonus"] > 0]
    payoff_rate = len(ins_paid) / len(ins_payers) * 100 if not ins_payers.empty else 0
    add(f"   Insurance payoff rate : {payoff_rate:.0f}% of insurance buyers received the bonus")
    add(f"   Insurance bonus value : +{INSURANCE_BONUS} pts when it pays off")
    add(f"   Insurance cost        : €2")

    # 7. Captain impact
    add("\n── 7. CAPTAIN MULTIPLIER ANALYSIS ──────────────────────────────────")
    cap_pct = avg_captain / max(avg_base, 1) * 100
    add(f"   Captain bonus averages {avg_captain:.1f} pts = {cap_pct:.0f}% of base points")
    add(f"   Captain multiplier     : {CAPTAIN_MULTIPLIER}× (adds 0.5× team pts)")

    # 8. Score range benchmark
    add("\n── 8. COMPETITIVE BALANCE ──────────────────────────────────────────")
    avg_range = summary["Score_Range"].mean()
    if avg_range < 40:
        balance = "VERY TIGHT — scores are closely packed, outcomes feel random"
    elif avg_range < 80:
        balance = "GOOD — scores are spread meaningfully, skill and draw matter"
    elif avg_range < 130:
        balance = "WIDE — there is a meaningful gap; lucky draws are noticeable"
    else:
        balance = "VERY WIDE — outcomes are highly determined by draw luck"
    add(f"   Score range verdict   : {balance}")
    add(f"   Avg range             : {avg_range:.0f} pts  "
        f"(ideal for a sweepstake: 50–100)")

    # 9. Fairness verdict and recommendations
    add("\n── 9. FAIRNESS VERDICT & RECOMMENDATIONS ───────────────────────────")
    issues: list[str] = []

    t4_per_team = summary["T4"].mean()
    if t4_per_team < 3.0:
        issues.append(
            f"T4 teams average only {t4_per_team:.1f} pts/team. They rarely advance, making them\n"
            f"   feel pointless. Consider adding a T4 Group Stage Participation bonus (+3 pts)\n"
            f"   or lowering the R16 progression bonus threshold."
        )

    if cap_pct > 30:
        issues.append(
            f"Captain bonus represents {cap_pct:.0f}% of base points. Pre-tournament captain\n"
            f"   choice can be GAME-CHANGING. Consider reducing multiplier to 1.3× or\n"
            f"   capping the captain bonus at 30 pts."
        )

    if payoff_rate < 20:
        issues.append(
            f"Insurance only pays off {payoff_rate:.0f}% of the time. T1 teams rarely exit in groups.\n"
            f"   At €2 for +{INSURANCE_BONUS} pts, it's good value when it fires but often wasted.\n"
            f"   Consider extending to 'eliminated before QF' to increase payoff rate."
        )

    t1t4_ratio = t1_avg / max(t4_avg, 0.1)
    if t1t4_ratio > 5:
        issues.append(
            f"T1/T4 pts ratio is {t1t4_ratio:.1f}x. This is expected by design (upsets are rare),\n"
            f"   but T4 owners may feel disadvantaged. The current progression bonus\n"
            f"   correctly compensates T4 for deep runs, but those runs rarely happen."
        )

    if avg_range > 110:
        issues.append(
            f"Score range of {avg_range:.0f} pts is wide. Outcomes are largely determined by\n"
            f"   draw luck (which T1 teams win the WC). Consider adding a 'survivor bonus'\n"
            f"   for all teams reaching R16 (+2 pts) to tighten the pack."
        )

    avg_pred_pts = all_df.loc[all_df["HasPack"]==1, "PredBonus"].mean()
    if avg_pred_pts < 5:
        issues.append(
            f"Prediction bonus averages only {avg_pred_pts:.1f} pts for pack buyers (cost: €5).\n"
            f"   The WC winner pick (12% hit rate) and golden boot are hard to get.\n"
            f"   Consider reducing WC winner threshold to '±1 place finish' (finalist counts)."
        )

    if not issues:
        add("   [OK] No major fairness issues detected.")
        add("   The scoring system is competitive and well-balanced across all simulations.")
    else:
        for i, issue in enumerate(issues, 1):
            add(f"\n   Issue {i}: {issue}")

    add("\n── 10. SUMMARY STATISTICS TABLE ────────────────────────────────────")
    add(f"   {'Metric':<35} {'Value':>10}")
    add(f"   {'-'*45}")
    metrics = [
        ("Avg 1st place score",          f"{summary['Score_1st'].mean():.1f}"),
        ("Avg last place score",          f"{summary['Score_Last'].mean():.1f}"),
        ("Avg score range",               f"{summary['Score_Range'].mean():.1f}"),
        ("Avg std deviation",             f"{summary['Score_Std'].mean():.1f}"),
        ("Avg Gini coefficient",          f"{summary['Gini'].mean():.3f}"),
        ("Avg pts/team T1",               f"{summary['T1'].mean():.1f}"),
        ("Avg pts/team T2",               f"{summary['T2'].mean():.1f}"),
        ("Avg pts/team T3",               f"{summary['T3'].mean():.1f}"),
        ("Avg pts/team T4",               f"{summary['T4'].mean():.1f}"),
        ("Avg captain bonus",             f"{avg_captain:.1f}"),
        ("Insurance payoff rate",         f"{payoff_rate:.0f}%"),
        ("T1 WC wins",                    f"{tier_wins.get(1,0)}/20"),
        ("T2 WC wins",                    f"{tier_wins.get(2,0)}/20"),
        ("T3 WC wins",                    f"{tier_wins.get(3,0)}/20"),
        ("T4 WC wins",                    f"{tier_wins.get(4,0)}/20"),
    ]
    for name, val in metrics:
        add(f"   {name:<35} {val:>10}")

    add("\n" + "=" * 72)
    return "\n".join(lines)


if __name__ == "__main__":
    run_all()
