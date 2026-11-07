"""One photo per facility. Not one per building.

    python3 scripts/pick_facility_photos.py

Writes data/reference/facility_photos.csv.

Will, 5 Nov 2026: "One photo of the facility itself. I didn't ask for housing
or classrooms to be mapped individually and we have nowhere to meaningfully
use the data. Keep it as a backup for later use, but find one photo to use."

So: the 191 recorded points group into institutions, and each institution gets
exactly ONE photo - of the thing itself, not of a teacher's house. The
per-building detail stays in waypoints_facilities.csv untouched; it is simply
not what the ward map shows.

Choosing which photo. The field names say what each point is, so they are read
in the order someone would answer the question "which of these IS the school?"

  1. the point named for the institution and nothing else - "Sakarina Health
     Centre", "Itokama Airstrip". If it exists it is the right answer.
  2. a main building - a classroom block, an administration block. For a
     school with no bare-named point this is the school.
  3. anything that is not somebody's house, a dormitory, a kitchen or a store.
  4. failing all that, the earliest recorded point that has a photo at all,
     so a facility is never left without a picture for want of a tidy name.

Which rule each one fell to is written out, because rule 4 is a guess and
should be visible as one.
"""
from pathlib import Path
import csv
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_ward_map import institution_of  # noqa: E402

from waypoint_drops import load_waypoints  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "reference" / "facility_photos.csv"

# Somebody lives or cooks or stores things here. It is not the facility.
ANCILLARY = re.compile(
    r"\b(teacher'?s?|head teacher'?s?|priest'?s?|dormitor|house|houses|kitchen|"
    r"mass|storage|store|toilet|ablution|tomb|oic'?s?)\b", re.I)
MAIN = re.compile(r"\b(building|block|classroom|\d\s*in\s*1)\b", re.I)


def rank(name, inst):
    bare = " ".join(name.split()).lower() == inst.lower()
    anc = bool(ANCILLARY.search(name))
    if bare:
        return 0
    if MAIN.search(name) and not anc:
        return 1
    if not anc:
        return 2
    return 3


REASON = {0: "named for the facility itself",
          1: "main building",
          2: "not an ancillary building",
          3: "GUESS - only ancillary points carry a photo"}


def main():
    pts = load_waypoints()

    groups = {}
    for p in pts:
        inst = institution_of(p["name"])
        if inst and p["photo_files"].strip():
            groups.setdefault(inst, []).append(p)

    rows = []
    for inst, group in sorted(groups.items()):
        group.sort(key=lambda p: (rank(p["name"], inst), p["recorded"]))
        best = group[0]
        r = rank(best["name"], inst)
        rows.append({
            "facility": inst,
            "photo": best["photo_files"].split()[0],
            "from_point": best["name"],
            "chosen_because": REASON[r],
            "lon": best["lon"], "lat": best["lat"],
            "note": best["note"],
            "points_in_facility": len(group),
            "photos_available": sum(len(p["photo_files"].split()) for p in group),
        })

    with OUT.open("w", newline="") as fh:
        fh.write("# One photo per facility, chosen by scripts/pick_facility_photos.py.\n"
                 "# The other photos stay in Drive and are not deleted - they are a\n"
                 "# backup, not the map. chosen_because says which rule picked this\n"
                 "# one; anything marked GUESS had only ancillary buildings to\n"
                 "# choose from and should be looked at before it is printed.\n")
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {OUT}")
    print(f"  {len(rows)} facilities, one photo each, "
          f"out of {sum(r['photos_available'] for r in rows)} available")
    for r in rows:
        flag = "  <-- CHECK" if r["chosen_because"].startswith("GUESS") else ""
        print(f"  {r['facility'][:40]:42s} {r['from_point'][:38]:40s} "
              f"{r['chosen_because']}{flag}")


if __name__ == "__main__":
    main()
