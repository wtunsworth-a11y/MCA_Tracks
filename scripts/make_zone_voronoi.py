"""An indication of the zone boundaries, from the village points alone.

outputs/access/zones_voronoi.geojson
outputs/access/zones_voronoi.kml
outputs/access/fig_zones_voronoi.png

THIS IS NOT A BOUNDARY. No zone boundary has ever been surveyed; the real
ones wait on the clan mapping. What this does is divide the plateau so that
every piece of ground goes to the nearest village, then merge the pieces
belonging to each zone. Where two zones' villages interleave, the line
between them is an artefact of which village happens to sit nearer, not a
line anyone recognises.

It is built from 79 Ward Profile villages, of which:

  * 58 have a position we stand behind or that came from the field
  * 17 are INDICATIVE - dragged by hand, some admitted guesses
  * 4 have no position at all and sit on their ward centre

So roughly a quarter of the points steering these polygons are approximate,
and the figure marks them so it is visible where a boundary rests on a guess.

Clipped to the WDPA conservation area. Villages recorded as outside the MCA
are used as points - leaving them out would push the outer zones' boundaries
outward past where they belong - but no polygon is kept for them.
"""
from pathlib import Path
import sys

import geopandas as gpd
import shapely
from shapely.geometry import MultiPoint, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)
from make_population_kml import indicative  # noqa: E402
from make_villages_kml import collect  # noqa: E402
from ward_profile import load_profile, variants  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BOUNDARY = ROOT / "data" / "processed" / "mca_boundary.gpkg"
RIVER = ROOT / "data" / "reference" / "bariji_river.geojson"
OVERRIDES = ROOT / "data" / "reference" / "zone_overrides.csv"
OUT_GJ = ROOT / "outputs" / "access" / "zones_voronoi.geojson"
OUT_KML = ROOT / "outputs" / "access" / "zones_voronoi.kml"
OUT_PNG = ROOT / "outputs" / "access" / "fig_zones_voronoi.png"

UTM = "EPSG:32755"
OUTSIDE = "Outside MCA"


def village_points():
    """Ward Profile villages as points, each with its zone and how well placed."""
    mapped = collect()
    places, aliases = load_places(), load_aliases()
    ind = indicative()

    def canon(n):
        al = aliases.get(str(n).strip().lower())
        return al["to"] if al and al["to"] else n

    def known(name):
        for v in variants(name):
            if v.lower() in mapped:
                return mapped[v.lower()]
            hit = best_tier(candidates(v, places, aliases))
            if hit:
                c = canon(hit[0]["name"])
                if c.lower() in mapped:
                    return mapped[c.lower()]
        return None

    rows = load_profile()

    # Zone reassignments confirmed in the field, overriding the Ward Profile's
    # own column. See zone_overrides.csv: these apply to the zone map only.
    if OVERRIDES.exists():
        import csv as _csv
        with OVERRIDES.open() as fh:
            ov = {(r["village"].strip().lower(), r["ward"].strip()): r["to_zone"]
                  for r in _csv.DictReader(l for l in fh
                                           if not l.startswith("#"))}
        moved = 0
        for r in rows:
            k = (r["village"].strip().lower(), r["ward"].strip())
            if k in ov and r["zone"] != ov[k]:
                r["zone"] = ov[k]
                moved += 1
        if moved:
            print(f"  {moved} villages reassigned by zone_overrides.csv")

    anchor = {}
    for r in rows:
        hit = known(r["village"])
        if hit:
            anchor.setdefault(r["ward"], []).append((hit["lon"], hit["lat"]))
    anchor = {w: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v))
              for w, v in anchor.items()}

    recs = []
    for r in rows:
        hit = known(r["village"])
        if hit:
            lon, lat = hit["lon"], hit["lat"]
            q = "field" if hit["src"] in ("waypoint file", "GPS-inferred") else "known"
        elif r["village"].strip().lower() in ind:
            lon, lat = ind[r["village"].strip().lower()]
            q = "indicative"
        else:
            lon, lat = anchor.get(r["ward"], (148.33, -9.13))
            q = "none"
        recs.append(dict(village=r["village"], zone=r["zone"], ward=r["ward"],
                         population=r["population"], households=r["households"],
                         quality=q, geometry=Point(lon, lat)))
    return gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:4326")


def recut_8_9(zones, pts):
    """Replace the 8|9 Voronoi line with the Bariji River.

    Will, 23 Oct 2026: the boundary between zones 8 and 9 is the Bariji River.
    The Voronoi guess was between 123 m and 2.8 km away from it and left 35 km
    of the river inside zone 9 rather than along the edge, so this is a
    correction rather than a tidy-up.

    The river branches, so it cannot simply be used to cut the polygon in two.
    Instead the shared outline and the river are noded together and
    polygonized, which yields however many fragments the branching implies,
    and each fragment is then given to whichever zone's villages actually sit
    in it. A fragment with no village goes to the nearer zone's villages -
    there is nothing better to go on, and saying so is better than pretending
    the river closed neatly.
    """
    if not RIVER.exists() or not {"8", "9"} <= set(zones["zone"]):
        print("  (8/9 not re-cut: river or zones missing)")
        return zones

    from shapely.ops import polygonize, unary_union

    river = gpd.read_file(RIVER).to_crs(zones.crs)
    z8 = zones.loc[zones["zone"] == "8", "geometry"].iloc[0]
    z9 = zones.loc[zones["zone"] == "9", "geometry"].iloc[0]
    both = unary_union([z8, z9])

    lines = unary_union([both.boundary, unary_union(list(river.geometry))])
    frags = [f for f in polygonize(lines) if f.representative_point().within(both)]
    if len(frags) < 2:
        print("  (8/9 not re-cut: the river does not divide the pair)")
        return zones

    v8 = pts[(pts["zone"] == "8")].geometry
    v9 = pts[(pts["zone"] == "9")].geometry
    out = {"8": [], "9": []}
    for f in frags:
        n8 = int(v8.within(f).sum())
        n9 = int(v9.within(f).sum())
        if n8 or n9:
            out["8" if n8 >= n9 else "9"].append(f)
        else:
            d8 = v8.distance(f.representative_point()).min() if len(v8) else 1e12
            d9 = v9.distance(f.representative_point()).min() if len(v9) else 1e12
            out["8" if d8 <= d9 else "9"].append(f)

    before = {"8": z8.area / 1e6, "9": z9.area / 1e6}
    for z, parts in out.items():
        if parts:
            zones.loc[zones["zone"] == z, "geometry"] = unary_union(parts)
    after = {z: zones.loc[zones["zone"] == z, "geometry"].iloc[0].area / 1e6
             for z in ("8", "9")}
    print(f"  re-cut 8|9 along the Bariji River from {len(frags)} fragments: "
          f"zone 8 {before['8']:.0f} -> {after['8']:.0f} km2, "
          f"zone 9 {before['9']:.0f} -> {after['9']:.0f} km2")
    return zones


def main():
    pts = village_points().to_crs(UTM)
    boundary = gpd.read_file(BOUNDARY).to_crs(UTM)
    hull = boundary.union_all()

    # Several villages share one position - Kawowoki 1 and 2, Anatua 1 and 2 -
    # and a Voronoi cannot split a point from itself. One seed per distinct
    # position, taking the zone of the most populous village on it.
    pts["key"] = pts.geometry.apply(lambda g: (round(g.x, 1), round(g.y, 1)))
    seeds = (pts.sort_values("population", ascending=False)
                .drop_duplicates("key", keep="first").reset_index(drop=True))
    print(f"{len(pts)} villages -> {len(seeds)} distinct positions")

    # Voronoi over a generous envelope, then clip: without the padding the
    # outermost cells are cut short of the boundary and leave slivers.
    env = MultiPoint(list(seeds.geometry)).envelope.buffer(40000)
    cells = shapely.voronoi_polygons(MultiPoint(list(seeds.geometry)),
                                     extend_to=env, only_edges=False)
    cells = list(shapely.get_parts(cells))

    # voronoi_polygons does not promise cell order, so match each back by
    # which seed it contains rather than by index.
    owner = []
    for cell in cells:
        hits = seeds[seeds.geometry.within(cell)]
        owner.append(hits.index[0] if len(hits) else None)

    rows = []
    for cell, idx in zip(cells, owner):
        if idx is None:
            continue
        clipped = cell.intersection(hull)
        if clipped.is_empty:
            continue
        s = seeds.loc[idx]
        rows.append(dict(zone=s["zone"], village=s["village"],
                         quality=s["quality"], geometry=clipped))
    cellgdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=UTM)

    # Dissolve to one polygon per zone. Villages outside the MCA contributed
    # seeds - they have to, or the outer zones bulge - but keep no territory.
    zones = (cellgdf[cellgdf["zone"] != OUTSIDE]
             .dissolve(by="zone", aggfunc="first").reset_index())
    # Before measuring anything: the 8|9 edge is a river, not a guess.
    zones = recut_8_9(zones, pts)
    zones["area_km2"] = (zones.geometry.area / 1e6).round(1)

    # How much of each zone's area is steered by an approximate point.
    approx = {}
    for z, grp in cellgdf[cellgdf["zone"] != OUTSIDE].groupby("zone"):
        tot = grp.geometry.area.sum()
        bad = grp[grp["quality"].isin(["indicative", "none"])].geometry.area.sum()
        approx[z] = round(100 * bad / tot, 0) if tot else 0
    zones["pct_approx"] = zones["zone"].map(approx)

    pop = pts[pts["zone"] != OUTSIDE].groupby("zone")["population"].sum()
    zones["population"] = zones["zone"].map(pop)

    out = zones.to_crs("EPSG:4326")
    out.to_file(OUT_GJ, driver="GeoJSON")
    try:
        out.to_file(OUT_KML, driver="KML")
    except Exception as exc:                       # KML driver is not always built in
        print(f"  (KML not written: {exc})")

    print(f"wrote {OUT_GJ}")
    print(f"{'zone':<6}{'km2':>9}{'people':>9}{'% of area on a guess':>22}")
    for _, r in zones.sort_values("zone").iterrows():
        print(f"{r['zone']:<6}{r['area_km2']:>9.1f}{int(r['population'] or 0):>9}"
              f"{r['pct_approx']:>21.0f}%")
    print(f"{'total':<6}{zones['area_km2'].sum():>9.1f}"
          f"{int(zones['population'].sum()):>9}")
    return zones, pts, boundary


def draw(zones, pts, boundary):
    """Draw it, with the approximate points marked so the weak edges show."""
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from make_access_figures import (BOUNDARY_EDGE, INK, INK_SOFT, inset,
                                     north_arrow, relief, scalebar)

    fig = plt.figure(figsize=(12, 8.8), facecolor="#FFFFFF")
    ax = fig.add_axes([0.015, 0.025, 0.97, 0.92])
    minx, miny, maxx, maxy = boundary.total_bounds
    padx, pady = (maxx - minx) * 0.06, (maxy - miny) * 0.06
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)
    relief(ax, extent)

    # A zone whose shape rests mostly on guesses is hatched, not just coloured.
    cmap = plt.get_cmap("tab20")
    order = sorted(zones["zone"], key=lambda z: (int(z.rstrip("ab")) if z.rstrip("ab").isdigit() else 99, z))
    colours = {z: cmap(i % 20) for i, z in enumerate(order)}
    for _, r in zones.iterrows():
        heavy = (r["pct_approx"] or 0) >= 50
        gpd.GeoSeries([r.geometry], crs=zones.crs).plot(
            ax=ax, facecolor=colours[r["zone"]], edgecolor="#FFFFFF", lw=1.2,
            alpha=0.55, hatch="//" if heavy else None, zorder=3)

    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.2,
                           linestyle=(0, (6, 3)), zorder=5)

    # The one edge on this map that is a real feature rather than a guess.
    river = None
    if RIVER.exists():
        river = gpd.read_file(RIVER).to_crs(zones.crs)
        river.plot(ax=ax, color="#1F6FB2", lw=1.9, alpha=0.95, zorder=8)

    good = pts[pts["quality"].isin(["known", "field"])]
    weak = pts[pts["quality"].isin(["indicative", "none"])]
    good.plot(ax=ax, color=INK, markersize=9, zorder=6)
    weak.plot(ax=ax, color="#B03A2E", marker="x", markersize=38, linewidth=1.4,
              zorder=7)

    for _, r in zones.iterrows():
        c = r.geometry.representative_point()
        t = ax.annotate(f"{r['zone']}", (c.x, c.y), ha="center", va="center",
                        fontsize=13, fontweight="bold", color=INK, zorder=9)
        t.set_path_effects([pe.withStroke(linewidth=3.2, foreground="#FFFFFF")])

    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_axis_off()

    ax.legend(handles=[
        Line2D([], [], marker="o", ls="none", color=INK, ms=6,
               label=f"Village with a position we stand behind ({len(good)})"),
        Line2D([], [], marker="x", ls="none", color="#B03A2E", ms=8, mew=1.6,
               label=f"Village placed by guess or not at all ({len(weak)})"),
        Patch(facecolor="#CCCCCC", edgecolor="#FFFFFF", hatch="//",
              label="Zone whose shape rests mostly on those guesses"),
        Line2D([], [], color="#1F6FB2", lw=1.9,
               label="Bariji River - the real 8|9 boundary"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.2, linestyle=(0, (6, 3)),
               label="Conservation Area (WDPA)"),
    ], loc="lower right", frameon=True, framealpha=0.95, fontsize=8.6,
        borderpad=0.8, labelspacing=0.55, edgecolor="#D5D8DC").set_zorder(10)

    ax.set_title("Indicative zones - only the 8|9 edge is a real boundary",
                 fontsize=13, color=INK, pad=12, loc="left")
    ax.annotate("zones 8 and 9 are divided along the Bariji River, which Will "
                "confirmed. Every other line is merely where one village's "
                "ground meets another's, and a quarter of the villages "
                "steering them are approximate",
                xy=(0.0, 1.004), xycoords="axes fraction", fontsize=8.4,
                color=INK_SOFT)
    north_arrow(ax); scalebar(ax); inset(fig, boundary)
    fig.savefig(OUT_PNG, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    draw(*main())
