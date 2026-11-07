"""Every facility-survey waypoint drop, found rather than listed.

Russell sends these one area at a time - the October facilities survey, then
zone 4 - and each arrives as its own file. Three scripts read them, and when
the list of files was hard-coded in each, adding a drop meant remembering all
three. Zone 4 was reported as entirely uncollected until two of them were
changed by hand.

So the files are discovered: data/reference/waypoints_*.csv, keeping only
those with the facility-survey schema. waypoints_mca.csv is the 18 Oct
rivers-and-hamlets drop with four columns and no condition notes, and it is
correctly skipped by that test rather than by name.
"""
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"


def drop_files():
    """The facility-survey drops, oldest name first for a stable order."""
    out = []
    for p in sorted(REF.glob("waypoints_*.csv")):
        with p.open() as fh:
            head = next((l for l in fh if not l.startswith("#")), "")
        cols = [c.strip() for c in head.strip().split(",")]
        if "note" in cols and "name" in cols:
            out.append(p)
    return out


def load_waypoints():
    rows = []
    for p in drop_files():
        with p.open() as fh:
            for r in csv.DictReader(l for l in fh if not l.startswith("#")):
                r.setdefault("photo_files", "")
                r["_drop"] = p.name
                rows.append(r)
    return rows


if __name__ == "__main__":
    for p in drop_files():
        print(p.name)
    print(f"{len(load_waypoints())} waypoints in {len(drop_files())} drops")
