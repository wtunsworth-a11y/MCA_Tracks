"""Report the structure of every source file in data/raw.

Run before any processing so the layer names, CRS, geometry types and extents
are on the record and can be checked against expectations.
"""

import warnings
from pathlib import Path

import geopandas as gpd
import pyogrio

warnings.filterwarnings("ignore")

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
SUFFIXES = {".gpkg", ".gpx", ".kmz", ".kml"}


def describe(path):
    print(f"\n{'=' * 78}\n{path.name}  ({path.stat().st_size:,} bytes)\n{'=' * 78}")
    try:
        layers = [row[0] for row in pyogrio.list_layers(path)]
    except Exception as exc:
        print(f"  !! cannot open: {type(exc).__name__}: {exc}")
        return

    for layer in layers:
        try:
            gdf = gpd.read_file(path, layer=layer)
        except Exception as exc:
            print(f"  [{layer}] !! read failed: {type(exc).__name__}: {exc}")
            continue

        if gdf.empty:
            print(f"  [{layer}] empty")
            continue

        geom_types = sorted(set(gdf.geometry.geom_type.dropna()))
        crs = gdf.crs.to_string() if gdf.crs else "UNDEFINED"
        minx, miny, maxx, maxy = gdf.total_bounds
        print(f"  [{layer}] {len(gdf)} features | {', '.join(geom_types)} | CRS {crs}")
        print(f"      bounds  x {minx:.5f} .. {maxx:.5f}   y {miny:.5f} .. {maxy:.5f}")

        # Attribute columns that actually carry data — empty ones are noise.
        populated = [
            c
            for c in gdf.columns
            if c != "geometry" and gdf[c].notna().any() and (gdf[c].astype(str).str.strip() != "").any()
        ]
        if populated:
            print(f"      fields: {', '.join(populated)}")
            for col in populated:
                vals = gdf[col].dropna().astype(str).str.strip()
                vals = vals[vals != ""]
                sample = vals.unique()[:4]
                print(f"        - {col}: {', '.join(repr(v[:45]) for v in sample)}")

        # Vertex count matters for line data: it tells us GPS log density.
        if any(t in geom_types for t in ("LineString", "MultiLineString")):
            total = 0
            for geom in gdf.geometry.dropna():
                parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
                total += sum(len(p.coords) for p in parts)
            print(f"      vertices: {total:,}")


def main():
    files = sorted(p for p in RAW.iterdir() if p.suffix.lower() in SUFFIXES)
    print(f"Found {len(files)} source file(s) in {RAW}")
    for path in files:
        describe(path)


if __name__ == "__main__":
    main()
