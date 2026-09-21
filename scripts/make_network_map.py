"""The road and foot-track network of the Managalas Plateau, on its own.

outputs/fig_roads_and_trails.png

This is the network as the subject, without the market circuit drawn over it.
Roads and trails are separated by MEASUREMENT, not by what a recording is
called: locally a foot track is called a road, and seven of the fifteen
recordings whose name contains "road" were walked. See NOTES.md for the
evidence hierarchy (GPS speed, overlap with a proven road, gradient, the 1973
sheets) and data/reference/confirmed_roads.csv for the field corrections.

The older outputs/managalas_tracks.png colours by the name each recording
carries and draws the superseded survey boundary. This one uses the measured
mode and the WDPA boundary, so prefer it.

Reuses the figure furniture from make_access_figures.py so the two maps are
visually the same product.
"""
from pathlib import Path
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_access_figures import (  # noqa: E402
    BOUNDARY_EDGE, CIRCUIT, INK, INK_SOFT, LAND, OTHER, UTM,
    clamp_into_axes, inset, load, marker_boxes, north_arrow, relief,
    scalebar, village_sizes,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

FOOT = "#7E7C76"
# Villages named on the map. Everything is drawn; labelling all 46 makes the
# plateau unreadable, so the label set is the largest by households plus the
# places a reader orients by.
LABEL_MIN_HH = 100
ALWAYS_LABEL = {"Afore", "Itokama", "Kaura", "Siribu", "Umbuara", "Gora"}


def main():
    roads, foot, boundary, vg, _sa = load()

    fig, ax = plt.subplots(figsize=(9, 7), facecolor="#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    minx, miny, maxx, maxy = boundary.total_bounds
    padx = (maxx - minx) * 0.06
    pady = (maxy - miny) * 0.06
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)

    relief(ax, extent)
    boundary.plot(ax=ax, facecolor=LAND, edgecolor="none", alpha=0.35, zorder=1)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.1,
                           linestyle=(0, (6, 3)), zorder=2)
    # Trails first, roads over them: where the two run together the road is the
    # thing a reader needs to see.
    foot.plot(ax=ax, color="#FFFFFF", lw=2.2, zorder=3)
    foot.plot(ax=ax, color=FOOT, lw=1.0, linestyle=(0, (3, 2)), zorder=4)
    roads.plot(ax=ax, color="#FFFFFF", lw=3.6, zorder=5)
    roads.plot(ax=ax, color=CIRCUIT, lw=2.1, zorder=6)

    ax.scatter(vg.geometry.x, vg.geometry.y, s=village_sizes(vg["households"]),
               color=OTHER, edgecolor="#8C8C8C", linewidths=0.5, zorder=7)

    # The frame has to be fixed before any label is placed, or the repulsion
    # works against matplotlib's wider autoscaled limits.
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")

    named = vg[(vg["households"] >= LABEL_MIN_HH) | vg["village"].isin(ALWAYS_LABEL)]
    texts = [ax.text(r.geometry.x, r.geometry.y, r["village"], fontsize=7.4,
                     color=INK, zorder=11,
                     bbox=dict(boxstyle="round,pad=0.15", fc="#FFFFFFCC", ec="none"))
             for _, r in named.iterrows()]

    from adjustText import adjust_text
    adjust_text(texts, ax=ax, expand=(1.10, 1.20), max_move=24,
                ensure_inside_axes=True, expand_axes=False,
                objects=marker_boxes(ax, vg.geometry.x, vg.geometry.y,
                                     village_sizes(vg["households"])),
                force_text=(0.3, 0.45), force_pull=(0.35, 0.35),
                force_static=(0.22, 0.30),
                arrowprops=dict(arrowstyle="-", color="#9A9A9A", lw=0.6))
    clamp_into_axes(ax, texts)

    road_km = roads.length.sum() / 1000
    foot_km = foot.length.sum() / 1000
    ax.legend(handles=[
        Line2D([], [], color=CIRCUIT, lw=2.1,
               label=f"Motorable road — {road_km:,.0f} km (GPS, driven)"),
        Line2D([], [], color=FOOT, lw=1.0, ls=(0, (3, 2)),
               label=f"Foot track — {foot_km:,.0f} km (GPS, walked)"),
        Line2D([], [], marker="o", color="none", markerfacecolor=OTHER,
               markeredgecolor="#8C8C8C", markersize=8,
               label="Village (sized by households)"),
        Patch(facecolor=LAND, edgecolor=BOUNDARY_EDGE, ls=(0, (6, 3)),
              label="Conservation Area (WDPA)"),
    ], loc="lower right", frameon=True, facecolor="#FFFFFFDD",
        edgecolor="#DDDDDD", fontsize=8.4, labelspacing=0.55)

    ax.set_axis_off()
    scalebar(ax); north_arrow(ax); inset(fig, boundary)
    ax.annotate("to Popondetta →", xy=(extent[1], maxy - (maxy - miny) * 0.10),
                ha="right", va="center", fontsize=8.6, fontweight="bold",
                color=CIRCUIT, xytext=(-8, 0), textcoords="offset points")
    ax.annotate("road and foot track separated by measured GPS speed, not by "
                "the name a recording carries",
                xy=(0.015, 0.985), xycoords="axes fraction", ha="left",
                va="top", fontsize=7.2, color=INK_SOFT, zorder=12,
                bbox=dict(boxstyle="round,pad=0.25", fc="#FFFFFFB0", ec="none"))

    fig.tight_layout()
    path = OUT / "fig_roads_and_trails.png"
    # bbox_inches="tight" trims the band the inset leaves behind; without it the
    # map is squeezed into the right-hand three quarters of the canvas.
    fig.savefig(path, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")
    print(f"  {len(roads)} road features, {road_km:.1f} km")
    print(f"  {len(foot)} foot features, {foot_km:.1f} km")
    print(f"  {len(named)} of {len(vg)} villages labelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
