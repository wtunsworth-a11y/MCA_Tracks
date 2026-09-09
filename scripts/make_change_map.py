"""Two-panel comparison: the 1973 track network against what has been walked since.

Read the caveat before the picture. The two panels are not the same kind of
thing, and the difference matters more than anything the map shows:

  1973   a systematic survey. Every track the surveyors could see on the air
         photographs is on the sheet, across the whole sheet.
  now    an opportunistic sample. These are the journeys somebody happened to
         record with a GPS. A route with no modern line is a route nobody has
         recorded yet, which is not the same as a route that is gone.

So the right reading is "where do the modern recordings sit relative to the old
network", not "what has disappeared". Absence on the right-hand panel is
absence of evidence.

The panels are side by side rather than overlaid because overlaying two dense
networks hides the very thing being compared. Colour means mode of travel and
is consistent across both panels, so the eye can carry one meaning between them.

Writes outputs/managalas_1973_vs_now.png
"""

import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"

UTM55S = "EPSG:32755"

SURFACE = "#fcfcfb"
INK = "#1c1b19"
INK_SOFT = "#6b6963"
BOUNDARY_FILL = "#f2f1ec"
BOUNDARY_EDGE = "#898781"

# Colour carries mode of travel and nothing else, so it means the same thing in
# both panels. Era is carried by the panel, not by a second colour dimension.
MOTOR = "#eb6834"
FOOT = "#2a78d6"
GARDEN = "#1baf7a"

MOTOR_TYPES_OLD = {"Road", "Vehicle track"}
MOTOR_TYPES_NEW = {"Road"}


def load():
    old = gpd.read_file(PROCESSED / "historic_tracks.gpkg", layer="tracks_1973")
    new = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    boundary = gpd.read_file(PROCESSED / "mca_boundary.gpkg", layer="boundary")
    return old.to_crs(UTM55S), new.to_crs(UTM55S), boundary.to_crs(UTM55S)


def draw(ax, boundary, groups, title, subtitle):
    boundary.plot(ax=ax, facecolor=BOUNDARY_FILL, edgecolor="none", zorder=0)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, linewidth=1.3,
                           linestyle=(0, (6, 3)), zorder=1)
    for subset, colour, width in groups:
        if subset.empty:
            continue
        subset.plot(ax=ax, color="#ffffff", linewidth=width + 1.4, zorder=2)
        subset.plot(ax=ax, color=colour, linewidth=width, zorder=3)
    ax.set_title(title, fontsize=12, color=INK, loc="left", pad=10, weight="bold")
    ax.text(0, 1.006, subtitle, transform=ax.transAxes, fontsize=8.6,
            color=INK_SOFT, va="bottom")
    ax.set_axis_off()


def main():
    old, new, boundary = load()

    # A common extent, so the two panels are directly comparable.
    minx, miny, maxx, maxy = boundary.total_bounds
    pad = max(maxx - minx, maxy - miny) * 0.03
    xlim = (minx - pad, maxx + pad)
    ylim = (miny - pad, maxy + pad)

    old_motor = old[old["type"].isin(MOTOR_TYPES_OLD)]
    old_foot = old[old["type"] == "Foot track"]
    new_motor = new[new["type"].isin(MOTOR_TYPES_NEW)]
    new_foot = new[new["type"] == "Village-to-village track"]
    new_garden = new[new["type"] == "Garden / survey track"]

    fig, axes = plt.subplots(1, 2, figsize=(15, 9.2), facecolor=SURFACE)
    for ax in axes:
        ax.set_facecolor(SURFACE)

    draw(axes[0], boundary,
         [(old_foot, FOOT, 0.7), (old_motor, MOTOR, 1.7)],
         "1973",
         "T683 topographic survey · every track the surveyors mapped")
    draw(axes[1], boundary,
         [(new_garden, GARDEN, 1.2), (new_foot, FOOT, 1.5), (new_motor, MOTOR, 2.4)],
         "2025–26",
         "GPS recordings · only journeys somebody happened to record")

    for ax in axes:
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_aspect("equal")

    handles = [
        Line2D([], [], color=MOTOR, lw=2.6, label="Road / vehicle track"),
        Line2D([], [], color=FOOT, lw=2.0, label="Foot / village-to-village track"),
        Line2D([], [], color=GARDEN, lw=1.8, label="Garden / survey track (2025–26 only)"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.3, ls=(0, (6, 3)),
               label="Managalas Conservation Area (WDPA)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=9, bbox_to_anchor=(0.5, 0.045))

    fig.suptitle("Managalas tracks: the 1973 survey and what has been recorded since",
                 fontsize=15, color=INK, x=0.5, y=0.965, weight="bold")
    fig.text(0.5, 0.932,
             "Sheets Sibium, Popondetta and Musa · aerial photography 1973 · "
             "georeferencing residual 46–54 m rms, sheet accuracy ±32 m",
             ha="center", fontsize=9, color=INK_SOFT)
    fig.text(0.5, 0.012,
             "A route missing from the right-hand panel has not been recorded with a GPS. "
             "It is not evidence that the route is gone.",
             ha="center", fontsize=9, color=INK, style="italic")

    OUTPUTS.mkdir(exist_ok=True)
    out = OUTPUTS / "managalas_1973_vs_now.png"
    fig.savefig(out, dpi=190, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {out}")

    print(f"\n1973  motorised {old_motor['length_km'].sum():7.0f} km  "
          f"foot {old_foot['length_km'].sum():7.0f} km")
    print(f"now   motorised {new_motor['length_km'].sum():7.0f} km  "
          f"foot {new_foot['length_km'].sum():7.0f} km  "
          f"garden {new_garden['length_km'].sum():6.0f} km")


if __name__ == "__main__":
    main()
