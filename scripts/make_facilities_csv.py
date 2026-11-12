"""The plain list Will asked for: name, type, village, coordinates.

    python3 scripts/make_facilities_csv.py

Writes outputs/gis/mca_government_facilities.csv, one row per government
facility.

THE VILLAGE IS AN AREA, NOT A POINT.

Will, 12 Nov 2026: "the polygons are meant to help you see that the named track
ends, facilities and features are within a polygon of a village, not a single
point. A village has area and multiple points may be included within a single
village."

This file used to match each facility to the nearest village CENTROID, which
is wrong twice over. It made a facility at the far edge of a large village look
badly placed - Kaura's outline is 1314 x 718 m, so a school inside it can be
700 m from the centre and still be plainly in Kaura - and it had no way to say
that six buildings are all in the one village.

So the question asked here is "which village outline is this point in?", and
only when the answer is none does it fall back to distance, measured to the
nearest outline's EDGE rather than to its middle.

The outlines are Will's village_footprints.kml of 12 Nov 2026: 68 named
settlements, each with its ward and its area. Checked against all 47 facilities
they disagreed with the old derived column exactly once, on Awaru, and they
were right.

WARD IS NOT VILLAGE, and the column carries both because confusing them is what
put Awaru Old Airstrip at Kaura: Awaru village sits inside ward 04 Kaura, so
the wrong answer read perfectly well.
"""
import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_access import haversine_km, load_villages  # noqa: E402

SRC = ROOT / "outputs" / "gis" / "mca_government_services.csv"
FOOT = ROOT / "data" / "reference" / "village_footprints.geojson"
OUT = ROOT / "outputs" / "gis" / "mca_government_facilities.csv"

# A facility is never the answer to "which village is this in". place_aliases
# positions facilities as well as places, and reading it unfiltered once put
# "Aguido Primary School" in the village column with three facilities filed at
# it. Will, 27 Oct 2026: "Aguido is the name of a person. Not a place."
NOT_A_SETTLEMENT = re.compile(
    r"\b(school|aid\s*post|aidpost|health\s+cent(?:re|er)|airstrip"
    r"|office|church|institute|clinic|haus\s*sik)\b", re.I)


def footprints():
    """[(village, ward, polygon)] - the authority on where a village IS."""
    if not FOOT.exists():
        return []
    gj = json.loads(FOOT.read_text())
    return [(f["properties"]["village"], f["properties"]["ward"],
             shape(f["geometry"])) for f in gj["features"]]


def point_places():
    """Places that have a position but no outline, best tier first.

    Still needed: the footprints cover 68 settlements, not every one, and a
    facility beyond them all has to land somewhere defensible.
    """
    TIERS = {"team": 0, "alias": 1, "gazetteer": 2}
    cand = {}

    def offer(name, lon, lat, tier):
        name = str(name).strip()
        if not name or NOT_A_SETTLEMENT.search(name):
            return
        rank, key = TIERS[tier], name.lower()
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

    out = []
    for _rank, name, coords in cand.values():
        for lon, lat in coords:
            out.append((name, lon, lat))
    return out


# Two outlines this close to equidistant are a tie, not a measurement. The Dea
# cluster sits ~0.7 km outside both Dea and Ugunomo and the gap between them
# was 10 m, so a coin-flip was moving "Old Dea Airstrip" and "Dea Primary
# School" into Ugunomo. Within this margin the facility's own name decides -
# as a tiebreak only. A name is still never evidence of WHERE something is,
# which is why it cannot overturn containment or a clear distance.
TIE_KM = 0.15


def locate(lon, lat, polys, pts, facility=""):
    """(village, ward, km) - km is 0.0 when the point is inside the outline."""
    p = Point(lon, lat)
    for name, ward, g in polys:
        if g.contains(p):
            return name, ward, 0.0

    ranked = []
    for name, ward, g in polys:
        q = nearest_points(p, g)[1]           # closest point ON THE OUTLINE
        ranked.append((haversine_km(lon, lat, q.x, q.y), name, ward))
    for name, vlon, vlat in pts:
        ranked.append((haversine_km(lon, lat, vlon, vlat), name, ""))
    if not ranked:
        return "", "", float("nan")
    ranked.sort(key=lambda r: r[0])

    d0 = ranked[0][0]
    tied = [r for r in ranked if r[0] - d0 <= TIE_KM]
    if len(tied) > 1 and facility:
        fl = facility.lower()
        named = [r for r in tied if r[1].lower().split("/")[0].strip() in fl]
        if len(named) == 1:
            d, name, ward = named[0]
            return name, ward, d
    d, name, ward = ranked[0]
    return name, ward, d


def main():
    fac = pd.read_csv(SRC, comment="#")
    polys, pts = footprints(), point_places()

    rows = []
    for f in fac.itertuples():
        v, w, d = locate(float(f.lon), float(f.lat), polys, pts, str(f.facility))
        rows.append({"name": f.facility, "type": f.kind,
                     "village": v, "ward": w,
                     "km_to_village": round(d, 2),
                     "latitude": round(float(f.lat), 7),
                     "longitude": round(float(f.lon), 7)})
    out = pd.DataFrame(rows).sort_values(["type", "name"], kind="stable")

    n_in = int((out.km_to_village == 0).sum())
    with OUT.open("w", newline="") as fh:
        fh.write("# Government facilities in the Managalas Conservation Area.\n")
        fh.write("# village: the village OUTLINE the facility stands in, from\n")
        fh.write("#   village_footprints.kml. A village is an area, so several\n")
        fh.write("#   facilities share one. km_to_village is 0.00 when the point\n")
        fh.write("#   is inside that outline; otherwise it is the distance to the\n")
        fh.write("#   nearest outline's EDGE, and that outline is named.\n")
        fh.write("# ward: the ward the outline belongs to. NOT the same thing -\n")
        fh.write("#   Awaru village is inside ward 04 Kaura.\n")
        fh.write("# Coordinates are WGS84 decimal degrees.\n")
        out.to_csv(fh, index=False)

    print(f"wrote {OUT.relative_to(ROOT)} — {len(out)} facilities")
    print(f"  inside a village outline: {n_in}")
    print(f"  outside every outline:    {len(out) - n_in}")
    share = out[out.km_to_village == 0].groupby("village").size()
    share = share[share > 1].sort_values(ascending=False)
    print(f"  villages holding more than one facility: {len(share)}")
    for v, n in share.items():
        print(f"      {v:30s} {n}")
    far = out[out.km_to_village > 0.6].sort_values("km_to_village", ascending=False)
    if len(far):
        print(f"  furthest from any outline:")
        for r in far.head(6).itertuples():
            print(f"      {r.name:36s} {r.km_to_village:5.2f} km from {r.village}")


if __name__ == "__main__":
    main()
