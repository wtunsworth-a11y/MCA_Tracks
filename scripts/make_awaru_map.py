"""Awaru on Sentinel-2, wide enough to show Numba and Kawowoki with it.

    python3 scripts/make_awaru_map.py

Writes outputs/access/fig_awaru_s2.png.

Will, 12 Nov 2026: "Show me Awaru on a stellite overlay to the extent where i
can see Numba and Kawowoki as well."

Awaru is the village that had no position in this repository at all, so its old
airstrip was filed at Kaura 1.63 km away - plausible only because the WARD is
Kaura. Its polygon came from Will's village_footprints.kml on 12 Nov. Numba sits
2.6 km north of it and Kawowoki 3.1 km south, so a window holding all three also
holds Kaura, Koeno and Sakarina, which is useful: it shows the ward boundary
problem in one view.

Imagery as in fetch_s2_airstrips.py: the AWS Open Data bucket
sentinel-cogs.s3.us-west-2.amazonaws.com, anonymous, windowed over HTTP, tile
T55LFK (band L - M is the equator to 8 S). Scene of 31 July 2026, the one recent
date with no cloud over this corner of the plateau.

Ten metres per pixel. Footprint outlines are Will's; everything else is
positioned from Russell's recordings.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("VSI_CACHE", "TRUE")

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
from shapely.geometry import shape, box

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "access" / "fig_awaru_s2.png"
SCENE = ("https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs"
         "/55/L/FK/2026/7/S2B_55LFK_20260731_0_L2A")
DATE = "31 July 2026"

# Chosen to hold Awaru, Numba and Kawowoki with room to breathe.
WEST, EAST = 148.3485, 148.4075
SOUTH, NORTH = -9.1105, -9.0420


def imagery():
    t = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)
    x0, y0 = t.transform(WEST, SOUTH)
    x1, y1 = t.transform(EAST, NORTH)
    chans, tf = [], None
    for b in ("B04", "B03", "B02"):
        with rasterio.open(f"/vsicurl/{SCENE}/{b}.tif") as ds:
            win = from_bounds(x0, y0, x1, y1, ds.transform)
            chans.append(ds.read(1, window=win).astype("float32"))
            tf = ds.window_transform(win)
    return np.dstack(chans), tf, (x0, x1, y0, y1)


def stretch(a):
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    return np.clip((a - lo) / (hi - lo), 0, 1) ** 0.85


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patheffects import withStroke

    rgb, tf, (x0, x1, y0, y1) = imagery()
    img = np.dstack([stretch(rgb[:, :, i]) for i in range(3)])

    t = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)
    win = box(WEST, SOUTH, EAST, NORTH)

    gj = json.loads((ROOT / "data" / "reference" /
                     "village_footprints.geojson").read_text())
    fig, ax = plt.subplots(figsize=(11.5, 13.0), dpi=200)
    ax.imshow(img, extent=[x0, x1, y0, y1], origin="upper", interpolation="bilinear")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)

    halo = [withStroke(linewidth=3.2, foreground="black")]
    # Labels are placed by measuring them. The limits MUST be set before the
    # first draw or every extent comes back in default axes space and the
    # whole collision test is nonsense - that bug has been written twice here.
    fig.canvas.draw()
    placed = []

    def put(x, y, text, **kw):
        """Place text at the first offset that does not overlap what is there."""
        for dx, dy in ((0, 14), (0, -16), (16, 0), (-16, 0), (14, 14),
                       (-14, -14), (14, -14), (-14, 14), (0, 30), (0, -32),
                       (30, 0), (-30, 0)):
            t_ = ax.annotate(text, (x, y), xytext=(dx, dy),
                             textcoords="offset points",
                             ha="center" if abs(dx) < 5 else
                                ("left" if dx > 0 else "right"),
                             va="center", path_effects=halo, **kw)
            fig.canvas.draw()
            bb = t_.get_window_extent().expanded(1.06, 1.22)
            if not any(bb.overlaps(o) for o in placed):
                placed.append(bb)
                return t_
            t_.remove()
        t_ = ax.annotate(text, (x, y), xytext=(0, 14),
                         textcoords="offset points", ha="center", va="center",
                         path_effects=halo, **kw)
        fig.canvas.draw()
        placed.append(t_.get_window_extent())
        return t_

    shown = 0
    for f in gj["features"]:
        g = shape(f["geometry"])
        if not g.intersects(win):
            continue
        shown += 1
        name = f["properties"]["village"]
        ward = f["properties"]["ward"]
        focus = name == "Awaru"
        for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            xs, ys = zip(*[t.transform(a, b) for a, b in poly.exterior.coords])
            ax.plot(xs, ys, lw=2.6 if focus else 1.6,
                    color="#ffd400" if focus else "#49e0ff", zorder=5)
            ax.fill(xs, ys, color="#ffd400" if focus else "#49e0ff",
                    alpha=0.17 if focus else 0.09, zorder=4)
        # anchor the label on the polygon's TOP edge, not its centroid, so the
        # outline itself stays readable
        c = g.centroid
        cx, _ = t.transform(c.x, c.y)
        _, top = t.transform(c.x, g.bounds[3])
        put(cx, top, f"{name}\nward {ward} · {f['properties']['area_ha']} ha",
            fontsize=10.0 if focus else 8.0,
            fontweight="bold" if focus else "normal",
            color="#ffd400" if focus else "white", zorder=7)

    # facilities, from the measured list
    import csv
    n_fac = 0
    with (ROOT / "outputs" / "gis" / "mca_government_facilities.csv").open() as fh:
        for r in csv.DictReader(l for l in fh if not l.startswith("#")):
            lon, lat = float(r["longitude"]), float(r["latitude"])
            if not (WEST <= lon <= EAST and SOUTH <= lat <= NORTH):
                continue
            n_fac += 1
            fx, fy = t.transform(lon, lat)
            ax.plot(fx, fy, marker="o", ms=6.5, mfc="#ff4d4d", mec="white",
                    mew=1.3, zorder=8)
            put(fx, fy, r["name"], fontsize=7.2, color="white", zorder=9)

    # scale bar
    ax.plot([x0 + 300, x0 + 1300], [y0 + 300, y0 + 300], lw=4, color="white",
            solid_capstyle="butt", zorder=10)
    ax.annotate("1 km", (x0 + 800, y0 + 420), ha="center", fontsize=9,
                color="white", path_effects=halo, zorder=10)

    ax.set_title(f"Awaru, with Numba and Kawowoki — Sentinel-2, {DATE}",
                 fontsize=14, pad=10)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.text(0.5, 0.012,
             "Village outlines from village_footprints.kml (Will, 12 Nov 2026). "
             "Facilities positioned by Russell on the ground. "
             "Imagery 10 m/pixel — outlines are indicative of extent, not survey.",
             ha="center", fontsize=7.6, color="#444")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT.relative_to(ROOT)}  ({shown} village footprints, "
          f"{n_fac} facilities, {img.shape[1]}x{img.shape[0]} px)")


if __name__ == "__main__":
    sys.exit(main())
