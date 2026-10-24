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
RIVERS = ROOT / "data" / "reference" / "rivers.geojson"
TRACKS = ROOT / "data" / "processed" / "tracks.gpkg"
OVERRIDES = ROOT / "data" / "reference" / "zone_overrides.csv"
OUT_GJ = ROOT / "outputs" / "access" / "zones_voronoi.geojson"
OUT_KML = ROOT / "outputs" / "access" / "zones_voronoi.kml"
OUT_PNG = ROOT / "outputs" / "access" / "fig_zones_voronoi.png"

UTM = "EPSG:32755"
RIVER_BLUE = "#1F6FB2"
ROAD_INK = "#4A3B32"

# The two vehicle roads, keyed by the name the recording carries and
# labelled the way Will asks for them. "Popondetta to Anatua Road" is the
# Popondetta-Afore corridor: it passes within 382 m of Afore and 1 m of
# Popondetta before running on to Anatua. There is a second recording of
# the same corridor, "Road Track - Popondetta to Sakarina Junction", which
# is not drawn because it would lay a near-duplicate line over this one.
ROADS = {
    "Popondetta to Anatua Road": "Popondetta \u2013 Afore Road",
    "Itokama to Afore Road (seg 1)": "Afore \u2013 Itokama Road",
}
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


# The inset map and the legend, in axes fractions, so a river name is never
# written underneath either of them. Taking the midpoint of the longest reach
# put "Kumusi" half off the west edge and behind the inset, and "Bariji" out
# on the lower Bariji miles beyond the conservation area.
KEEP_OUT = [(0.03, 0.65, 0.27, 0.94),   # inset
            (0.68, 0.00, 1.00, 0.17)]   # legend
EDGE_MARGIN = 0.05


def label_candidates(grp, hull, extent):
    """Places a line's name could go, best first.

    Inside the conservation area beats outside it - these are the MCA's
    rivers and roads, and a name out on the lower Bariji thirty kilometres
    past the boundary tells a reader nothing - then bigger water, then a
    longer piece of line. Points under the inset, under the legend or near the edge
    are not offered at all: the midpoint of the longest reach put "Kumusi"
    half off the west edge and behind the inset map.
    """
    x0, x1, y0, y1 = extent
    out = []
    for _, row in grp.iterrows():
        geom = row.geometry
        # Bigger water first, so a river is named on its main stem. Without
        # this "Bariji" went on an order-3 headwater up in zone 1 rather
        # than on the order-4 reach that divides 8 from 9.
        order = int(row["ORD_STRA"]) if "ORD_STRA" in grp.columns else 0
        for part in shapely.get_parts(shapely.GeometryCollection([geom])):
            if part.length <= 0:
                continue
            for f in (0.5, 0.35, 0.65, 0.2, 0.8, 0.45, 0.55, 0.3, 0.7):
                pt = part.interpolate(f, normalized=True)
                fx, fy = (pt.x - x0) / (x1 - x0), (pt.y - y0) / (y1 - y0)
                if not (EDGE_MARGIN < fx < 1 - EDGE_MARGIN
                        and EDGE_MARGIN < fy < 1 - EDGE_MARGIN):
                    continue
                if any(a < fx < c and b < fy < d for a, b, c, d in KEEP_OUT):
                    continue
                out.append(((hull.contains(pt), order, part.length), pt))
    out.sort(key=lambda kv: kv[0], reverse=True)
    return [pt for _, pt in out]


def fill_unclaimed(zones, hull):
    """Hand the unclaimed eastern ground to zones 8 and 9, split by the Bariji.

    Babarobo is the one village with a real position that the Ward Profile
    files outside the MCA, and it sits in the far east. Its Voronoi cell
    covered the easternmost ground inside the conservation area and was then
    discarded with the other outside cells, which left 26 km2 of the MCA
    belonging to no zone at all.

    Will, 24 Oct 2026: "Extend Zones 8 and 9 along the Bariji River to fill
    the MCA." So the leftover is noded against the river, polygonized, and
    each fragment goes to whichever of 8 or 9 it actually adjoins - the same
    rule that already divides those two upstream, carried east.
    """
    claimed = shapely.union_all(list(zones.geometry))
    gap = hull.difference(claimed)
    parts = [g for g in shapely.get_parts(shapely.GeometryCollection([gap]))
             if g.area > 10_000]
    if not parts:
        return zones

    z = {r["zone"]: r.geometry for _, r in zones.iterrows()}
    if "8" not in z or "9" not in z:
        return zones
    river = (gpd.read_file(RIVER).to_crs(zones.crs).union_all()
             if RIVER.exists() else None)

    add = {"8": [], "9": []}
    for part in parts:
        # Only ground these two can reach. A hole elsewhere is not theirs.
        if min(part.distance(z["8"]), part.distance(z["9"])) > 1.0:
            continue
        lines = [part.boundary]
        if river is not None:
            cut = river.intersection(part.buffer(1.0))
            if not cut.is_empty:
                lines.append(cut)
        frags = list(shapely.get_parts(
            shapely.GeometryCollection(
                list(shapely.ops.polygonize(shapely.node(
                    shapely.union_all(lines)))))))
        if not frags:
            frags = [part]
        for f in frags:
            if f.area < 10_000:
                continue
            d8, d9 = f.distance(z["8"]), f.distance(z["9"])
            if d8 == d9:
                # Touching both: go with whichever it shares more edge with.
                d8 = -f.buffer(1.0).intersection(z["8"]).area
                d9 = -f.buffer(1.0).intersection(z["9"]).area
            add["8" if d8 < d9 else "9"].append(f)

    moved = 0.0
    for zone, frags in add.items():
        if not frags:
            continue
        i = zones.index[zones["zone"] == zone][0]
        before = zones.at[i, "geometry"].area
        zones.at[i, "geometry"] = shapely.union_all([zones.at[i, "geometry"]]
                                                   + frags)
        gained = (zones.at[i, "geometry"].area - before) / 1e6
        moved += gained
        print(f"  filled {gained:.1f} km2 of unclaimed MCA into zone {zone}")
    if not moved:
        print("  nothing to fill")
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
    # Still before anything is measured: no ground inside the MCA is left out.
    zones = fill_unclaimed(zones, hull)
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
    from make_access_figures import (BOUNDARY_EDGE, INK, inset,
                                     north_arrow, relief, scalebar)

    fig = plt.figure(figsize=(12, 8.8), facecolor="#FFFFFF")
    ax = fig.add_axes([0.015, 0.025, 0.97, 0.92])
    minx, miny, maxx, maxy = boundary.total_bounds
    padx, pady = (maxx - minx) * 0.06, (maxy - miny) * 0.06
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)
    relief(ax, extent)

    # Flat fills. The hatching that used to mark the zones resting on
    # approximate positions is gone: every zone on this map rests on
    # indications, so singling some out invited the reader to trust the rest.
    # The title carries that instead.
    cmap = plt.get_cmap("tab20")
    order = sorted(zones["zone"], key=lambda z: (int(z.rstrip("ab")) if z.rstrip("ab").isdigit() else 99, z))
    colours = {z: cmap(i % 20) for i, z in enumerate(order)}
    for _, r in zones.iterrows():
        gpd.GeoSeries([r.geometry], crs=zones.crs).plot(
            ax=ax, facecolor=colours[r["zone"]], edgecolor="#FFFFFF", lw=1.2,
            alpha=0.55, zorder=3)

    # Over the fills, not under them. The zones now tile the conservation area
    # exactly, so the WDPA line sits beneath their outer edge and was invisible
    # - a legend entry for a symbol nothing on the map showed.
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.2,
                           linestyle=(0, (6, 3)), zorder=12)

    # The rivers, drawn as rivers. Width follows Strahler order so the Musa
    # and the Kumusi read as bigger water than the Girua.
    from shapely.geometry import box as _box
    frame = _box(extent[0], extent[2], extent[1], extent[3])
    hull = boundary.union_all()
    to_name = []                      # (text, candidate points, colour, style)

    if RIVERS.exists():
        rv = gpd.read_file(RIVERS).to_crs(zones.crs).clip(frame)
        for name, grp in rv.groupby("river"):
            lw = 1.1 + 0.42 * (grp["ORD_STRA"].max() - 3)
            grp.plot(ax=ax, color=RIVER_BLUE, lw=lw, alpha=0.95, zorder=8)
            to_name.append((name, label_candidates(grp, hull, extent),
                            RIVER_BLUE, "italic"))

    # The vehicle roads, from the field recordings rather than any gazetteer -
    # these are the two the trucks actually use. Drawn with a white casing so
    # they stay legible crossing a zone fill, and over the rivers, because a
    # road crossing a river is a bridge or a ford, not the other way round.
    if TRACKS.exists():
        tr = gpd.read_file(TRACKS, layer="tracks").to_crs(zones.crs)
        for rec_name, label in ROADS.items():
            grp = tr[tr["name"] == rec_name]
            if grp.empty:
                continue
            grp = grp.clip(frame)
            if grp.empty:
                continue
            grp.plot(ax=ax, color="#FFFFFF", lw=3.8, alpha=0.9, zorder=10)
            grp.plot(ax=ax, color=ROAD_INK, lw=1.9, zorder=11)
            to_name.append((label, label_candidates(grp, hull, extent),
                            ROAD_INK, "normal"))

    good = pts[pts["quality"].isin(["known", "field"])]
    good.plot(ax=ax, color=INK, markersize=9, zorder=6)
    # The approximate positions still SEED the tessellation - they are what
    # gives zone 10 its ground - but they are not drawn. Most of them are
    # hamlets of a village that already has a dot here: Gora's three hamlets,
    # Gorobuna's outliers. A mark beside Gora read as a fourth settlement
    # next to it rather than as part of it.

    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_axis_off()

    ax.legend(handles=[
        Line2D([], [], marker="o", ls="none", color=INK, ms=6,
               label="Villages"),
        Line2D([], [], color=RIVER_BLUE, lw=1.9, label="Rivers"),
        Line2D([], [], color=ROAD_INK, lw=1.9, label="Vehicle roads"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.2, linestyle=(0, (6, 3)),
               label="Conservation Area (WDPA)"),
    ], loc="lower right", frameon=True, framealpha=0.95, fontsize=8.6,
        borderpad=0.8, labelspacing=0.55, edgecolor="#D5D8DC").set_zorder(10)

    ax.set_title("Indicative Map of MCA Zones",
                 fontsize=13, color=INK, pad=12, loc="left")

    # Everything written on the map, placed against measured text boxes
    # rather than hoped-for gaps. The zone numbers go down first and keep
    # their ground: a reader looks for those before anything else, and the
    # first pass at this wrote "Afore - Itokama Road" straight through the
    # numbers 3 and 5 and "Bariji" across the 1.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []

    def put(text, xy, dx, dy, **kw):
        t = ax.annotate(text, xy, xytext=(dx, dy), textcoords="offset points",
                        ha="center", **kw)
        t.set_path_effects([pe.withStroke(linewidth=kw.pop("halo", 2.8),
                                          foreground="#FFFFFF")])
        return t, t.get_window_extent(renderer=renderer).expanded(1.06, 1.3)

    for _, r in zones.iterrows():
        c = r.geometry.representative_point()
        t, box = put(f"{r['zone']}", (c.x, c.y), 0, 0, va="center",
                     fontsize=13, fontweight="bold", color=INK, zorder=13)
        boxes.append(box)

    for text, cands, colour, style in to_name:
        for pt in cands:
            for dy in (7, -14, 15, -22):
                t, box = put(text, (pt.x, pt.y), 0, dy, fontsize=8.2,
                             style=style, color=colour, zorder=14)
                if not any(box.overlaps(b) for b in boxes):
                    boxes.append(box)
                    break
                t.remove()
            else:
                continue
            break

    north_arrow(ax); scalebar(ax); inset(fig, boundary)
    fig.savefig(OUT_PNG, dpi=200, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    draw(*main())
