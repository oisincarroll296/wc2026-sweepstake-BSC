"""One-off script to update test_competition.py for the new purchases schema."""
import re
from pathlib import Path

p = Path(__file__).parent.parent / "tests" / "test_competition.py"
content = p.read_text(encoding="utf-8")

# 1. _empty_purchases new schema
content = content.replace(
    'def _empty_purchases() -> pd.DataFrame:\n    return pd.DataFrame(columns=[\n        "Player", "PurchaseType", "Status", "Timestamp", "Reference", "Selection",\n    ])',
    'def _empty_purchases() -> pd.DataFrame:\n    return pd.DataFrame(columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])',
)

# 2. _purchases helper
content = content.replace(
    'def _purchases(*rows) -> pd.DataFrame:\n    return pd.DataFrame(rows, columns=[\n        "Player", "PurchaseType", "Status", "Timestamp", "Reference", "Selection",\n    ])',
    'def _purchases(*rows) -> pd.DataFrame:\n    records = [\n        {"Player": r[0], "PurchaseType": r[1], "Selection": r[2] if len(r) > 2 else "",\n         "Reference": "", "Timestamp": ""}\n        for r in rows\n    ]\n    return pd.DataFrame(records, columns=["Player", "PurchaseType", "Selection", "Reference", "Timestamp"])',
)

# 3. Replace 6-element tuples like ("Alice", "BuyIn", "PROCESSED", "", "", "")
# and ("Alice", "NinthTeam", "PROCESSED", "", "", "Germany")
def fix_tuple(m):
    player = m.group(1)
    ptype  = m.group(2)
    sel    = m.group(3)
    if sel:
        return f'("{player}", "{ptype}", "{sel}")'
    else:
        return f'("{player}", "{ptype}")'

pattern = r'\("([A-Za-z ]+)", "([A-Za-z]+)", "(?:PROCESSED|PENDING|CANCELLED)", "", "", "([^"]*)"\)'
content = re.sub(pattern, fix_tuple, content)

p.write_text(content, encoding="utf-8")
print("Done")
