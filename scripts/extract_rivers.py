"""Pull the named rivers out of the MLA repo's HydroRIVERS layer.

Writes data/reference/rivers.geojson, which the zone map draws.

HydroRIVERS carries no names at all - only IDs - so the names have to come
from somewhere else and be attached by geometry. OpenStreetMap has all five
rivers named, so each OSM course is sampled every 250 m and every sample is
snapped to the nearest HydroRIVERS reach; the stem that most of the samples
land on takes the name.

That method was checked before it was trusted. The Bariji was identified
independently last October from 14 field waypoints named Bareji or Baraji,
which all fell on stem 50432013. Snapping the OSM Bariji to the same network
puts 97 % of its samples on that same stem, median 122 m away. Two unrelated
sources agreeing on one ID is the reason the other four are believed.

Why HydroRIVERS geometry rather than the OSM lines it was named from:
HydroRIVERS is continuous, and the 8|9 zone boundary is cut along its Bariji
reaches, so drawing anything else would show the river beside the boundary it
is supposed to be. OSM's Bariji is 74 km in three disconnected pieces against
HydroRIVERS' continuous 102.5 km; drawn, it would break into fragments.

The cost is accuracy, and it is not the same for every river. Bariji, Kumusi
and Musa snap within about 200 m, which is a couple of pixels on the zone
map. The Pongani does not: median 979 m, and only 88 % of its samples agree
on a stem, because HydroRIVERS holds just 21 km of it at order 3. It is drawn
because it was asked for, but it is the one line on the map that may be a
kilometre from the water.

Needs MCA_MLA's data/hydrorivers_oro_clip_major.gpkg, which is not in this
repository. Fetch just that one file rather than cloning 3.5 GB:

    git clone --depth 1 --filter=blob:none --no-checkout \
        https://github.com/wtunsworth-a11y/mca_mla DIR
    git -C DIR sparse-checkout init --no-cone
    echo data/hydrorivers_oro_clip_major.gpkg > DIR/.git/info/sparse-checkout
    git -C DIR checkout HEAD

Run:  python3 scripts/extract_rivers.py DIR/data/hydrorivers_oro_clip_major.gpkg
"""
from pathlib import Path
import sys

import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "reference" / "rivers.geojson"

# stem -> name, settled by the snapping described above. The percentage is how
# many of that river's OSM samples landed on this stem, and the metres are the
# median distance from the OSM course to it.
STEMS = {
    50432013: ("Bariji", 97, 122),
    50431235: ("Musa", 100, 203),
    50423794: ("Kumusi", 100, 165),
    50426669: ("Girua", 96, 232),
    50431103: ("Pongani", 88, 979),
}


def main(gpkg):
    hr = gpd.read_file(gpkg)
    keep = hr[hr["MAIN_RIV"].isin(STEMS)].copy()
    keep["river"] = keep["MAIN_RIV"].map(lambda m: STEMS[m][0])
    keep["name_confidence_pct"] = keep["MAIN_RIV"].map(lambda m: STEMS[m][1])
    keep["osm_offset_m"] = keep["MAIN_RIV"].map(lambda m: STEMS[m][2])
    cols = ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "ORD_STRA",
            "DIS_AV_CMS", "river", "name_confidence_pct", "osm_offset_m",
            "geometry"]
    keep = keep[[c for c in cols if c in keep.columns]]
    keep.to_file(OUT, driver="GeoJSON")
    print(f"wrote {OUT}")
    for name, grp in keep.groupby("river"):
        print(f"  {name:8s} {len(grp):4d} reaches  {grp.LENGTH_KM.sum():6.1f} km  "
              f"max order {grp.ORD_STRA.max()}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
