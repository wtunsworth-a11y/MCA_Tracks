"""Road network, road-distance access, and service areas for the market circuit.

This replaces a figure that drew straight lines between market stops. The point
of the exercise is that a straight line across this plateau is not a journey, so
nothing here measures one.

What the network is built from
------------------------------
GPS recordings made by the project, classified as motorable or walked by
measurement rather than by name (see classify_mode.py - locally a foot track is
called a road, so the names are actively misleading). OpenStreetMap could not be
consulted: every OSM endpoint is unreachable from this environment, which is
recorded in NOTES.md rather than worked around. No segment is drawn anywhere a
vehicle has not been recorded travelling, or which does not follow a line the
1973 survey drew as motorable.

How distance is measured
------------------------
The road lines are noded at their intersections into a graph and shortest paths
run over it, so a village's distance to a market stop is the distance actually
travelled. Villages that the road does not reach are reported as unreachable
rather than given a straight-line figure that would read as a road distance.

Walking time uses Tobler's hiking function over the Copernicus 30 m DEM, along
the real path where one exists and along the straight line where it does not -
and which of the two was used is recorded per village.

Writes outputs/access/: mca_roads.geojson, mca_village_access.csv,
mca_service_areas.geojson
"""

import json
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from shapely.geometry import LineString, Point
from shapely.ops import unary_union, linemerge, nearest_points

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "access"
DEM_DIR = ROOT / "data" / "dem"

WGS84 = "EPSG:4326"
UTM = "EPSG:32755"          # UTM 55S, metres; all distances are computed here

# A village further than this from the network is not served by it. Set from the
# data: every village the brief says is road-served is within 1.4 km, and the
# nearest one it says is not is 7.9 km away, so the gap is wide and unambiguous.
SNAP_MAX_M = 2000
SERVICE_BANDS_KM = (2, 5, 10)

# Positions as given in the brief. Two of them are quoted to two decimal places
# where the rest are quoted to four, which is a tenth of a degree-minute either
# way - about 1.1 km - and it shows: the brief's Siribu sits 2.0 km off the road
# while the surveyed Siribu is 13 m from it. Where the survey file holds the same
# village, its median household position is used instead and the substitution is
# reported. Yoivi is not in the survey file at all, so the brief's rounded
# position stands and is flagged.
MARKET_STOPS = [
    ("Monday",    "Itokama", -9.2003, 148.2657, "1"),
    ("Tuesday",   "Umbuara", -9.1220, 148.2731, "2"),
    ("Wednesday", "Yoivi",   -9.13,   148.44,   "8"),
    ("Thursday",  "Siribu",  -9.09,   148.34,   "3 and 5"),
    ("Friday",    "Kaura",   -9.0632, 148.3775, "6"),
    ("Saturday",  "Afore",   -9.1430, 148.3918, "7a and 7b"),
]


def load_overrides():
    """Field knowledge that outranks the measurement.

    The measured rules can say a vehicle was recorded passing close to a stop.
    They cannot say whether that stop actually has road access: Yoivi's recorded
    proximity is to a coordinate the brief rounded to two decimal places, about
    1.1 km either way, and Siribu's nearest road is 1.5 km off. Somebody who
    knows the ground says both have track access only, upgradeable to road. That
    is recorded here and applied, rather than reached by quietly moving a
    threshold until the numbers agreed.
    """
    path = ROOT / "data" / "access_overrides.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#")
    return {r["stop"]: r for _, r in df.iterrows()}


def reconcile_stops(village_df):
    """Prefer the surveyed position of a stop over a rounded one in the brief."""
    out, notes = [], []
    by_name = {r.vil_name.lower(): r for r in village_df.itertuples()}
    for day, stop, lat, lon, zones in MARKET_STOPS:
        v = by_name.get(stop.lower())
        rounded = (abs(lat * 100 - round(lat * 100)) < 1e-9
                   and abs(lon * 100 - round(lon * 100)) < 1e-9)
        if v is not None and rounded:
            moved = np.hypot((v.lat - lat) * 110570,
                             (v.lon - lon) * 111320 * np.cos(np.radians(abs(lat))))
            notes.append(f"{stop}: brief gives {lat:.2f},{lon:.2f} (2 dp); using the "
                         f"surveyed position {v.lat:.6f},{v.lon:.6f}, {moved:.0f} m away")
            lat, lon = v.lat, v.lon
        elif v is None:
            notes.append(f"{stop}: not in the survey file; the brief's position "
                         f"{lat},{lon} is used as given and is rounded to 2 dp")
        out.append((day, stop, lat, lon, zones))
    return out, notes


# --------------------------------------------------------------------------
# DEM

class Dem:
    def __init__(self):
        files = sorted(DEM_DIR.glob("*.tif"))
        if not files:
            raise SystemExit("no DEM tiles in data/dem")
        self.arr, self.tf = merge([rasterio.open(f) for f in files])
        self.arr = self.arr[0].astype(float)
        self.name = "Copernicus DEM GLO-30 (30 m)"

    def z(self, lons, lats):
        r, c = rasterio.transform.rowcol(self.tf, lons, lats)
        r = np.clip(np.asarray(r), 0, self.arr.shape[0] - 1)
        c = np.clip(np.asarray(c), 0, self.arr.shape[1] - 1)
        return self.arr[r, c]


def tobler_hours(line_utm, line_ll, dem, step_m=60.0):
    """Walking time by Tobler's hiking function, which is slope-dependent.

    W = 6 exp(-3.5 |S + 0.05|) km/h, S the slope as a rise over run. On the flat
    that is 5.0 km/h; at a 20 per cent climb it is 2.3; at 20 per cent downhill
    3.9. A flat 4 km/h would understate the climbs badly on this terrain.
    """
    L = line_utm.length
    if L <= 0:
        return 0.0
    n = max(int(L // step_m), 2)
    fr = np.linspace(0, 1, n + 1)
    pu = [line_utm.interpolate(x, normalized=True) for x in fr]
    pl = [line_ll.interpolate(x, normalized=True) for x in fr]
    z = dem.z(np.array([p.x for p in pl]), np.array([p.y for p in pl]))
    d = np.hypot(np.diff([p.x for p in pu]), np.diff([p.y for p in pu]))
    d = np.maximum(d, 1e-6)
    s = np.diff(z) / d
    w = 6.0 * np.exp(-3.5 * np.abs(s + 0.05))          # km/h
    return float(np.sum((d / 1000.0) / np.maximum(w, 0.05)))


# --------------------------------------------------------------------------
# graph

def node_key(pt, ndp=1):
    return (round(pt[0], ndp), round(pt[1], ndp))


def bridge_gaps(G, max_gap_m=450.0):
    """Join separate components whose loose ends nearly touch.

    The gaps are in the recordings, not in the road: a GPS is switched off and
    on again, or two people recorded overlapping halves of the same route. Left
    unbridged they make the network into islands, and a real journey becomes
    unroutable - the Siribu spur came out as its own island, so the only village
    that could reach the Siribu stop was Siribu itself.

    Only ends are joined, only across different components, and only under the
    tolerance; the count and total length are reported so the amount of invented
    connection is visible rather than hidden.
    """
    from scipy.spatial import cKDTree
    ends = [n for n, d in G.degree() if d == 1]
    if not ends:
        return 0, 0.0
    arr = np.array(ends)
    tree = cKDTree(arr)
    comp = {}
    for ci, c in enumerate(nx.connected_components(G)):
        for n in c:
            comp[n] = ci
    n_bridge, total = 0, 0.0
    for i, a in enumerate(ends):
        for j in tree.query_ball_point(arr[i], max_gap_m):
            b = ends[j]
            if a == b or comp.get(a) == comp.get(b):
                continue
            d = float(np.hypot(arr[i][0] - arr[j][0], arr[i][1] - arr[j][1]))
            G.add_edge(a, b, weight=d, bridged=True)
            # merge the two components so the next pair is judged correctly
            ca, cb = comp[a], comp[b]
            for k, vcomp in comp.items():
                if vcomp == cb:
                    comp[k] = ca
            n_bridge += 1
            total += d
    return n_bridge, total


def build_graph(lines_utm):
    """Node the lines at their crossings and return a weighted graph."""
    merged = unary_union(lines_utm)          # splits every line at intersections
    parts = []
    if merged.geom_type == "LineString":
        parts = [merged]
    else:
        parts = [g for g in merged.geoms if g.geom_type == "LineString"]

    G = nx.Graph()
    for seg in parts:
        cs = list(seg.coords)
        for a, b in zip(cs[:-1], cs[1:]):
            ka, kb = node_key(a), node_key(b)
            if ka == kb:
                continue
            w = float(np.hypot(b[0] - a[0], b[1] - a[1]))
            if G.has_edge(ka, kb):
                if G[ka][kb]["weight"] <= w:
                    continue
            G.add_edge(ka, kb, weight=w)
    return G, parts


def snap(G, pt):
    """Nearest graph node to a point, and how far off-network that is."""
    nodes = np.array(list(G.nodes))
    d = np.hypot(nodes[:, 0] - pt.x, nodes[:, 1] - pt.y)
    i = int(np.argmin(d))
    return tuple(nodes[i]), float(d[i])


# --------------------------------------------------------------------------

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dem = Dem()

    tracks = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    roads = tracks[tracks["mode"] == "Motor road"].copy()
    foot = tracks[tracks["mode"] == "Foot track"].copy()

    # Road geometry supplied directly rather than derived from a recording. It
    # is kept in its own file and merged here so it never gets confused with
    # something the speed test established, and so its provenance travels with
    # it into the output.
    # Tracks someone has actually driven. The measurement had no timestamps for
    # these and fell back to the 1973 sheets, which got them wrong; a person who
    # has driven the route outranks that.
    confirmed = ROOT / "data" / "reference" / "confirmed_roads.csv"
    if confirmed.exists():
        cf = pd.read_csv(confirmed, comment="#")
        hit = tracks["name"].isin(cf["track_name"])
        if hit.any():
            reason = dict(zip(cf["track_name"], cf["reason"]))
            promoted = tracks[hit].copy()
            promoted["mode"] = "Motor road"
            promoted["mode_evidence"] = promoted["name"].map(
                lambda n: f"confirmed by field knowledge: {reason.get(n, '')}")
            print(f"  + {len(promoted)} track(s) confirmed driveable, "
                  f"{promoted['length_km'].sum():.2f} km:")
            for _, r in promoted.iterrows():
                print(f"      {r['name']}")
            roads = gpd.GeoDataFrame(pd.concat([roads, promoted], ignore_index=True),
                                     geometry="geometry", crs=roads.crs)
            foot = foot[~foot["name"].isin(cf["track_name"])]

    supplied = ROOT / "data" / "reference" / "supplied_roads.geojson"
    if supplied.exists():
        extra = gpd.read_file(supplied)
        print(f"  + {len(extra)} supplied road feature(s), "
              f"{extra['length_km'].sum():.2f} km")
        roads = gpd.GeoDataFrame(pd.concat([roads, extra], ignore_index=True),
                                 geometry="geometry", crs=roads.crs)
    print(f"{len(roads)} road features ({roads['length_km'].sum():.0f} km), "
          f"{len(foot)} foot ({foot['length_km'].sum():.0f} km)")

    # ---- deliverable 1: the road layer ------------------------------------
    keep = ["name", "mode", "mode_evidence", "speed_kmh_median",
            "speed_frac_over_12", "grad_p85_pct", "source_file", "format",
            "length_km", "geometry"]
    keep = [c for c in keep if c in roads.columns]
    out_roads = roads[keep].rename(columns={
        "name": "name", "source_file": "source_file",
        "grad_p85_pct": "gradient_p85_pct"})
    out_roads["source"] = "project GPS recording, " + out_roads["source_file"].astype(str)
    out_roads["surface"] = "unknown"       # not recorded in the source data
    out_roads["tracktype"] = "unknown"
    out_roads.to_file(OUT / "mca_roads.geojson", driver="GeoJSON")
    print(f"wrote {OUT/'mca_roads.geojson'}")

    roads_u = roads.to_crs(UTM)
    foot_u = foot.to_crs(UTM)
    G, parts = build_graph(list(roads_u.geometry))
    nb, tb = bridge_gaps(G)
    print(f"road graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges; "
          f"{nb} recording gap(s) bridged, {tb/1000:.2f} km total")

    # a graph of everything walkable, for the villages the road does not reach
    Gw, _ = build_graph(list(roads_u.geometry) + list(foot_u.geometry))
    nbw, tbw = bridge_gaps(Gw)
    print(f"walkable graph: {Gw.number_of_nodes()} nodes, {Gw.number_of_edges()} edges; "
          f"{nbw} gap(s) bridged, {tbw/1000:.2f} km")

    # ---- stops -------------------------------------------------------------
    v_for_stops = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")
    stops_def, stop_notes = reconcile_stops(v_for_stops)
    print("\nmarket stop positions:")
    for n in stop_notes:
        print(f"  ! {n}")
    stops = gpd.GeoDataFrame(
        [{"day": d, "stop": s, "zones": z,
          "geometry": Point(lon, lat)} for d, s, lat, lon, z in stops_def],
        crs=WGS84)
    stops_u = stops.to_crs(UTM)
    stop_nodes, stop_snap = [], []
    for p in stops_u.geometry:
        k, dd = snap(G, p)
        stop_nodes.append(k); stop_snap.append(dd)
    stops["snap_m"] = np.round(stop_snap, 1)
    print("\nmarket stops, distance from the road network:")
    for (_, r), dd in zip(stops.iterrows(), stop_snap):
        print(f"  {r['day']:<10} {r['stop']:<9} {dd:7.0f} m")

    overrides = load_overrides()
    track_only = {k for k, v in overrides.items()
                  if str(v.get("access", "")).strip().lower() == "track"}
    # --upgraded models the world in which the upgradeable stops have been
    # upgraded, so the cost of not doing it can be stated as a number.
    upgraded = "--upgraded" in sys.argv
    if upgraded:
        print("\n[UPGRADE SCENARIO] treating every upgradeable stop as road-served")
        track_only = set()
    if track_only:
        print("\nfield-knowledge overrides (track access only, not road):")
        for k in sorted(track_only):
            print(f"  ! {k}: {overrides[k]['note']}")
    stops["access"] = ["track" if r["stop"] in track_only else "road"
                       for _, r in stops.iterrows()]
    stops["upgradeable"] = [str(overrides[r["stop"]]["upgradeable"])
                            if r["stop"] in overrides else ""
                            for _, r in stops.iterrows()]

    # A stop a vehicle cannot reach cannot serve anybody by road, so it is taken
    # out of the road routing entirely. It stays a market: people still walk in,
    # and the walking figures below still use it.
    dist_from_stop = {}
    for (d, s, *_), k in zip(stops_def, stop_nodes):
        if s in track_only:
            continue
        dist_from_stop[s] = nx.single_source_dijkstra_path_length(G, k, weight="weight")

    # ---- villages ----------------------------------------------------------
    v = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")
    vg = gpd.GeoDataFrame(v, geometry=[Point(x, y) for x, y in zip(v.lon, v.lat)],
                          crs=WGS84)
    vu = vg.to_crs(UTM)

    # Villages someone on the ground says are reachable on foot only. This
    # outranks the snap test: proximity to a road line is not access to it, and
    # Natanga measured 1.70 km off the network - inside the 2 km cut, but the
    # 1.70 km is a walk.
    foot_only = {}
    fo_path = ROOT / "data" / "reference" / "footpath_only_villages.csv"
    if fo_path.exists():
        fo = pd.read_csv(fo_path, comment="#")
        foot_only = dict(zip(fo["village"], fo["reason"]))
        print("\nfield-knowledge overrides (footpath access only):")
        for k in sorted(foot_only):
            print(f"  ! {k}: {foot_only[k]}")

    rows = []
    for (_, vr), pu, pl in zip(vg.iterrows(), vu.geometry, vg.geometry):
        node, off = snap(G, pu)
        on_foot_only = vr["vil_name"] in foot_only
        reachable = (off <= SNAP_MAX_M) and not on_foot_only

        # road_km is distance ALONG THE ROAD, node to node. The walk from the
        # village to wherever it meets the road is reported separately as
        # offroad_to_road_m rather than folded in: folding it in made Kaura,
        # which is itself a market stop 1.4 km off the road, come out as 1.4 km
        # from itself.
        best_stop, best_km = None, np.inf
        if reachable:
            for s, dmap in dist_from_stop.items():
                if node in dmap:
                    km = dmap[node] / 1000.0
                    if km < best_km:
                        best_stop, best_km = s, km

        # straight line to that stop, or to the nearest stop if unreachable
        if best_stop is None:
            j = int(np.argmin([pu.distance(q) for q in stops_u.geometry]))
            nearest_name = stops.iloc[j]["stop"]
            straight_km = pu.distance(stops_u.geometry.iloc[j]) / 1000.0
        else:
            j = list(stops["stop"]).index(best_stop)
            nearest_name = best_stop
            straight_km = pu.distance(stops_u.geometry.iloc[j]) / 1000.0

        # walking time: over the walkable network if we can get there, else the
        # straight line, and say which
        wnode, woff = snap(Gw, pu)
        snode, soff = snap(Gw, stops_u.geometry.iloc[j])
        hours, wsrc = None, None
        if woff <= SNAP_MAX_M and soff <= SNAP_MAX_M:
            try:
                path = nx.shortest_path(Gw, wnode, snode, weight="weight")
                # a village that snaps to the stop's own node gives a one-point
                # path, which is not a line
                if len(path) < 2:
                    path = [path[0], path[0]] if path else []
                line_u = LineString(path) if len(path) >= 2 else None
                line_ll = (gpd.GeoSeries([line_u], crs=UTM).to_crs(WGS84).iloc[0]
                           if line_u else None)
                hours = tobler_hours(line_u, line_ll, dem) if line_u else 0.0
                # the off-network hops at each end, walked in a straight line
                ends = ((pu, Point(path[0])), (Point(path[-1]), stops_u.geometry.iloc[j])) if path else ()
                for a, b in ends:
                    if a.distance(b) > 1:
                        seg_u = LineString([a, b])
                        seg_ll = gpd.GeoSeries([seg_u], crs=UTM).to_crs(WGS84).iloc[0]
                        hours += tobler_hours(seg_u, seg_ll, dem)
                wsrc = "path network"
            except nx.NetworkXNoPath:
                hours = None
        if hours is None:
            seg_u = LineString([pu, stops_u.geometry.iloc[j]])
            seg_ll = gpd.GeoSeries([seg_u], crs=UTM).to_crs(WGS84).iloc[0]
            hours = tobler_hours(seg_u, seg_ll, dem)
            wsrc = "straight line (no connected path)"

        rows.append({
            "village": vr["vil_name"], "zone": vr["zone"], "ward": vr["wards"],
            "households": vr["est_hh"], "lat": vr["lat"], "lon": vr["lon"],
            "alt": round(vr["alt"], 1),
            "nearest_stop": nearest_name,
            "road_km": round(best_km, 2) if best_stop else "",
            "straight_km": round(straight_km, 2),
            "walk_hours_est": round(hours, 2),
            "road_reachable": "yes" if best_stop else "no",
            "road_access_basis": ("field knowledge: footpath only" if on_foot_only
                                  else "measured: within 2 km of the network"
                                  if best_stop else
                                  "measured: beyond 2 km of the network"),
            "offroad_to_road_m": round(off),
            "walk_basis": wsrc,
            "stop_access": ("track only" if nearest_name in track_only else "road"),
            "position_spread_km": round(vr["spread_km"], 2),
        })

    acc = pd.DataFrame(rows)
    name = "mca_village_access_upgraded.csv" if upgraded else "mca_village_access.csv"
    acc.to_csv(OUT / name, index=False)
    print(f"\nwrote {OUT/name}")

    served = acc[acc.road_reachable == "yes"]
    tot = acc["households"].sum()
    print(f"{len(served)} of {len(acc)} villages reachable by road; "
          f"{served['households'].sum()} of {tot} households "
          f"({served['households'].sum()/tot*100:.1f}%)")
    for band in (2, 5, 10):
        m = served[pd.to_numeric(served["road_km"], errors="coerce") <= band]
        print(f"    within {band:2d} km by road: {m['households'].sum():5d} "
              f"({m['households'].sum()/tot*100:.1f}%)")

    # ---- service areas -----------------------------------------------------
    polys = []
    for (d, s, lat, lon, z), k in zip(stops_def, stop_nodes):
        if s not in dist_from_stop:
            continue
        dmap = dist_from_stop[s]
        for band in SERVICE_BANDS_KM:
            segs = []
            for seg in parts:
                cs = list(seg.coords)
                inside = [c for c in cs if dmap.get(node_key(c), np.inf) <= band * 1000]
                if len(inside) >= 2:
                    segs.append(LineString(inside))
            if not segs:
                continue
            # A corridor 1 km wide, centred on the road. This is a drawing
            # width chosen so the bands can be read on a 55 km-wide map, not a
            # claim that everywhere within 500 m of the road is served; at the
            # 300 m first used the bands were invisible under the road line.
            poly = unary_union([s_.buffer(500) for s_ in segs])
            polys.append({"day": d, "stop": s, "zones": z, "band_km": band,
                          "geometry": poly})
    sa = gpd.GeoDataFrame(polys, crs=UTM).to_crs(WGS84)
    sa_name = ("mca_service_areas_upgraded.geojson" if upgraded
               else "mca_service_areas.geojson")
    sa.to_file(OUT / sa_name, driver="GeoJSON")
    print(f"wrote {OUT/sa_name}  ({len(sa)} polygons)")

    # The upgrade run is a what-if. It must not overwrite the delivered stops or
    # the method record - doing so once left method.json claiming no stop was
    # track-only, which is the opposite of what the delivered figures show.
    if not upgraded:
        stops.to_file(OUT / "mca_market_stops.geojson", driver="GeoJSON")
        meta = {"crs_analysis": UTM, "crs_output": WGS84, "dem": dem.name,
                "track_only_stops": sorted(track_only),
                "walking_model": "Tobler hiking function",
                "snap_max_m": SNAP_MAX_M,
                "service_bands_km": list(SERVICE_BANDS_KM),
                "osm_available": False}
        (OUT / "method.json").write_text(json.dumps(meta, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
