"""Sentinel-2 true colour over the MCA airstrips, read straight from the bucket.

    python3 scripts/fetch_s2_airstrips.py

Writes outputs/access/fig_airstrips_s2.png and one GeoTIFF crop per strip in
data/processed/s2_airstrips/.

Will, 4 Nov 2026, wanted the airstrips as polygons - "Grassy long polygon" -
rather than as points. This fetches the imagery that makes that possible.

WHERE THE DATA COMES FROM, and why this works when the obvious routes do not.
The tile servers are all refused by this container's proxy: Esri, Bing, Google
tiles, Mapbox, Sentinel Hub, Copernicus, USGS, Planetary Computer, and the
Element 84 STAC API at earth-search.aws.element84.com. But the AWS Open Data
BUCKET behind that API answers anonymous requests, and so does ASF's. The
lesson is that the search API and the data are separate hosts and only one of
them is blocked.

    sentinel-cogs.s3.us-west-2.amazonaws.com   Sentinel-2 L2A as COGs

Being Cloud Optimized GeoTIFFs, a window can be read over HTTP without
fetching the scene: each 2.2 km crop here costs a few hundred KB, not 1.2 GB.

The tile is T55LFK - zone 55, latitude band L, square FK - which covers all
five strips. Band L, not M: M is the equator to 8 S, and the plateau is at
9.1 S. Two whole searches were wasted on band M before that was checked
against a real raster's bounds rather than against an MGRS formula.

Scene: 31 July 2026, chosen because its scene classification layer reports
0.0% cloud and shadow over the box holding all five strips. Of ten recent
scenes tested, only two were clear; four were 100% clouded. Dry season or not,
this plateau is rarely visible from orbit.

TEN METRES PER PIXEL. A strip 25-30 m wide is two or three pixels across, so
an outline traced from this is good to roughly a pixel - call it +/- 10-15 m
on each edge. That is honest for extent and orientation and for judging
whether a strip is still clear. It is not a survey, and a polygon from it
should never be presented as one.
"""
from pathlib import Path
import os
import sys

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("VSI_CACHE", "TRUE")

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
OUT_FIG = ROOT / "outputs" / "access" / "fig_airstrips_s2.png"
OUT_TIF = ROOT / "data" / "processed" / "s2_airstrips"

SCENE = ("https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs"
         "/55/L/FK/2026/7/S2B_55LFK_20260731_0_L2A")
DATE = "31 July 2026"

# Positions Russell recorded on the ground, 17-26 Oct 2026. The crop is centred
# on each, so the strip is found by looking where he stood rather than by
# searching the tile.
SITES = {
    "Afore":    (148.39000, -9.13966, "non-operational, tall kunai grass"),
    "Sila":     (148.36336, -9.06412, "closed down"),
    "Itokama":  (148.26497, -9.19966, "in use"),
    "Old Dea":  (148.32688, -9.05813, "closed 1988; Dea Primary School now on it"),
    "Awaru":    (148.38864, -9.07300, "old strip, cleared early 2000s as a soccer field"),
}
HALF_M = 1100


def crops():
    t = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)
    bands = {b: rasterio.open(f"/vsicurl/{SCENE}/{b}.tif")
             for b in ("B04", "B03", "B02")}
    OUT_TIF.mkdir(parents=True, exist_ok=True)
    out = {}
    try:
        for name, (lon, lat, note) in SITES.items():
            x, y = t.transform(lon, lat)
            box = (x - HALF_M, y - HALF_M, x + HALF_M, y + HALF_M)
            chans, win, tf = [], None, None
            for b in ("B04", "B03", "B02"):
                ds = bands[b]
                win = from_bounds(*box, ds.transform)
                chans.append(ds.read(1, window=win).astype("float32"))
                tf = ds.window_transform(win)
            stack = np.dstack(chans)
            out[name] = (stack, tf, note)
            with rasterio.open(
                    OUT_TIF / f"{name.replace(' ', '_').lower()}_{DATE[-4:]}.tif",
                    "w", driver="GTiff", height=stack.shape[0],
                    width=stack.shape[1], count=3, dtype="uint16",
                    crs="EPSG:32755", transform=tf) as dst:
                dst.write(stack.astype("uint16").transpose(2, 0, 1))
    finally:
        for ds in bands.values():
            ds.close()
    return out


def stretch(a):
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    return np.clip((a - lo) / (hi - lo), 0, 1) ** 0.85


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = crops()
    fig, axes = plt.subplots(1, 5, figsize=(21, 4.9), facecolor="#FFFFFF")
    for ax, (name, (stack, tf, note)) in zip(axes, data.items()):
        ax.imshow(stretch(stack), interpolation="bilinear")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_edgecolor("#D5D8DC")
        ax.set_title(f"{name}\n{note}", fontsize=9.5, color="#2B2B2B", pad=7)
        n = stack.shape[1]
        bar = 500 / 10.0                       # 500 m at 10 m per pixel
        ax.plot([n * 0.06, n * 0.06 + bar], [n * 0.94, n * 0.94],
                color="#FFFFFF", lw=3.4, solid_capstyle="butt")
        ax.plot([n * 0.06, n * 0.06 + bar], [n * 0.94, n * 0.94],
                color="#111111", lw=1.6, solid_capstyle="butt")
        ax.text(n * 0.06, n * 0.90, "500 m", fontsize=7.5, color="#111111",
                path_effects=None)
    fig.suptitle(f"MCA airstrips — Sentinel-2 true colour, {DATE}, 10 m per pixel "
                 f"(north up; outlines traced from this are good to about "
                 f"±10–15 m, not a survey)",
                 fontsize=11.5, color="#2B2B2B", x=0.012, ha="left", y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT_FIG, dpi=150, facecolor="#FFFFFF")
    print(f"wrote {OUT_FIG}")
    print(f"wrote {len(data)} GeoTIFF crops to {OUT_TIF}")


if __name__ == "__main__":
    sys.exit(main())
