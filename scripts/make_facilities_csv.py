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
from build_access import corrected_positions, haversine_km, load_villages  # noqa: E402

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

    The 46-village gazetteer is not the whole list. Umuate holds an elementary
    school and 212 people in ward 14, and is absent from it, so its school was
    being filed at Madokoro 6.3 km away. place_aliases.csv and
    placed_by_team.csv carry positions for places like that, with the evidence
    for each, so they are folded in here - the team's own placements last so
    they win.
    """
    vil, _ = load_villages()
    out = {}
    for v in vil.itertuples():
        out[str(v.vil_name).strip().lower()] = (
            str(v.vil_name).strip(), float(v.lon), float(v.lat))
    for key, (lon, lat, _src) in corrected_positions().items():
        name = out.get(key, (key.title(),))[0]
        if key not in out and NOT_A_SETTLEMENT.search(name):
            continue
        out[key] = (name, lon, lat)
    return list(out.values())


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
