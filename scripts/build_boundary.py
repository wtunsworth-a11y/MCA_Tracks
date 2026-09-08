"""Build the Managalas Conservation Area boundary from the WDPA polygon.

The authoritative boundary is the WDPA (World Database on Protected Areas)
record for Managalas Conservation Area, published by UNEP-WCMC via Protected
Planet. Nothing else is used — an earlier version of this script transcribed the
20-point gazetted survey table out of a Drive PDF, which produced a straight-
sided polygon that is not the boundary in use. That approach has been dropped.

Protected Planet is not reachable from this sandbox (the proxy refuses the
CONNECT), so the download is a manual step:

  1. https://www.protectedplanet.net/  ->  search "Managalas"
  2. Download the protected area as shapefile or GeoJSON
  3. Put the file (or the unzipped folder) in data/raw/

This script then finds it and writes data/processed/mca_boundary.gpkg
(layer "boundary"). Any vector format geopandas can read will do: .shp with its
sidecars, .geojson, .json, .gpkg, .kml.
"""

import sys
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

WGS84 = "EPSG:4326"
UTM55S = "EPSG:32755"

# Filenames from Protected Planet are shaped like WDPA_WDOECM_Sep2026_Public_
# 555637123_shp.zip, so match on the WDPA marker as well as on our own naming.
NAME_HINTS = ("wdpa", "wdoecm", "managalas", "mca_boundary", "protectedplanet")
VECTOR_SUFFIXES = (".shp", ".geojson", ".json", ".gpkg", ".kml", ".zip")


def candidates():
    """Vector files in data/raw that look like a WDPA download."""
    found = []
    for path in sorted(RAW.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VECTOR_SUFFIXES:
            continue
        haystack = str(path.relative_to(RAW)).lower()
        if any(hint in haystack for hint in NAME_HINTS):
            found.append(path)
    return found


def read_any(path):
    """Read one candidate, looking inside a zip if that is what we were given."""
    if path.suffix.lower() != ".zip":
        return gpd.read_file(path)

    # Protected Planet ships a zip; a WDPA shapefile zip often holds three
    # layers (point, polygon, and a combined one). Take the polygons.
    with zipfile.ZipFile(path) as zf:
        inner = [n for n in zf.namelist() if n.lower().endswith((".shp", ".geojson"))]
    if not inner:
        raise ValueError(f"{path.name}: no .shp or .geojson inside")

    frames = []
    for name in inner:
        try:
            frame = gpd.read_file(f"zip://{path}!{name}")
        except Exception:
            continue
        if not frame.empty and frame.geom_type.str.contains("Polygon").any():
            frames.append(frame)
    if not frames:
        raise ValueError(f"{path.name}: no polygon layer inside")
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def main():
    sources = candidates()
    if not sources:
        print("No WDPA boundary file found in data/raw.")
        print()
        print("The MCA boundary is the WDPA polygon, and Protected Planet is not")
        print("reachable from here, so it has to be downloaded by hand:")
        print("  1. https://www.protectedplanet.net/ -> search 'Managalas'")
        print("  2. download as shapefile or GeoJSON")
        print("  3. drop it in data/raw/ (a .zip is fine) and re-run this script")
        print()
        print("Until then no boundary is drawn — better a map with no boundary")
        print("than one with the wrong boundary.")
        return 1

    boundary = None
    for path in sources:
        try:
            frame = read_any(path)
        except Exception as exc:
            print(f"  !! {path.name}: {exc}")
            continue
        polygons = frame[frame.geom_type.str.contains("Polygon")]
        if polygons.empty:
            print(f"  -- {path.name}: no polygons, skipped")
            continue
        print(f"  ++ {path.relative_to(RAW)}: {len(polygons)} polygon feature(s)")
        boundary = polygons.to_crs(WGS84) if polygons.crs else polygons.set_crs(WGS84)
        break

    if boundary is None:
        print("!! found candidate files but none held a usable polygon")
        return 1

    # Several WDPA records can share a name (a designation plus its zones);
    # dissolve to one outline so downstream inside/outside tests are simple.
    merged = boundary.union_all()
    out = gpd.GeoDataFrame(
        [{"name": "Managalas Conservation Area", "source": "WDPA / Protected Planet"}],
        geometry=[merged],
        crs=WGS84,
    )
    area_km2 = out.to_crs(UTM55S).area.iloc[0] / 1e6
    out["area_km2"] = round(area_km2, 1)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    target = PROCESSED / "mca_boundary.gpkg"
    out.to_file(target, layer="boundary", driver="GPKG")

    minx, miny, maxx, maxy = out.total_bounds
    print(f"WDPA boundary -> {area_km2:,.0f} km2")
    print(f"bounds  lon {minx:.4f} .. {maxx:.4f}   lat {miny:.4f} .. {maxy:.4f}")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
