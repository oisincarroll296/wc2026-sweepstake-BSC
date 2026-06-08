"""
Snapshot all data files to data/snapshots/<timestamp>_<label>/

Usage:
    python tools/snapshot.py                  # auto-labelled
    python tools/snapshot.py pre_draw         # labelled snapshot
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"


def snapshot(label: str = "") -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"{ts}_{label}" if label else ts
    dest = SNAPSHOTS / name
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(DATA.glob("*.csv")):
        shutil.copy2(f, dest / f.name)
        copied.append(f.name)
    for f in sorted(DATA.glob("*.json")):
        shutil.copy2(f, dest / f.name)
        copied.append(f.name)
    print(f"Snapshot → {dest.name}")
    print(f"  Files: {', '.join(copied)}")
    return dest


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    snapshot(label)
