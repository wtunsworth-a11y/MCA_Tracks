"""Figure A (the map) and Figure B (market reach), replacing the old Figure 8.

The fault being corrected is that the old figure drew straight lines between
market stops, which on a dissected plateau implies vehicles travelling where
there is no road. So the governing rule here is that a line is drawn only where
a vehicle has actually been recorded travelling. Zones 4, 9 and 10 have no road
and get none; their villages are drawn in red and named as unreachable.

Palette and type as specified: DejaVu Sans 9 pt, #1F4E79 for the circuit and its
stops, #C4C4C4 for other villages, #B03A2E for the roadless zones. Titles and
figure numbers are left out of the image for the document to supply.

Writes outputs/access/fig_mca_map.png and fig_market_reach.png at 200 dpi.
"""

import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import Point

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "access"

WGS84 = "EPSG:4326"
UTM = "EPSG:32755"

CIRCUIT = "#1F4E79"
OTHER = "#C4C4C4"
NOROAD = "#B03A2E"
INK = "#222222"
INK_SOFT = "#666666"
LAND = "#F4F3F0"
BOUNDARY_EDGE = "#9A9A9A"


mpl.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": "#CCCCCC", "text.color": INK,
    "axes.labelcolor": INK, "xtick.color": INK_SOFT, "ytick.color": INK_SOFT,
})


def hillshade(dem_arr, az=315.0, alt=45.0, cell=30.0, z=2.0):
    """A muted relief shade, so the map reads as terrain and not as a photo."""
    gy, gx = np.gradient(dem_arr * z, cell)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az_r, alt_r = np.radians(360.0 - az + 90.0), np.radians(alt)
    hs = (np.sin(alt_r) * np.cos(slope)
          + np.cos(alt_r) * np.sin(slope) * np.cos(az_r - aspect))
    return np.clip(hs, 0, 1)


def load():
    tracks = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks").to_crs(UTM)
    roads = tracks[tracks["mode"] == "Motor road"]
    confirmed = ROOT / "data" / "reference" / "confirmed_roads.csv"
    if confirmed.exists():
        cf = pd.read_csv(confirmed, comment="#")
        hit = tracks["name"].isin(cf["track_name"])
        roads = gpd.GeoDataFrame(pd.concat([roads, tracks[hit]], ignore_index=True),
                                 geometry="geometry", crs=UTM)
    supplied = ROOT / "data" / "reference" / "supplied_roads.geojson"
    if supplied.exists():
        extra = gpd.read_file(supplied).to_crs(UTM)
        roads = gpd.GeoDataFrame(pd.concat([roads, extra], ignore_index=True),
                                 geometry="geometry", crs=UTM)
    foot = tracks[tracks["mode"] == "Foot track"]
    if confirmed.exists():
        foot = foot[~foot["name"].isin(cf["track_name"])]
    boundary = gpd.read_file(PROCESSED / "mca_boundary.gpkg", layer="boundary").to_crs(UTM)
    acc = pd.read_csv(OUT / "mca_village_access.csv")
    acc["zone"] = acc["zone"].astype(str)
    vg = gpd.GeoDataFrame(acc, geometry=[Point(x, y) for x, y in zip(acc.lon, acc.lat)],
                          crs=WGS84).to_crs(UTM)
    sa = gpd.read_file(OUT / "mca_service_areas.geojson").to_crs(UTM)
    return roads, foot, boundary, vg, sa


def relief(ax, extent):
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import reproject, Resampling, calculate_default_transform
    files = sorted((ROOT / "data" / "dem").glob("*.tif"))
    if not files:
        return
    srcs = [rasterio.open(f) for f in files]
    arr, tf = merge(srcs)
    dst_crs = UTM
    left, right, bottom, top = extent
    transform, w, h = calculate_default_transform(
        srcs[0].crs, dst_crs, arr.shape[2], arr.shape[1], *rasterio.transform.array_bounds(
            arr.shape[1], arr.shape[2], tf))
    dst = np.zeros((h, w), dtype=np.float32)
    reproject(arr[0], dst, src_transform=tf, src_crs=srcs[0].crs,
              dst_transform=transform, dst_crs=dst_crs, resampling=Resampling.bilinear)
    b = rasterio.transform.array_bounds(h, w, transform)
    hs = hillshade(dst, cell=abs(transform.a))
    ax.imshow(hs, cmap="Greys_r", vmin=-0.1, vmax=1.35, alpha=0.42,
              extent=(b[0], b[2], b[1], b[3]), origin="upper", zorder=0,
              interpolation="bilinear")


def scalebar(ax, length_m=10000):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * 0.055
    y = y0 + (y1 - y0) * 0.055
    ax.plot([x, x + length_m], [y, y], color=INK, lw=2.4, solid_capstyle="butt",
            zorder=12)
    ax.plot([x, x + length_m / 2], [y, y], color="#FFFFFF", lw=2.4,
            solid_capstyle="butt", zorder=13)
    ax.plot([x, x + length_m], [y, y], color=INK, lw=0.7, zorder=14)
    for xx, lab in ((x, "0"), (x + length_m, f"{length_m//1000} km")):
        ax.text(xx, y + (y1 - y0) * 0.012, lab, ha="center", fontsize=7.5,
                color=INK, zorder=14)


def north_arrow(ax):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x1 - (x1 - x0) * 0.055
    y = y1 - (y1 - y0) * 0.10
    ax.annotate("", xy=(x, y + (y1 - y0) * 0.045), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.3), zorder=14)
    ax.text(x, y - (y1 - y0) * 0.022, "N", ha="center", fontsize=8.5,
            color=INK, zorder=14)


def inset(fig, boundary):
    """Where this is, inside Papua New Guinea."""
    axi = fig.add_axes([0.075, 0.645, 0.165, 0.215])
    axi.set_facecolor("#FFFFFF")
    outline = ROOT / "data" / "reference" / "png_outline.geojson"
    if outline.exists():
        png = gpd.read_file(outline)
        png.plot(ax=axi, facecolor="#E8E7E3", edgecolor="#AAAAAA", lw=0.6)
    c = boundary.to_crs(WGS84).geometry.iloc[0].centroid
    axi.plot([c.x], [c.y], marker="s", ms=5.5, color=NOROAD, zorder=3)
    axi.annotate("Managalas", (c.x, c.y), xytext=(6, -9),
                 textcoords="offset points", fontsize=7, color=INK)
    axi.set_xlim(140.3, 156.3)
    axi.set_ylim(-11.9, -0.9)
    axi.set_xticks([]); axi.set_yticks([])
    axi.set_title("Papua New Guinea", fontsize=7, color=INK_SOFT, pad=3)
    for sp in axi.spines.values():
        sp.set_color("#CCCCCC")


def base(ax, boundary, roads, foot, extent):
    relief(ax, extent)
    boundary.plot(ax=ax, facecolor=LAND, edgecolor="none", alpha=0.35, zorder=1)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.1,
                           linestyle=(0, (6, 3)), zorder=2)
    foot.plot(ax=ax, color="#FFFFFF", lw=2.0, zorder=3)
    foot.plot(ax=ax, color="#7E7C76", lw=0.9, linestyle=(0, (3, 2)), zorder=4)
    roads.plot(ax=ax, color="#FFFFFF", lw=3.4, zorder=5)
    roads.plot(ax=ax, color=CIRCUIT, lw=1.9, zorder=6)


def clamp_into_axes(ax, texts, frac=0.012):
    """Pull any label that still sits outside the frame back inside it.

    adjustText's ensure_inside_axes keeps the anchor in bounds but a long label
    can still overhang, which put Biriri and Gewoya off the right edge.
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    mx, my = (x1 - x0) * frac, (y1 - y0) * frac
    fig = ax.figure
    fig.canvas.draw()
    for t in texts:
        bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
        bb = bb.transformed(ax.transData.inverted())
        dx = dy = 0.0
        if bb.x1 > x1 - mx:
            dx = (x1 - mx) - bb.x1
        if bb.x0 < x0 + mx:
            dx = (x0 + mx) - bb.x0
        if bb.y1 > y1 - my:
            dy = (y1 - my) - bb.y1
        if bb.y0 < y0 + my:
            dy = (y0 + my) - bb.y0
        if dx or dy:
            x, y = t.get_position()
            t.set_position((x + dx, y + dy))


def marker_boxes(ax, xs, ys, sizes, pad_pt=1.5):
    """Display-space boxes around point markers, for adjustText to avoid.

    adjustText works in display coordinates when it is handed Text artists or
    Bbox objects, but converts a PathCollection to data coordinates instead -
    mixing the two produced non-finite values and a cKDTree error. So the
    markers are turned into display-space Bboxes here rather than passed in as
    collections.
    """
    from matplotlib.transforms import Bbox
    px_per_pt = ax.figure.dpi / 72.0
    boxes = []
    for x, y, s in zip(np.asarray(xs), np.asarray(ys), np.asarray(sizes)):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        dx, dy = ax.transData.transform((x, y))
        r = (np.sqrt(float(s)) / 2.0 + pad_pt) * px_per_pt
        boxes.append(Bbox([[dx - r, dy - r], [dx + r, dy + r]]))
    return boxes


def village_sizes(hh):
    return 14 + np.sqrt(np.clip(hh, 0, None)) * 7.0


def figure_a(roads, foot, boundary, vg, stops):
    fig, ax = plt.subplots(figsize=(9, 7), facecolor="#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    minx, miny, maxx, maxy = boundary.total_bounds
    padx = (maxx - minx) * 0.06
    pady = (maxy - miny) * 0.06
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)
    base(ax, boundary, roads, foot, extent)

    # Drawn from the measured/overridden result, not from a zone list: Kiera and
    # Natanga are in Zone 3 and have no road access, which a zone rule misses.
    roadless = vg[vg["road_reachable"] == "no"]
    served = vg[vg["road_reachable"] != "no"]
    ax.scatter(served.geometry.x, served.geometry.y,
               s=village_sizes(served["households"]), color=OTHER,
               edgecolor="#8C8C8C", linewidths=0.5, zorder=7)
    ax.scatter(roadless.geometry.x, roadless.geometry.y,
               s=village_sizes(roadless["households"]), color=NOROAD,
               edgecolor="#7B2018", linewidths=0.5, zorder=8)

    su = stops.to_crs(UTM)
    road_stop = su[su["access"] != "track"]
    track_stop = su[su["access"] == "track"]
    ax.scatter(road_stop.geometry.x, road_stop.geometry.y, s=118, marker="o",
               facecolor=CIRCUIT, edgecolor="#FFFFFF", linewidths=1.6, zorder=10)
    # A stop a vehicle cannot reach is not the same thing as one it can, so it
    # is not drawn as though it were: hollow, and named as upgradeable.
    ax.scatter(track_stop.geometry.x, track_stop.geometry.y, s=132, marker="o",
               facecolor="#FFFFFF", edgecolor=CIRCUIT, linewidths=2.2, zorder=10)

    # The frame has to be fixed BEFORE any label is placed. Setting it afterwards
    # meant the repulsion and the clamp both worked against matplotlib's
    # autoscaled limits, which are wider than the final frame - which is how
    # "Afore Saturday" ended up out in the right-hand margin.
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")

    # Six stops and nine roadless villages sit close together, so the labels are
    # placed by repulsion rather than at a fixed offset, which stacked them.
    # Afore is placed by hand in the open ground west of Toma, with a leader back
    # to the stop. Left to the repulsion it was pushed off the map entirely.
    # West of Toma (148.4005 E), and dropped far enough south of Itokama's own
    # label that the two boxes no longer touch - at -9.2205 the "Saturday" box
    # clipped the descender of "Monday".
    afore_at = gpd.GeoSeries([Point(148.3630, -9.2375)], crs=WGS84).to_crs(UTM).iloc[0]

    texts = []
    afore_ann = None
    for (_, r), p in zip(stops.iterrows(), su.geometry):
        suffix = "\ntrack only" if r["access"] == "track" else ""
        if r["stop"] == "Afore":
            afore_ann = ax.annotate(f"{r['stop']}\n{r['day']}", xy=(p.x, p.y),
                        xytext=(afore_at.x, afore_at.y), textcoords="data",
                        fontsize=8.2, color=CIRCUIT, fontweight="bold", zorder=11,
                        ha="center", va="center",
                        arrowprops=dict(arrowstyle="-", color="#9A9A9A", lw=0.6),
                        bbox=dict(boxstyle="round,pad=0.2", fc="#FFFFFFE0",
                                  ec="none"))
            continue
        texts.append(ax.text(p.x, p.y, f"{r['stop']}\n{r['day']}{suffix}",
                             fontsize=8.2,
                             color=CIRCUIT, fontweight="bold", zorder=11,
                             bbox=dict(boxstyle="round,pad=0.2", fc="#FFFFFFE0",
                                       ec="none")))
    for _, r in roadless.iterrows():
        texts.append(ax.text(r.geometry.x, r.geometry.y, r["village"], fontsize=7.2,
                             color=NOROAD, zorder=11,
                             bbox=dict(boxstyle="round,pad=0.15", fc="#FFFFFFCC",
                                       ec="none")))
    from adjustText import adjust_text
    # Keep them inside the frame and near their own point: left unconstrained,
    # repulsion threw Afore and Gewoya clean off the map. The village and stop
    # markers go in as static objects too, so a label box does not come to rest
    # on top of a dot it is not naming.
    static = (marker_boxes(ax, served.geometry.x, served.geometry.y,
                           village_sizes(served["households"]))
              + marker_boxes(ax, roadless.geometry.x, roadless.geometry.y,
                             village_sizes(roadless["households"]))
              + marker_boxes(ax, road_stop.geometry.x, road_stop.geometry.y,
                             np.full(len(road_stop), 118.0))
              + marker_boxes(ax, track_stop.geometry.x, track_stop.geometry.y,
                             np.full(len(track_stop), 132.0)))
    if afore_ann is not None:
        # Padded: the hand-placed box needs a clear margin, or Itokama's label
        # comes to rest with its descenders inside it.
        static.append(afore_ann.get_window_extent(
            ax.figure.canvas.get_renderer()).expanded(1.18, 1.45))
    adjust_text(texts, ax=ax, expand=(1.12, 1.22), max_move=26,
                ensure_inside_axes=True, expand_axes=False,
                objects=static,
                force_text=(0.3, 0.45), force_pull=(0.35, 0.35),
                force_static=(0.22, 0.30),
                arrowprops=dict(arrowstyle="-", color="#9A9A9A", lw=0.6))
    clamp_into_axes(ax, texts)

    ax.set_axis_off()
    scalebar(ax); north_arrow(ax); inset(fig, boundary)

    # Popondetta is off the frame to the north-east; say so rather than crop to it
    ax.annotate("to Popondetta →", xy=(extent[1], maxy - (maxy - miny) * 0.10),
                xytext=(-96, 0), textcoords="offset points", fontsize=8.2,
                color=CIRCUIT, fontweight="bold", zorder=12)

    handles = [
        Line2D([], [], color=CIRCUIT, lw=2.0, label="Motorable road (GPS, driven)"),
        Line2D([], [], color="#7E7C76", lw=1.0, ls=(0, (3, 2)), label="Foot track (GPS, walked)"),
        Line2D([], [], marker="o", ls="", ms=8, mfc=CIRCUIT, mec="#FFFFFF",
               label="Market stop, road access"),
        Line2D([], [], marker="o", ls="", ms=8, mfc="#FFFFFF", mec=CIRCUIT,
               mew=2.0, label="Market stop, track only — upgradeable"),
        Line2D([], [], marker="o", ls="", ms=7, mfc=OTHER, mec="#8C8C8C",
               label="Village (sized by households)"),
        Line2D([], [], marker="o", ls="", ms=7, mfc=NOROAD, mec="#7B2018",
               label="Village with no road access"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.1, ls=(0, (6, 3)),
               label="Conservation Area (WDPA)"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8,
              labelspacing=0.55)
    fig.tight_layout()
    p = OUT / "fig_mca_map.png"
    fig.savefig(p, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {p}")


def figure_b(roads, foot, boundary, vg, sa, stops, acc):
    fig, ax = plt.subplots(figsize=(9, 7), facecolor="#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    minx, miny, maxx, maxy = boundary.total_bounds
    padx = (maxx - minx) * 0.06
    pady = (maxy - miny) * 0.06
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)
    base(ax, boundary, roads, foot, extent)

    # One hue, light to dark with nearness: reach is a magnitude, not a category.
    # Drawn widest band first so the nearer bands sit on top.
    shades = {10: "#CBD9E6", 5: "#8FB0CD", 2: "#4E7FA9"}
    for band in (10, 5, 2):
        sel = sa[sa["band_km"] == band]
        if sel.empty:
            continue
        sel.plot(ax=ax, facecolor=shades[band], edgecolor="none", alpha=0.85,
                 zorder=3 + (10 - band) * 0.1)
    roads.plot(ax=ax, color=CIRCUIT, lw=1.1, zorder=6)

    beyond = acc[(acc["road_reachable"] == "no")]
    vg_beyond = vg[vg["village"].isin(beyond["village"])]
    vg_within = vg[~vg["village"].isin(beyond["village"])]
    ax.scatter(vg_within.geometry.x, vg_within.geometry.y,
               s=village_sizes(vg_within["households"]), color=OTHER,
               edgecolor="#8C8C8C", linewidths=0.5, zorder=7)
    ax.scatter(vg_beyond.geometry.x, vg_beyond.geometry.y,
               s=village_sizes(vg_beyond["households"]), color=NOROAD,
               edgecolor="#7B2018", linewidths=0.5, zorder=8)

    su = stops.to_crs(UTM)
    rs = su[su["access"] != "track"]
    ts = su[su["access"] == "track"]
    ax.scatter(rs.geometry.x, rs.geometry.y, s=110, facecolor=CIRCUIT,
               edgecolor="#FFFFFF", linewidths=1.6, zorder=10)
    ax.scatter(ts.geometry.x, ts.geometry.y, s=124, facecolor="#FFFFFF",
               edgecolor=CIRCUIT, linewidths=2.2, zorder=10)
    for (_, r), p in zip(stops.iterrows(), su.geometry):
        lab = r["stop"] + (" (track only)" if r["access"] == "track" else "")
        ax.annotate(lab, (p.x, p.y), xytext=(8, 6), textcoords="offset points",
                    fontsize=8, color=CIRCUIT, fontweight="bold", zorder=11,
                    bbox=dict(boxstyle="round,pad=0.2", fc="#FFFFFFDD", ec="none"))

    # Zone 4's walk-in to Itokama, and Toma and Biriri, all asked for by name.
    z4 = vg[vg["zone"] == "4"]
    itok = su.geometry.iloc[list(stops["stop"]).index("Itokama")]
    for _, r in z4.iterrows():
        ax.plot([r.geometry.x, itok.x], [r.geometry.y, itok.y], color=NOROAD,
                lw=1.1, ls=(0, (5, 3)), zorder=9)
    if len(z4):
        mid = z4.iloc[0]
        # a third of the way along, and pushed left, to clear the Toma callout
        ax.annotate("Zone 4 walks in to Itokama\n(footpath, not a road)",
                    (mid.geometry.x + (itok.x - mid.geometry.x) * 0.35,
                     mid.geometry.y + (itok.y - mid.geometry.y) * 0.35),
                    xytext=(-118, -26), textcoords="offset points", fontsize=7.4,
                    color=NOROAD, zorder=11,
                    arrowprops=dict(arrowstyle="-", color=NOROAD, lw=0.7),
                    bbox=dict(boxstyle="round,pad=0.22", fc="#FFFFFFEE", ec="none"))

    # Toma and Biriri sit 4 km apart, so their callouts are fanned rather than
    # given the same offset, which overlapped them.
    for name, off in (("Toma", (-34, -58)), ("Biriri", (14, -46))):
        row = acc[acc["village"] == name]
        v = vg[vg["village"] == name]
        if row.empty or v.empty:
            continue
        r = row.iloc[0]
        g = v.geometry.iloc[0]
        ax.annotate(f"{name}: no road; {r['walk_hours_est']:.1f} h walk\n"
                    f"to {r['nearest_stop']} ({r['straight_km']:.1f} km straight)",
                    (g.x, g.y), xytext=off, textcoords="offset points",
                    fontsize=7.4, color=NOROAD, zorder=12,
                    arrowprops=dict(arrowstyle="-", color=NOROAD, lw=0.7),
                    bbox=dict(boxstyle="round,pad=0.22", fc="#FFFFFFEE", ec="none"))

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_axis_off()
    scalebar(ax); north_arrow(ax)

    handles = [
        Patch(facecolor=shades[2], edgecolor="none",
              label="within 2 km by road"),
        Patch(facecolor=shades[5], edgecolor="none", label="2–5 km"),
        Patch(facecolor=shades[10], edgecolor="none", label="5–10 km"),
        Line2D([], [], color="none", label="(corridor drawn 1 km wide to be legible)"),
        Line2D([], [], marker="o", ls="", ms=7, mfc=OTHER, mec="#8C8C8C",
               label="Village on the road network"),
        Line2D([], [], marker="o", ls="", ms=7, mfc=NOROAD, mec="#7B2018",
               label="Village with no road access"),
        Line2D([], [], color=NOROAD, lw=1.1, ls=(0, (5, 3)),
               label="Walk-in route (footpath)"),
        Line2D([], [], marker="o", ls="", ms=8, mfc="#FFFFFF", mec=CIRCUIT,
               mew=2.0, label="Stop with track access only"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8,
              labelspacing=0.55)
    fig.tight_layout()
    p = OUT / "fig_market_reach.png"
    fig.savefig(p, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {p}")


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_access import reconcile_stops

    roads, foot, boundary, vg, sa = load()
    acc = pd.read_csv(OUT / "mca_village_access.csv")
    acc["zone"] = acc["zone"].astype(str)
    vdf = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")
    stops_def, _ = reconcile_stops(vdf)
    stops = gpd.read_file(OUT / "mca_market_stops.geojson")

    figure_a(roads, foot, boundary, vg, stops)
    figure_b(roads, foot, boundary, vg, sa, stops, acc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
