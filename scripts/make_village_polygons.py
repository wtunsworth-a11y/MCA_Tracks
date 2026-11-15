"""One clean polygon layer: the villages, under their preferred names.

    python3 scripts/make_village_polygons.py

Writes outputs/gis/mca_villages_polygons.{kml,geojson,gpkg}.

Will, 15 Nov 2026: "a clean map of the village polygons (polygon or polygons
per named village using the preferred name)".

Three things make this more than a copy of village_footprints.kml:

  THE PREFERRED NAME. The outline file is authoritative on EXTENT, not on
  spelling - its ward 12 polygon is labelled Gazot and the preferred spelling
  is Gadzot. Every name is resolved through place_aliases.csv first.

  ONE FEATURE PER VILLAGE. Anatua is recorded as two polygons, Anatua 1 and
  Anatua 2, 1.18 km apart; Will, 12 Nov: "Anatua is both of those". Polygons
  sharing a preferred name become one MultiPolygon, so the layer has one
  feature per village and not one per outline.

  COMPOUND LABELS SPLIT. Five outlines name more than one place - "Sila 2 /
  Sakarina / Sila 1", "Numba/Siurana", "Kawowoki 1 / Kawowoki 2", "Itokama /
  Itokama station", "Buanfuo (Jakiro/Sibisibi)". Where every part resolves to
  the same preferred name the outline simply takes it. Where they do not, the
  outline is one shape covering several named places and is kept whole, with
  the parts listed in `also_known_as` rather than silently dropped.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
FOOT = ROOT / "data" / "reference" / "village_footprints.geojson"
OUT = ROOT / "outputs" / "gis"
STEM = "mca_villages_polygons"


def preferred():
    """as-written (lowercased) -> preferred spelling, chain followed."""
    al = ROOT / "data" / "reference" / "place_aliases.csv"
    direct = {}
    if al.exists():
        for r in pd.read_csv(al, comment="#").itertuples():
            a, b = getattr(r, "as_written", None), getattr(r, "resolved_to", None)
            if pd.isna(a) or pd.isna(b):      # a blank resolved_to is a note
                continue
            a, b = str(a).strip(), str(b).strip()
            if a and b:
                direct[a.lower()] = b

    def follow(n, d=0):
        nxt = direct.get(n.strip().lower())
        if nxt is None or nxt.strip().lower() == n.strip().lower() or d > 8:
            return n
        return follow(nxt, d + 1)

    return follow


def parts_of(label):
    """The named places a compound outline label refers to."""
    label = re.sub(r"[()]", " / ", label)
    return [p.strip() for p in label.split("/") if p.strip()]


def main():
    follow = preferred()
    gj = json.loads(FOOT.read_text())

    groups = defaultdict(lambda: {"geoms": [], "ward": None, "aka": set(),
                                  "outlines": 0, "ha": 0.0})
    for f in gj["features"]:
        label = f["properties"]["village"]
        bits = parts_of(label)
        names = {follow(b) for b in bits}
        # A trailing number is NOT noise. Will, 15 Nov 2026: "Anatua 1 and
        # Anatua 2 (their preference)" - the village itself distinguishes
        # them, so they stay two villages. Stripping the number merged them.
        if len(names) == 1:
            key = names.pop()
            aka = {b for b in bits if b.strip().lower() != key.lower()}
        else:
            # genuinely several places under one outline - do not invent a split
            key = label
            aka = set(bits)
        g = groups[key]
        g["geoms"].append(shape(f["geometry"]))
        g["ward"] = g["ward"] or f["properties"].get("ward")
        g["aka"] |= aka
        g["outlines"] += 1
        g["ha"] += float(f["properties"].get("area_ha") or 0)

    rows = []
    for name, g in sorted(groups.items()):
        rows.append({
            "village": name,
            "ward": g["ward"] or "",
            "outlines": g["outlines"],
            "area_ha": round(g["ha"], 2),
            "also_known_as": "; ".join(sorted(g["aka"])),
            "geometry": unary_union(g["geoms"]) if len(g["geoms"]) > 1
            else g["geoms"][0],
        })

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT / f"{STEM}.geojson", driver="GeoJSON")
    gdf.to_file(OUT / f"{STEM}.gpkg", layer="villages", driver="GPKG")
    # The GeoPandas KML driver writes no <name>, so the layer opens as 68
    # unnamed shapes. Write it properly instead.
    sys.path.insert(0, str(ROOT / "scripts"))
    import kml_writer
    byward = defaultdict(list)
    for r in gdf.sort_values(["ward", "village"]).itertuples():
        desc = (f"<b>{r.village}</b><br/>Ward {r.ward}<br/>"
                f"{r.area_ha:.2f} ha"
                + (f"<br/>{r.outlines} separate outlines" if r.outlines > 1 else "")
                + (f"<br/>also written: {r.also_known_as}" if r.also_known_as else ""))
        byward[r.ward or "(no ward)"].append(
            (r.village, desc, r.geometry, "village"))
    kml_writer.write(
        OUT / f"{STEM}.kml",
        "MCA village polygons",
        ("One feature per named village, under the preferred spelling. "
         f"{len(gdf)} villages, {gdf.area_ha.sum():,.1f} ha. Outlines from "
         "village_footprints.kml (Will, 12 Nov 2026); names resolved through "
         "place_aliases.csv. Extent is indicative, not survey."),
        {"village": ("ff00d4ff", 2, "4d00d4ff")},
        [(f"Ward {w}", items) for w, items in sorted(byward.items())])

    multi = gdf[gdf.outlines > 1]
    print(f"wrote {STEM}.{{kml,geojson,gpkg}} to {OUT.relative_to(ROOT)}")
    print(f"  {len(gdf)} villages from {int(gdf.outlines.sum())} outlines")
    print(f"  total area {gdf.area_ha.sum():,.1f} ha")
    if len(multi):
        print(f"  {len(multi)} village(s) made of more than one polygon:")
        for r in multi.itertuples():
            print(f"      {r.village:22s} {r.outlines} outlines  ({r.also_known_as})")
    renamed = [r for r in gdf.itertuples() if r.also_known_as]
    print(f"  {len(renamed)} carry an also_known_as")
    return 0


if __name__ == "__main__":
    sys.exit(main())
