"""
Restore data files from a snapshot.

Usage:
    python tools/restore.py              # interactive — lists and picks
    python tools/restore.py pre_draw     # restore snapshot whose name contains 'pre_draw'
    python tools/restore.py 0            # restore by index (0 = most recent)
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"


def list_snapshots() -> list[Path]:
    if not SNAPSHOTS.exists():
        return []
    return sorted(SNAPSHOTS.iterdir(), reverse=True)


def restore(snap: Path) -> None:
    for f in sorted(snap.glob("*.csv")):
        shutil.copy2(f, DATA / f.name)
    for f in sorted(snap.glob("*.json")):
        shutil.copy2(f, DATA / f.name)
    print(f"Restored from: {snap.name}")


def main() -> None:
    snaps = list_snapshots()
    if not snaps:
        print("No snapshots found in data/snapshots/")
        sys.exit(1)

    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg.isdigit():
        idx = int(arg)
        if idx >= len(snaps):
            print(f"Index {idx} out of range (0–{len(snaps)-1})")
            sys.exit(1)
        chosen = snaps[idx]
    elif arg:
        matches = [s for s in snaps if arg in s.name]
        if not matches:
            print(f"No snapshot matching '{arg}'")
            sys.exit(1)
        chosen = matches[0]
    else:
        print("Available snapshots:")
        for i, s in enumerate(snaps):
            print(f"  [{i}] {s.name}")
        choice = input("Enter number to restore: ").strip()
        if not choice.isdigit() or int(choice) >= len(snaps):
            print("Invalid choice.")
            sys.exit(1)
        chosen = snaps[int(choice)]

    confirm = input(f"Restore from '{chosen.name}'? This overwrites data/. (yes/no): ").strip()
    if confirm.lower() != "yes":
        print("Cancelled.")
        sys.exit(0)
    restore(chosen)


if __name__ == "__main__":
    main()
