"""An addendum map for one ward: its villages, the network, and its facilities.

    python3 scripts/make_ward_map.py "06 Koeno"

Writes outputs/access/fig_ward_map_<ward>.png.

Meant to go in the back of a Ward Profile, so it answers the questions a ward
profile leaves open: where are the villages, what can you drive to, what can
you only walk to, and what is actually built here.

THERE IS NO WARD BOUNDARY. None exists in this repository or in the MLA one,
so this does not draw one and does not imply one. What it draws is the ward's
own villages and everything recorded around them, which is a different and
more honest thing than a polygon nobody has surveyed.

A facility belongs to the ward whose village it NAMES - "Sila Airstrip" is
Sila's wherever it stands - and only falls back to the nearest village when it
names none we know. That order matters: Afore High School stands at Sakarina
and would otherwise be filed under Afore, 8.5 km away.

Positions that are dragged pins rather than survey are drawn hollow and
labelled "(approx)", because several wards are mostly those and a map that
hides it is worse than no map.
"""
from pathlib import Path
import csv
import math
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe          # noqa: E402
import matplotlib.pyplot as plt              # noqa: E402
from matplotlib.lines import Line2D          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (          # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)
from make_access_figures import (             # noqa: E402
    BOUNDARY_EDGE, INK, INK_SOFT, load, north_arrow, relief, scalebar,
)
from make_population_kml import indicative    # noqa: E402
from make_villages_kml import collect         # noqa: E402
from reconcile_facilities import kinds_of     # noqa: E402
from ward_profile import load_profile, variants  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WP = ROOT / "data" / "reference" / "waypoints_facilities.csv"
RIVERS = ROOT / "data" / "reference" / "rivers.geojson"
OUT_DIR = ROOT / "outputs" / "access"

VILLAGE = "#C9681F"
FOOT = "#9C9A94"
ROAD = "#1F6FB2"

# One mark per kind of thing, so the map reads without counting colours.
# Marker, colour, size, label. The three school levels share a square and
# differ by size and tone, because they are the same kind of thing at three
# scales; an airstrip gets an X because a dash vanished against the relief.
MARK = {
    "elementary school": ("s", "#58A55C", 6.5, "Elementary school"),
    "primary school":    ("s", "#1B7A3E", 8.5, "Primary school"),
    "high school":       ("s", "#0B3D23", 10.5, "High / secondary school"),
    "aid post":          ("P", "#E07B39", 8.0, "Aid post"),
    "health centre":     ("P", "#A5281B", 9.5, "Health centre"),
    "chw house":         ("P", "#E8A09A", 7.0, "CHW house"),
    "airstrip":          ("X", "#6C3483", 10.0, "Airstrip"),
    "church":            ("^", "#8E6FA0", 8.0, "Church"),
    "office":            ("D", "#34495E", 7.5, "Government office"),
    "guest house":       ("o", "#B7950B", 7.5, "Guest house"),
}
OTHER = ("o", "#808B96", 6.0, "Other recorded point")


# A school is one institution with many buildings. "Afore High School Teacher's
# house", "... Boys Dormitory", "... 2 in 1 building" are all ONE school, and
# the first version of this map drew a green square for each of them: ward 06
# Koeno appeared to have 39 facilities when it has three schools, a health
# centre, a church and an airstrip. Will, 4 Nov 2026: "How many schools in that
# one ward? Or did you show teachers houses as separate schools?"
#
# So a point's name is cut at the kind word, and everything sharing the cut is
# one institution drawn as one mark.
INSTITUTION = re.compile(
    r"^(.*?\b(?:elementary|primary|high|secondary)\s+school"
    r"|.*?\bhealth\s+cent(?:re|er)"
    r"|.*?\baid\s+post"
    r"|.*?\bchurch"
    r"|.*?\bairstrip"
    r"|.*?\boffice)\b", re.I)

# A point that only POINTS AT something is not that thing.
NOT_THE_PLACE = re.compile(r"^\s*(track leading to|hamlet of|road to|path to)\b", re.I)


def institution_of(name):
    """The institution a recorded point belongs to, or None if it is its own
    thing - a creek, a tomb, a hamlet."""
    if NOT_THE_PLACE.match(name or ""):
        return None
    m = INSTITUTION.match(name or "")
    if not m:
        return None
    label = " ".join(m.group(1).split())
    # Sakarina Health Center and Sakarina Health Centre are one building.
    return re.sub(r"\bcenter\b", "Centre", label, flags=re.I)


def km(a, b):
    lo1, la1, lo2, la2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def main(ward):
    mapped = collect()
    places, aliases = load_places(), load_aliases()
    ind = indicative()
    profile = load_profile()

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

    rows = [r for r in profile if r["ward"].strip() == ward]
    if not rows:
        sys.exit(f"no ward called {ward!r} in the Ward Profile")
    vills = []
    for r in rows:
        p, approx = where(r["village"])
        if p:
            vills.append((r["village"], p, approx, r["households"], r["population"]))
    if not vills:
        sys.exit(f"no position for any village in {ward}")

    # Which ward each known village belongs to, for attributing points by name.
    vill_ward = {}
    for r in profile:
        for v in variants(r["village"]):
            if v and v.lower() in mapped:
                vill_ward.setdefault(v.lower(), r["ward"].strip())

    with WP.open() as fh:
        pts = [p for p in csv.DictReader(l for l in fh if not l.startswith("#"))]
    for p in pts:
        p["lon"], p["lat"] = float(p["lon"]), float(p["lat"])

    def owner(p):
        """Which ward a recorded point belongs to.

        The name first - "Sila Airstrip" is Sila's wherever it stands - but
        only if the named village is actually nearby. Afore High School is
        named after the LLG and stands at Sakarina, 8.5 km from Afore and in
        a different ward, so the first version of this filed twenty points,
        a whole secondary school, under the wrong ward. The ground decides
        when the name and the ground disagree.
        """
        flat = " ".join(re.sub(r"[^a-z0-9 ]", " ", p["name"].lower()).split())
        here = (p["lon"], p["lat"])
        named = [(len(v), v, w) for v, w in vill_ward.items()
                 if len(v) >= 4 and v in flat]
        if named:
            _n, v, w = max(named)
            if km(here, (mapped[v]["lon"], mapped[v]["lat"])) <= 3.0:
                return w
        best = None
        for v, w in vill_ward.items():
            d = km(here, (mapped[v]["lon"], mapped[v]["lat"]))
            if best is None or d < best[0]:
                best = (d, w)
        return best[1] if best and best[0] <= 5.0 else None

    here = [p for p in pts if owner(p) == ward]
    print(f"{ward}: {len(vills)} villages placed, {len(here)} facility points")

    draw(ward, vills, here)


def draw(ward, vills, pts):
    roads, foot, boundary, _vg, _sa = load()
    from pyproj import Transformer
    import geopandas as gpd
    from shapely.geometry import box as _box
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)

    xs, ys = [], []
    for _n, p, _a, _h, _pop in vills:
        x, y = to_utm.transform(p["lon"], p["lat"])
        xs.append(x); ys.append(y)
    for p in pts:
        x, y = to_utm.transform(p["lon"], p["lat"])
        xs.append(x); ys.append(y)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(1500, (max(xs) - min(xs)) * 0.70, (max(ys) - min(ys)) * 0.70)
    extent = (cx - half, cx + half, cy - half, cy + half)
    frame = _box(extent[0], extent[2], extent[1], extent[3])

    # The legend goes BESIDE the map, not on it. Inside, it covered Koeno -
    # the ward's largest village, 1,144 people - and the label underneath it
    # was the only sign anything was there.
    fig = plt.figure(figsize=(12.6, 8.4), facecolor="#FFFFFF")
    ax = fig.add_axes([0.012, 0.02, 0.74, 0.92])
    relief(ax, extent)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.1,
                           linestyle=(0, (6, 3)), zorder=3)
    if RIVERS.exists():
        rv = gpd.read_file(RIVERS).to_crs("EPSG:32755").clip(frame)
        if len(rv):
            rv.plot(ax=ax, color="#7FB3D5", lw=1.3, alpha=0.9, zorder=4)
    foot.plot(ax=ax, color=FOOT, lw=0.9, linestyle=(0, (3, 2)), alpha=0.85, zorder=5)
    roads.plot(ax=ax, color="#FFFFFF", lw=3.4, alpha=0.9, zorder=6)
    roads.plot(ax=ax, color=ROAD, lw=1.7, zorder=7)

    # Group the points into institutions, then draw one mark each.
    insts, loose = {}, []
    for p in pts:
        key = institution_of(p["name"])
        if key is None:
            loose.append(p)
        else:
            insts.setdefault(key, []).append(p)

    used = {}
    for p in loose:
        x, y = to_utm.transform(p["lon"], p["lat"])
        m, c, ms, lab = OTHER
        used[lab] = (m, c, ms)
        ax.plot(x, y, marker=m, ms=ms, mfc=c, mec="#FFFFFF", mew=0.8,
                ls="none", zorder=8)

    inst_marks = []
    for key, group in insts.items():
        ks = kinds_of(key)
        kind = next((k for k in MARK if k in ks), None)
        m, c, ms, lab = MARK.get(kind, OTHER)
        used[lab] = (m, c, ms)
        lon = sum(q["lon"] for q in group) / len(group)
        lat = sum(q["lat"] for q in group) / len(group)
        x, y = to_utm.transform(lon, lat)
        ax.plot(x, y, marker=m, ms=ms + 3, mfc=c, mec="#FFFFFF", mew=1.3,
                ls="none", zorder=10)
        inst_marks.append((key, x, y, len(group)))
    print(f"  {len(insts)} institutions, {len(loose)} other points")
    for key, group in sorted(insts.items()):
        print(f"    {key:46s} {len(group):3d} building(s)/point(s)")

    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_axis_off()
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []

    # Sila 1 and Sila 2 are two Ward Profile rows on one position, and drawing
    # them separately put one marker exactly under the other and silently
    # dropped a label. One mark, both names, both counts.
    groups = []
    for name, p, approx, hh, pop in vills:
        key = (round(p["lon"], 4), round(p["lat"], 4))
        for g in groups:
            if g["key"] == key:
                g["names"].append(name); g["hh"] += hh; g["pop"] += pop
                g["approx"] = g["approx"] or approx
                break
        else:
            groups.append(dict(key=key, p=p, names=[name], hh=hh, pop=pop,
                               approx=approx))

    for g in sorted(groups, key=lambda g: -g["pop"]):
        name = " + ".join(g["names"])
        p, approx, hh, pop = g["p"], g["approx"], g["hh"], g["pop"]
        x, y = to_utm.transform(p["lon"], p["lat"])
        ax.plot(x, y, "o", ms=13, mfc="#FFFFFF" if approx else VILLAGE,
                mec=VILLAGE, mew=2.0, zorder=11)
        label = f"{name} (approx)" if approx else name
        label += f"\n{pop:,} people, {hh} households"
        inward = -1 if x > (extent[0] + extent[1]) / 2 else 1
        placed = False
        for ox, dy in ((13, 2), (13, -26), (0, 16), (0, -36), (13, 20), (13, -48),
                       (24, 8), (24, -32), (0, 30), (0, -54)):
            t = ax.annotate(label, (x, y), xytext=(ox * inward, dy),
                            textcoords="offset points",
                            ha="left" if inward > 0 else "right",
                            fontsize=9, fontweight="bold",
                            color=INK if not approx else INK_SOFT, zorder=12)
            t.set_path_effects([pe.withStroke(linewidth=3.0, foreground="#FFFFFF")])
            b = t.get_window_extent(renderer=renderer).expanded(1.04, 1.15)
            if not any(b.overlaps(o) for o in boxes):
                boxes.append(b)
                placed = True
                break
            t.remove()
        if not placed:
            # Nowhere clear: keep it anyway. A village silently missing its
            # name is worse than a name sitting close to another.
            t = ax.annotate(label, (x, y), xytext=(13 * inward, 2),
                            textcoords="offset points",
                            ha="left" if inward > 0 else "right",
                            fontsize=9, fontweight="bold", color=INK, zorder=12)
            t.set_path_effects([pe.withStroke(linewidth=3.0, foreground="#FFFFFF")])
            boxes.append(t.get_window_extent(renderer=renderer))

    for key, x, y, n in sorted(inst_marks, key=lambda t: -t[3]):
        txt = f"{key}\n{n} buildings recorded" if n > 1 else key
        inward = -1 if x > (extent[0] + extent[1]) / 2 else 1
        for ox, dy in ((10, 0), (10, -18), (0, 11), (0, -24), (10, 14),
                       (10, -32), (20, 6), (20, -26)):
            t = ax.annotate(txt, (x, y), xytext=(ox * inward, dy),
                            textcoords="offset points",
                            ha="left" if inward > 0 else "right",
                            fontsize=7.8, color=INK_SOFT, zorder=12)
            t.set_path_effects([pe.withStroke(linewidth=2.6,
                                              foreground="#FFFFFF")])
            b = t.get_window_extent(renderer=renderer).expanded(1.04, 1.2)
            if not any(b.overlaps(o) for o in boxes):
                boxes.append(b)
                break
            t.remove()

    handles = [Line2D([], [], marker="o", ls="none", ms=10, mfc=VILLAGE,
                      mec=VILLAGE, label="Village"),
               Line2D([], [], marker="o", ls="none", ms=10, mfc="#FFFFFF",
                      mec=VILLAGE, mew=2.0, label="Village, position approximate")]
    handles += [Line2D([], [], marker=m, ls="none", ms=ms, mfc=c,
                       mec="#FFFFFF", label=lab)
                for lab, (m, c, ms) in sorted(used.items())]
    handles += [Line2D([], [], color=ROAD, lw=1.7, label="Motorable road (recorded)"),
                Line2D([], [], color=FOOT, lw=0.9, linestyle=(0, (3, 2)),
                       label="Foot track (recorded)"),
                Line2D([], [], color=BOUNDARY_EDGE, lw=1.1, linestyle=(0, (6, 3)),
                       label="Conservation Area (WDPA)")]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.015, 1.0),
              frameon=True, framealpha=1.0, fontsize=8.6, borderpad=0.8,
              labelspacing=0.6, edgecolor="#D5D8DC").set_zorder(14)

    people = sum(v[4] for v in vills)
    ax.set_title(f"Ward {ward} — {len(vills)} villages, {people:,} people, "
                 f"{len(insts)} facilities from {len(pts)} recorded points",
                 fontsize=13, color=INK, pad=12, loc="left")
    shared = [g for g in groups if len(g["names"]) > 1]
    if shared:
        says = "; ".join(" + ".join(g["names"]) for g in shared)
        ax.annotate(f"{says} share one recorded position and are drawn as one "
                    f"mark - we cannot yet separate them on the ground",
                    xy=(0.0, 1.004), xycoords="axes fraction", fontsize=8.4,
                    color=INK_SOFT)
    span = extent[1] - extent[0]
    bar = max(b for b in (250, 500, 1000, 2000, 5000, 10000) if b <= span * 0.35)
    north_arrow(ax); scalebar(ax, bar)
    out = OUT_DIR / f"fig_ward_map_{re.sub(r'[^a-z0-9]+', '_', ward.lower())}.png"
    fig.savefig(out, dpi=170, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
