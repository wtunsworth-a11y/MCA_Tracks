"""The itinerary drawn on the plateau.

outputs/access/fig_itinerary.png

The same plan as ITINERARY.md - it imports the route from make_itinerary
rather than recomputing it, so the numbers on the map are the numbers in the
document. Stop 1 is Afore; the line is the order to work through, not the
path to take, since the walking follows the tracks underneath.

Legs that still need recording are drawn solid and heavy: those are the hops
where the tracker goes on.
"""
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_access_figures import (  # noqa: E402
    BOUNDARY_EDGE, INK, LAND, UTM, inset, load, north_arrow, relief, scalebar,
)
from make_itinerary import compute, TO_UTM  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "access" / "fig_itinerary.png"

ROUTE = "#B03A2E"        # the order to work through
JOB = "#1F4E79"          # a leg that needs recording
FOOT = "#9C9A94"


def fan_out(xs, ys, extent, rounds=600):
    """Nudge overlapping stop markers apart so every number can be read.

    Eleven of the stops sit within a couple of kilometres of Afore and print
    on top of each other at this scale. The marker moves; a leader line keeps
    it tied to where the place actually is, so nothing is silently relocated.
    """
    sep = (extent[1] - extent[0]) * 0.021
    px, py = list(xs), list(ys)
    for _ in range(rounds):
        moved = False
        for i in range(len(px)):
            for j in range(i + 1, len(px)):
                dx, dy = px[j] - px[i], py[j] - py[i]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist >= sep:
                    continue
                if dist < 1e-6:          # exactly coincident: push along x
                    dx, dy, dist = sep, 0.0, sep
                push = (sep - dist) / 2.0
                ux, uy = dx / dist, dy / dist
                px[i] -= ux * push; py[i] -= uy * push
                px[j] += ux * push; py[j] += uy * push
                moved = True
        if not moved:
            break
    return px, py


def main():
    plan = compute()
    route, resolve = plan["route"], plan["resolve"]
    stops, jobs_by_pair = plan["stops"], plan["jobs_by_pair"]

    roads, foot, boundary, _vg, _sa = load()

    # Map on the left, the key to the numbers on the right: a number on a map
    # is useless without the name beside it, and he should not need the
    # document in his other hand to read the picture.
    fig = plt.figure(figsize=(15.5, 8.6), facecolor="#FFFFFF")
    ax = fig.add_axes([0.015, 0.025, 0.635, 0.93])
    ax.set_facecolor("#FFFFFF")

    xy = [TO_UTM.transform(resolve(n)["lon"], resolve(n)["lat"]) for n in route]
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]

    minx, miny, maxx, maxy = boundary.total_bounds
    minx, maxx = min(minx, min(xs)), max(maxx, max(xs))
    miny, maxy = min(miny, min(ys)), max(maxy, max(ys))
    padx, pady = (maxx - minx) * 0.07, (maxy - miny) * 0.07
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)

    relief(ax, extent)
    boundary.plot(ax=ax, facecolor=LAND, edgecolor="none", alpha=0.30, zorder=1)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.0,
                           linestyle=(0, (6, 3)), zorder=2)
    foot.plot(ax=ax, color=FOOT, lw=0.5, linestyle=(0, (3, 2)), alpha=0.7, zorder=3)
    roads.plot(ax=ax, color="#7FA8C9", lw=1.1, alpha=0.9, zorder=4)

    # the hops, job legs picked out
    n_job = 0
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        is_job = frozenset((a, b)) in jobs_by_pair
        n_job += is_job
        ax.plot([xs[i], xs[i + 1]], [ys[i], ys[i + 1]],
                color=JOB if is_job else ROUTE,
                lw=2.6 if is_job else 1.3,
                alpha=0.95 if is_job else 0.65,
                solid_capstyle="round",
                linestyle="-" if is_job else (0, (5, 2)),
                zorder=6 if is_job else 5)

    # numbered stops; filled where there is something to collect. Markers are
    # fanned out of the Afore pile-up, with a hairline back to the true spot.
    lx, ly = fan_out(xs, ys, extent)
    for i, name in enumerate(route):
        has = bool(stops.get(name))
        if (lx[i] - xs[i]) ** 2 + (ly[i] - ys[i]) ** 2 > 1.0:
            ax.plot([xs[i], lx[i]], [ys[i], ly[i]], color=ROUTE, lw=0.5,
                    alpha=0.55, zorder=6.5)
            ax.plot(xs[i], ys[i], ".", ms=1.8, color=ROUTE, zorder=6.6)
        ax.plot(lx[i], ly[i], "o", ms=11.5,
                mfc="#FFFFFF" if not has else ROUTE,
                mec=ROUTE, mew=1.4, zorder=7)
        ax.text(lx[i], ly[i], str(i + 1), ha="center", va="center",
                fontsize=6.0, color="#FFFFFF" if has else ROUTE,
                fontweight="bold", zorder=8)

    ax.plot(lx[0], ly[0], "o", ms=20, mfc="none", mec=ROUTE, mew=1.8, zorder=7)
    ax.annotate("START", (lx[0], ly[0]), xytext=(0, 18),
                textcoords="offset points", ha="center", fontsize=8.5,
                fontweight="bold", color=ROUTE, zorder=9)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_axis_off()

    n_collect = len([s for s in route if stops.get(s)])
    handles = [
        Line2D([], [], color=JOB, lw=2.6,
               label=f"Walk and record this leg — {n_job} of them"),
        Line2D([], [], color=ROUTE, lw=1.3, linestyle=(0, (5, 2)), alpha=0.7,
               label="Travel on to the next stop"),
        Line2D([], [], color=ROUTE, marker="o", ms=9, ls="none", mfc=ROUTE,
               label=f"Stop with points to collect — {n_collect}"),
        Line2D([], [], color=ROUTE, marker="o", ms=9, ls="none", mfc="#FFFFFF",
               label=f"Stop on the way — {len(route) - n_collect}"),
        Line2D([], [], color="#7FA8C9", lw=1.1, label="Motorable road (recorded)"),
        Line2D([], [], color=FOOT, lw=0.8, linestyle=(0, (3, 2)),
               label="Foot track (recorded)"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.0, linestyle=(0, (6, 3)),
               label="Conservation Area (WDPA)"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=True, framealpha=0.94,
              fontsize=8.5, borderpad=0.8, labelspacing=0.55,
              edgecolor="#D5D8DC").set_zorder(10)

    ax.set_title(f"The round: {len(route)} stops in order from Afore",
                 fontsize=12.5, color=INK, pad=12, loc="left")

    north_arrow(ax)
    scalebar(ax)
    inset(fig, boundary)

    # ---- the key ----
    axk = fig.add_axes([0.665, 0.025, 0.325, 0.93])
    axk.set_axis_off()
    axk.set_xlim(0, 1)
    axk.set_ylim(0, 1)

    axk.text(0, 0.995, "The stops, in order", fontsize=11.5, color=INK,
             fontweight="bold", va="top")
    axk.text(0, 0.963,
             "Filled number = points to collect there.\n"
             "A hairline ties a moved number to its true place.",
             fontsize=7.6, color="#5A6673", va="top")

    rows = [(i + 1, name, len(stops.get(name, []))) for i, name in enumerate(route)]
    half = (len(rows) + 1) // 2
    cols = [rows[:half], rows[half:]]
    top, bottom = 0.915, 0.012
    step = (top - bottom) / max(half, 1)

    for ci, col in enumerate(cols):
        x = 0.02 + ci * 0.50
        for ri, (num, name, npts) in enumerate(col):
            y = top - ri * step
            filled = npts > 0
            axk.plot(x, y + 0.004, "o", ms=10.5, clip_on=False,
                     mfc=ROUTE if filled else "#FFFFFF", mec=ROUTE, mew=1.2)
            axk.text(x, y + 0.004, str(num), ha="center", va="center",
                     fontsize=5.6, fontweight="bold", clip_on=False,
                     color="#FFFFFF" if filled else ROUTE)
            label = name if len(name) <= 20 else name[:19] + "\u2026"
            axk.text(x + 0.035, y + 0.004, label, fontsize=8.2, va="center",
                     color=INK, clip_on=False)
            if npts:
                axk.text(x + 0.455, y + 0.004,
                         f"{npts} pt" + ("s" if npts > 1 else ""),
                         fontsize=7.4, va="center", ha="right",
                         color="#5A6673", clip_on=False)

    fig.savefig(OUT, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT}")
    print(f"  {len(route)} stops, {n_job} legs to record on the route")


if __name__ == "__main__":
    main()
