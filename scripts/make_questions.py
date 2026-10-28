"""The questions only. One ward, one map, one question at a time.

    python3 scripts/make_questions.py

Writes outputs/access/QUESTIONS.md and outputs/access/fig_q_*.png.

Will, 28 Oct 2026: "He is easily confused. Clear map and question of what you
need to know. Nothing extraneous."

So this is not a list of work. It is only the things nobody here can answer
from the data: nine facilities that the ward tables record without saying
which village they are in, and one at Afore where part of a row was found and
part was not. Everything that can be worked out has been worked out already
and is not repeated here.

Each ward gets one map showing its villages and nothing else, then its
questions, one line each, with somewhere to write the answer.
"""
from pathlib import Path
import csv
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe          # noqa: E402
import matplotlib.pyplot as plt              # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (          # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)
from make_access_figures import (             # noqa: E402
    INK, INK_SOFT, load, north_arrow, relief, scalebar,
)
from make_population_kml import indicative    # noqa: E402
from make_villages_kml import collect         # noqa: E402
from ward_profile import load_profile, variants  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECONCILED = ROOT / "outputs" / "access" / "facilities_reconciled.csv"
OUT_MD = ROOT / "outputs" / "access" / "QUESTIONS.md"
FIG_DIR = ROOT / "outputs" / "access"

VILLAGE = "#C9681F"
FOOT = "#9C9A94"
MIN_SPAN_M = 2500

# Plain words for what the ward table calls a facility. "Aid Post + CHW house"
# is not a question anyone can answer out loud.
def plain(facility):
    f = facility.lower()
    if "airstrip" in f:
        return "the airstrip"
    if "aid post" in f and "chw" in f:
        return "the aid post with the CHW house"
    if "aid post" in f:
        return "the aid post"
    if "elementary" in f:
        return "the elementary school"
    if "primary" in f:
        return "the primary school"
    if "high school" in f:
        return "the high school"
    if "health" in f:
        return "the health centre"
    return facility.split(",")[0].lower()


def main():
    with RECONCILED.open() as fh:
        rec = list(csv.DictReader(fh))

    unnamed = [r for r in rec
               if r["verdict"] in ("PARTIAL", "LIKELY")
               and r["village"].strip().lower() == "not named"]
    partial = [r for r in rec if r["verdict"] == "PARTIAL"]

    mapped = collect()
    places, aliases = load_places(), load_aliases()
    ind = indicative()

    def where(name):
        for v in variants(name):
            if not v:
                continue
            if v.lower() in mapped:
                return mapped[v.lower()], False
            hit = best_tier(candidates(v, places, aliases))
            if hit:
                al = aliases.get(str(hit[0]["name"]).strip().lower())
                nm = str(al["to"] if al and al["to"] else hit[0]["name"]).lower()
                if nm in mapped:
                    return mapped[nm], False
        for v in variants(name):
            if v.strip().lower() in ind:
                lon, lat = ind[v.strip().lower()]
                return {"name": name, "lon": lon, "lat": lat}, True
        return None, False

    by_ward = {}
    for r in load_profile():
        by_ward.setdefault(r["ward"].strip(), set()).add(r["village"].strip())

    roads, foot, boundary, _vg, _sa = load()
    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)

    n = 0
    lines = ["# Questions for Russell", "",
             "Each page is one ward. The map shows the villages in that ward. "
             "Under it is the question. Write the village name on the line, "
             "and record the point when you are there.", "",
             "Where a name says **(approx)** we are not sure exactly where "
             "that village is, so the dot is only roughly right. Ask locally.",
             ""]

    for ward in sorted({r["ward"] for r in unnamed}):
        rows = [r for r in unnamed if r["ward"] == ward]
        pts = [(v, *where(v)) for v in sorted(by_ward.get(ward, set()))]
        pts = [(v, p, a) for v, p, a in pts if p]
        lines += ["---", "", f"## {ward}", ""]
        if pts:
            fig = FIG_DIR / f"fig_q_{re.sub(r'[^a-z0-9]+', '_', ward.lower())}.png"
            draw(fig, ward, pts, roads, foot, to_utm)
            lines += [f"![{ward}]({fig.name})", ""]
        for r in rows:
            n += 1
            lines += [f"**{n}. Which village in {ward} has "
                      f"{plain(r['facility'])}?**", "",
                      "Village: ______________________________", ""]

    for r in partial:
        n += 1
        lines += ["---", "", f"## {r['ward']} — {r['village']}", "",
                  f"**{n}. You said Afore station is all collected, and we "
                  f"have 34 points from Afore. But we have the three CHW "
                  f"houses and no Health Centre. Is there a Health Centre "
                  f"building there, separate from the CHW houses?**", "",
                  "Yes / No: ____________    If yes, please record it.", ""]

    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT_MD}")
    print(f"  {n} questions over {len({r['ward'] for r in unnamed})} wards")


def draw(path, ward, pts, roads, foot, to_utm):
    xs, ys = [], []
    for _v, p, _a in pts:
        x, y = to_utm.transform(p["lon"], p["lat"])
        xs.append(x); ys.append(y)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    # Generous, because the names are set large for reading in the field and
    # a label that runs off the edge takes the whole map with it: savefig's
    # tight box grows to include it and the picture arrives as a map with a
    # band of white beside it.
    half = max(MIN_SPAN_M, (max(xs) - min(xs)) * 0.95, (max(ys) - min(ys)) * 0.95)
    extent = (cx - half, cx + half, cy - half, cy + half)

    fig = plt.figure(figsize=(7.2, 5.6), facecolor="#FFFFFF")
    ax = fig.add_axes([0.01, 0.02, 0.98, 0.95])
    relief(ax, extent)
    foot.plot(ax=ax, color=FOOT, lw=0.7, linestyle=(0, (3, 2)), alpha=0.75, zorder=3)
    roads.plot(ax=ax, color="#7FA8C9", lw=1.4, alpha=0.9, zorder=4)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_axis_off()

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    for village, p, approx in sorted(pts, key=lambda t: t[0]):
        x, y = to_utm.transform(p["lon"], p["lat"])
        ax.plot(x, y, "o", ms=9, mfc=VILLAGE, mec="#FFFFFF", mew=1.2, zorder=8)
        label = f"{village} (approx)" if approx else village
        # Write the name towards the middle of the map first, so a village
        # near the right edge is labelled on its left and the text stays on
        # the paper.
        inward = -1 if x > (extent[0] + extent[1]) / 2 else 1
        for ox, dy in ((10, 4), (10, -12), (0, 12), (0, -17), (10, 13),
                       (10, -22), (18, 4), (18, -12)):
            dx = ox * inward
            t = ax.annotate(label, (x, y), xytext=(dx, dy),
                            textcoords="offset points",
                            ha="left" if dx > 0 else "right" if dx < 0 else "center",
                            fontsize=10, fontweight="bold",
                            color=INK if not approx else INK_SOFT, zorder=9)
            t.set_path_effects([pe.withStroke(linewidth=3.0, foreground="#FFFFFF")])
            box = t.get_window_extent(renderer=renderer).expanded(1.06, 1.3)
            if not any(box.overlaps(b) for b in boxes):
                boxes.append(box)
                break
            t.remove()

    # scalebar() defaults to 10 km, which is twice the width of some of these
    # maps: the bar ran off the side and savefig's tight box stretched the
    # picture to follow it, leaving a band of white beside the map.
    span = extent[1] - extent[0]
    bar = max(b for b in (250, 500, 1000, 2000, 5000, 10000) if b <= span * 0.35)
    north_arrow(ax); scalebar(ax, bar)
    fig.savefig(path, dpi=130, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
