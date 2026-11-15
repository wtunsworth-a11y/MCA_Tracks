"""One clean line layer: every road and track, once, classed.

    python3 scripts/make_clean_network.py

Writes outputs/gis/mca_network_clean.{kml,geojson,gpkg}.

Will, 15 Nov 2026: "a clean map of mapped tracks and roads (no duplicates, no
overlaps, point to point polylines) identifying road and track by Class".

The raw layer is 170 GPS recordings totalling 1,042 km, and that total is not
the length of the network - it is the length of the walking. Routes are walked
in both directions and on different days, so the same ground is recorded many
times, and no two recordings of it share a vertex.

So this does three things, in this order:

  DEDUPE BY CORRIDOR, not by geometry. Two recordings of one path never match
  exactly, so identity tests find nothing. Each recording is taken longest
  first and only the part of it lying outside a corridor already covered is
  kept. The corridor is CORRIDOR_M either side, which is wide enough for GPS
  scatter under canopy and narrow enough to keep two genuinely parallel paths
  apart.

  ROADS WIN. A road is often also recorded as a foot track, by someone walking
  it. Roads are laid down first, so where the two coincide the surviving line
  is the road and the duplicate foot record is dropped.

  NODE EVERYTHING. The survivors are unioned once, which splits every line at
  every crossing, then merged back into the longest runs that do not pass
  through a junction. That is what makes them point-to-point polylines rather
  than whole-day recordings laid over each other.

Class comes from `mode` in the processed layer, which classify_mode.py decides
from measured speed and gradient rather than from the name of the file.
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "tracks.gpkg"
OUT = ROOT / "outputs" / "gis"
STEM = "mca_network_clean"
METRIC = 32755                 # UTM 55S

# Half-width of the corridor a recording is considered already covered by.
# GPS under canopy scatters; 25 m absorbs that without welding two real paths
# that run 60 m apart on opposite banks.
CORRIDOR_M = 25.0
# A survivor shorter than this is a GPS crumb at a junction, not a route.
MIN_SEG_M = 60.0

CLASSES = [("Motor road", "road"), ("Foot track", "track")]


def lines_of(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        out = []
        for g in geom.geoms:
            out += lines_of(g)
        return out
    return []


def thin(geoms, covered):
    """Keep only what is not already inside `covered`. Returns (kept, covered)."""
    kept = []
    for g in sorted(geoms, key=lambda x: -x.length):
        piece = g.difference(covered) if covered is not None else g
        for seg in lines_of(piece):
            if seg.length >= MIN_SEG_M:
                kept.append(seg)
        if kept:
            buf = unary_union([s.buffer(CORRIDOR_M) for s in kept])
            covered = buf if covered is None else unary_union([covered, buf])
    return kept, covered


def main():
    src = gpd.read_file(SRC, layer="tracks").to_crs(METRIC)
    raw_km = src.length.sum() / 1000
    print(f"{len(src)} recordings, {raw_km:,.0f} km of walking")

    covered, by_class = None, {}
    for mode, label in CLASSES:
        sub = src[src["mode"] == mode]
        geoms = [g for row in sub.geometry for g in lines_of(row)]
        kept, covered = thin(geoms, covered)
        by_class[label] = kept
        print(f"  {label:6s} {len(sub):3d} recordings "
              f"({sum(g.length for g in geoms)/1000:6.1f} km) "
              f"-> {len(kept):3d} pieces, {sum(g.length for g in kept)/1000:6.1f} km")

    # Node once across both classes so a road/track crossing becomes a vertex,
    # then merge each class into its longest junction-free runs.
    everything = unary_union([g for v in by_class.values() for g in v])
    rows = []
    for label, kept in by_class.items():
        corridor = unary_union([g.buffer(1.0) for g in kept])
        mine = [s for s in lines_of(everything) if s.representative_point().within(corridor)]
        merged = lines_of(linemerge(MultiLineString(mine))) if mine else []
        for n, seg in enumerate(sorted(merged, key=lambda x: -x.length), 1):
            if seg.length < MIN_SEG_M:
                continue
            rows.append({"class": label,
                         "segment": f"{label}-{n:03d}",
                         "length_km": round(seg.length / 1000, 3),
                         "geometry": seg})

    gdf = gpd.GeoDataFrame(rows, crs=f"EPSG:{METRIC}").to_crs(4326)
    OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT / f"{STEM}.geojson", driver="GeoJSON")
    gdf.to_file(OUT / f"{STEM}.gpkg", layer="network", driver="GPKG")
    sys.path.insert(0, str(ROOT / "scripts"))
    import kml_writer
    STYLE = {"road": ("ff2222ee", 4, None), "track": ("ff22cc22", 3, None)}
    folders = []
    for label, pretty in (("road", "Motor roads"), ("track", "Foot tracks")):
        sub = gdf[gdf["class"] == label]
        # itertuples() renames `class`, which is a Python keyword, so the
        # label in scope is used rather than reading it back off the row.
        items = [(row.segment,
                  f"<b>{pretty[:-1]}</b><br/>{row.length_km:.2f} km<br/>"
                  f"Class: {label}", row.geometry, label)
                 for _i, row in sub.iterrows()]
        folders.append((f"{pretty} ({len(items)}, "
                        f"{sub.to_crs(METRIC).length.sum()/1000:.0f} km)", items))
    kml_writer.write(
        OUT / f"{STEM}.kml",
        "MCA roads and tracks, cleaned",
        ("Every recorded route once, classed as road or track. Duplicates and "
         "retracing removed by corridor, roads taking precedence where a road "
         "was also walked; lines noded at every crossing so each is a "
         "point-to-point polyline. Class from measured speed and gradient, "
         "not from file names."),
        STYLE, folders)

    m = gdf.to_crs(METRIC)
    print(f"\nwrote {STEM}.{{kml,geojson,gpkg}} to {OUT.relative_to(ROOT)}")
    for label in by_class:
        s = m[m["class"] == label]
        print(f"  {label:6s} {len(s):3d} polylines  {s.length.sum()/1000:7.1f} km")
    print(f"  TOTAL  {len(m):3d} polylines  {m.length.sum()/1000:7.1f} km "
          f"(from {raw_km:,.0f} km of recordings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
