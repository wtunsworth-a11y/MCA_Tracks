"""The plain list Will asked for: name, type, village, coordinates.

One row per government facility. The village is decided by POSITION, not by
the facility's name, because the name lies often enough to matter here: Afore
High School is named for the LLG and stands at Sakarina, 8.5 km from Afore
station, and Suwari Primary School is physically elsewhere again. So each
facility is attributed to the nearest village in the corrected gazetteer, and
the distance is carried so a far attribution can be seen for what it is.

    python3 scripts/make_facilities_csv.py

Writes outputs/gis/mca_government_facilities.csv.
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_access import haversine_km, load_villages  # noqa: E402

SRC = ROOT / "outputs" / "gis" / "mca_government_services.csv"
OUT = ROOT / "outputs" / "gis" / "mca_government_facilities.csv"

# Beyond this the facility is not meaningfully "at" the village, it is only
# nearest to it. Same threshold the ward attribution and the facilities
# reconciliation use, so the three agree.
MAX_AT_KM = 3.0

# place_aliases.csv positions anything worth pinning, facilities included, so
# it cannot be read as a settlement list unfiltered. "Aguido Primary School"
# came through as a village and three facilities were filed "at" it. Will, 27
# Oct 2026: "Aguido is the name of a person. Not a place". A facility is never
# the answer to "which village is this in".
NOT_A_SETTLEMENT = re.compile(
    r"\b(school|aid\s*post|aidpost|health\s+cent(?:re|er)|airstrip"
    r"|office|church|institute|clinic|haus\s*sik)\b", re.I)


def places():
    """Every place a facility could stand at, with the best position for it.

    The 46-village gazetteer is not the whole list. Umuate holds a school and
    212 people in ward 14 and is absent from it. Anatua is absent too, and is
    one village in two parts - Will, 11 Nov 2026: "Anatua is both of those" -
    so it needs TWO points under the one name.

    Positions are tiered, and for each name only the best tier is kept: the
    team's own placements, then a position written into place_aliases.csv with
    the evidence for it, then the gazetteer. Within a tier every point is kept,
    which is what lets Anatua be two places. Keeping points from more than one
    tier would be worse than useless: the facility would be matched to
    whichever stale duplicate happened to sit nearest, and every distance in
    the file would flatter itself.

    Facilities are excluded, because place_aliases.csv positions anything worth
    pinning and a facility is never the answer to "which village is this in".
    """
    TIERS = {"team": 0, "alias": 1, "gazetteer": 2}
    cand = {}  # name.lower() -> (tier_rank, display_name, [(lon, lat), ...])

    def offer(name, lon, lat, tier):
        name = str(name).strip()
        if not name or NOT_A_SETTLEMENT.search(name):
            return
        rank = TIERS[tier]
        key = name.lower()
        cur = cand.get(key)
        if cur is None or rank < cur[0]:
            cand[key] = (rank, name, [(float(lon), float(lat))])
        elif rank == cur[0]:
            cur[2].append((float(lon), float(lat)))

    pt = ROOT / "data" / "reference" / "placed_by_team.csv"
    if pt.exists():
        for r in pd.read_csv(pt, comment="#").itertuples():
            offer(r.place, r.lon, r.lat, "team")

    al = ROOT / "data" / "reference" / "place_aliases.csv"
    if al.exists():
        for r in pd.read_csv(al, comment="#").itertuples():
            lon, lat = getattr(r, "lon", None), getattr(r, "lat", None)
            if pd.notna(lon) and pd.notna(lat):
                offer(getattr(r, "resolved_to", ""), lon, lat, "alias")

    vil, _ = load_villages()
    for v in vil.itertuples():
        offer(v.vil_name, v.lon, v.lat, "gazetteer")

    pts = []
    for _rank, name, coords in cand.values():
        for lon, lat in coords:
            pts.append((name, lon, lat))
    return pts


def main():
    fac = pd.read_csv(SRC, comment="#")
    vil = places()

    rows = []
    for f in fac.itertuples():
        best, best_km = None, None
        for name, vlon, vlat in vil:
            d = haversine_km(float(f.lon), float(f.lat), vlon, vlat)
            if best_km is None or d < best_km:
                best, best_km = name, d
        rows.append({
            "name": f.facility,
            "type": f.kind,
            "village": best,
            "km_from_village": round(best_km, 2),
            "latitude": round(float(f.lat), 7),
            "longitude": round(float(f.lon), 7),
        })

    out = pd.DataFrame(rows).sort_values(["type", "name"], kind="stable")

    far = out[out.km_from_village > MAX_AT_KM]
    with OUT.open("w", newline="") as fh:
        fh.write("# Government facilities in the Managalas Conservation Area.\n")
        fh.write("# The village is the NEAREST village by position, not the name in\n")
        fh.write("# the facility's title. km_from_village says how good that is:\n")
        fh.write(f"# over {MAX_AT_KM:.0f} km the facility is near that village, not at it.\n")
        fh.write("# Coordinates are WGS84 decimal degrees.\n")
        out.to_csv(fh, index=False)

    print(f"wrote {OUT.relative_to(ROOT)} — {len(out)} facilities")
    print(out.groupby('type').size().to_string())
    if len(far):
        print(f"\n{len(far)} not AT their nearest village (> {MAX_AT_KM:.0f} km):")
        for r in far.sort_values('km_from_village', ascending=False).itertuples():
            print(f"  {r.name:38s} {r.km_from_village:5.2f} km from {r.village}")


if __name__ == "__main__":
    main()
