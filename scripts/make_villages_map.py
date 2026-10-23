"""Every village and hamlet we hold a position for, drawn.

outputs/access/fig_villages.png

The picture of mca_villages.kml: it imports that script's collect() rather
than gathering the positions again, so the map and the file cannot disagree
about where anything is or how well we know it.

Shape carries confidence, which is the thing a reader most needs and the
thing a plain dot hides:

  * a filled circle, sized by households, is a surveyed village
  * a filled diamond is a position someone placed or confirmed on the ground
  * a small open circle is a hamlet from the field waypoint file
  * a hollow grey cross is a cluster we inferred and nobody has confirmed

The last of those has been wrong before - Vouka had no village at it and
Ondoro turned out to be roadside - so it is drawn as the weakest mark on the
map rather than as another dot.
"""
from pathlib import Path
import csv
import sys

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_access_figures import (  # noqa: E402
    BOUNDARY_EDGE, INK, INK_SOFT, LAND, inset, load, north_arrow, relief,
    scalebar,
)
from make_villages_kml import collect, ACCESS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "access" / "fig_villages.png"

SURVEY = "#C9681F"
GROUND = "#2E7D4F"
HAMLET = "#8E6FA0"
GUESS = "#9A9A9A"
FOOT = "#9C9A94"

# Labelled: everything big enough to orient by, plus the places a reader
# looks for first. Labelling all 158 makes the plateau unreadable.
LABEL_MIN_HH = 120
ALWAYS = {"Afore", "Itokama", "Kaura", "Siribu", "Umbuara", "Gora", "Kokoro",
          "Toma", "Jaure", "Aiari"}


def households():
    if not ACCESS.exists():
        return {}
    with ACCESS.open() as fh:
        out = {}
        for r in csv.DictReader(fh):
            try:
                out[r["village"].strip().lower()] = int(r["households"])
            except (ValueError, KeyError):
                pass
        return out


def main():
    best = collect()
    hh = households()
    roads, foot, boundary, _vg, _sa = load()

    fig = plt.figure(figsize=(11.5, 8.6), facecolor="#FFFFFF")
    ax = fig.add_axes([0.015, 0.025, 0.97, 0.93])
    ax.set_facecolor("#FFFFFF")

    minx, miny, maxx, maxy = boundary.total_bounds
    padx, pady = (maxx - minx) * 0.06, (maxy - miny) * 0.06
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)

    relief(ax, extent)
    boundary.plot(ax=ax, facecolor=LAND, edgecolor="none", alpha=0.30, zorder=1)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.0,
                           linestyle=(0, (6, 3)), zorder=2)
    foot.plot(ax=ax, color=FOOT, lw=0.45, linestyle=(0, (3, 2)), alpha=0.6,
              zorder=3)
    roads.plot(ax=ax, color="#7FA8C9", lw=1.0, alpha=0.85, zorder=4)

    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)

    groups = {"gazetteer": [], "ground": [], "waypoint file": [],
              "GPS-inferred": []}
    for rec in best.values():
        src = rec["src"]
        key = ("ground" if src in ("placed by the team", "field evidence")
               else src)
        if key in groups:
            groups[key].append(rec)

    def xy(rec):
        return to_utm.transform(rec["lon"], rec["lat"])

    # weakest first, so a confirmed position is never hidden under a guess
    for rec in groups["GPS-inferred"]:
        x, y = xy(rec)
        ax.plot(x, y, marker="x", ms=5.0, mew=1.1, color=GUESS, zorder=5)
    for rec in groups["waypoint file"]:
        x, y = xy(rec)
        ax.plot(x, y, "o", ms=4.6, mfc="none", mec=HAMLET, mew=1.1, zorder=6)
    for rec in groups["ground"]:
        x, y = xy(rec)
        ax.plot(x, y, "D", ms=5.6, mfc=GROUND, mec="#FFFFFF", mew=0.7, zorder=8)
    for rec in groups["gazetteer"]:
        x, y = xy(rec)
        n = hh.get(rec["name"].lower(), 0)
        size = 5.0 + (n ** 0.5) * 0.55 if n else 5.0
        ax.plot(x, y, "o", ms=size, mfc=SURVEY, mec="#FFFFFF", mew=0.8,
                alpha=0.95, zorder=7)

    # Labels. adjustText was tried here and dragged names clear across the
    # map, leaving leader lines fanning out of one spot and Siribu sitting
    # over empty ground. This instead tries eight positions around each mark
    # and takes the first that does not collide with a label already placed,
    # so a name never leaves its own village.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    OFFSETS = [(7, 4), (-7, 4), (7, -8), (-7, -8), (0, 9), (0, -12),
               (12, 0), (-12, 0)]
    placed_boxes = []

    def label(rec):
        x, y = xy(rec)
        for dx, dy in OFFSETS:
            ha = "left" if dx > 0 else ("right" if dx < 0 else "center")
            t = ax.annotate(rec["name"], (x, y), xytext=(dx, dy),
                            textcoords="offset points", fontsize=7.6,
                            color=INK, ha=ha, zorder=10)
            t.set_path_effects([pe.withStroke(linewidth=2.6,
                                              foreground="#FFFFFF")])
            box = t.get_window_extent(renderer=renderer).expanded(1.08, 1.25)
            if not any(box.overlaps(b) for b in placed_boxes):
                placed_boxes.append(box)
                return
            t.remove()
        # Nowhere free: keep it anyway rather than silently dropping a village.
        t = ax.annotate(rec["name"], (x, y), xytext=(7, 4),
                        textcoords="offset points", fontsize=7.6, color=INK,
                        zorder=10)
        t.set_path_effects([pe.withStroke(linewidth=2.6, foreground="#FFFFFF")])
        placed_boxes.append(t.get_window_extent(renderer=renderer))

    # Biggest first, so where two names compete the larger village keeps the
    # spot nearest its mark.
    to_label = [r for r in groups["gazetteer"] + groups["ground"]
                if hh.get(r["name"].lower(), 0) >= LABEL_MIN_HH
                or r["name"] in ALWAYS]
    for rec in sorted(to_label, key=lambda r: -hh.get(r["name"].lower(), 0)):
        label(rec)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_axis_off()

    n_hh = sum(hh.get(r["name"].lower(), 0) for r in groups["gazetteer"])
    handles = [
        Line2D([], [], marker="o", ls="none", ms=9, mfc=SURVEY, mec="#FFFFFF",
               label=f"Surveyed village, sized by households "
                     f"({len(groups['gazetteer'])}, {n_hh:,} households)"),
        Line2D([], [], marker="D", ls="none", ms=7, mfc=GROUND, mec="#FFFFFF",
               label=f"Placed or confirmed on the ground "
                     f"({len(groups['ground'])})"),
        Line2D([], [], marker="o", ls="none", ms=7, mfc="none", mec=HAMLET,
               mew=1.1, label=f"Hamlet from the field waypoints "
                              f"({len(groups['waypoint file'])})"),
        Line2D([], [], marker="x", ls="none", ms=7, mew=1.1, color=GUESS,
               label=f"Inferred, unconfirmed ({len(groups['GPS-inferred'])})"),
        Line2D([], [], color="#7FA8C9", lw=1.0, label="Motorable road (recorded)"),
        Line2D([], [], color=FOOT, lw=0.8, linestyle=(0, (3, 2)),
               label="Foot track (recorded)"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.0, linestyle=(0, (6, 3)),
               label="Conservation Area (WDPA)"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=True, framealpha=0.94,
              fontsize=8.4, borderpad=0.8, labelspacing=0.55,
              edgecolor="#D5D8DC").set_zorder(11)

    total = sum(len(v) for v in groups.values())
    ax.set_title(f"Managalas: {total} villages and hamlets we have a position for",
                 fontsize=12.5, color=INK, pad=12, loc="left")
    ax.annotate("mark shape shows how well the position is known, not how big "
                "the place is", xy=(0.0, 1.005), xycoords="axes fraction",
                fontsize=8.2, color=INK_SOFT)

    north_arrow(ax)
    scalebar(ax)
    inset(fig, boundary)

    fig.savefig(OUT, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT}")
    for k, v in groups.items():
        print(f"  {len(v):4d}  {k}")


if __name__ == "__main__":
    main()
