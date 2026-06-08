"""Quick leaderboard check script."""
import sys, warnings
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
warnings.filterwarnings('ignore')

import streamlit as st
class _FC:
    def __call__(self, fn=None, **kw): return fn if fn else (lambda f: f)
    def clear(self): pass
st.cache_data = _FC()

from src.competition import prize_leaderboard, load_player_status, load_purchases, calculate_prize_pool
from src.scoring_engine import load_match_stats, load_predictions, load_captains
from src.event_engine import load_allocation

parts  = load_player_status()["Player"].tolist()
alloc  = load_allocation().assignments
ms     = load_match_stats()
purch  = load_purchases()
caps   = load_captains()
preds  = load_predictions()
status = load_player_status()

lb = prize_leaderboard(parts, alloc, ms, purch, caps, preds, status)
print("PRIZE LEADERBOARD (QF stage demo)")
print(lb[["Rank","Player","TotalPoints","BasePoints","CaptainBonus","PredictionBonus","InsuranceBonus"]].to_string(index=False))

pool = calculate_prize_pool(purch)
print(f"\nPrize pool: E{pool['current_pot']:.2f}  "
      f"1st: E{pool['first_prize']:.2f}  "
      f"2nd: E{pool['second_prize']:.2f}  "
      f"3rd: E{pool['third_prize']:.2f}")
