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
    print(f"road graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # a graph of everything walkable, for the villages the road does not reach
    Gw, _ = build_graph(list(roads_u.geometry) + list(foot_u.geometry))
    print(f"walkable graph: {Gw.number_of_nodes()} nodes, {Gw.number_of_edges()} edges")

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

    dist_from_stop = {}
    for (d, s, *_), k in zip(stops_def, stop_nodes):
        dist_from_stop[s] = nx.single_source_dijkstra_path_length(G, k, weight="weight")

    # ---- villages ----------------------------------------------------------
    v = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")
    vg = gpd.GeoDataFrame(v, geometry=[Point(x, y) for x, y in zip(v.lon, v.lat)],
                          crs=WGS84)
    vu = vg.to_crs(UTM)

    rows = []
    for (_, vr), pu, pl in zip(vg.iterrows(), vu.geometry, vg.geometry):
        node, off = snap(G, pu)
        reachable = off <= SNAP_MAX_M

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
            "offroad_to_road_m": round(off),
            "walk_basis": wsrc,
            "position_spread_km": round(vr["spread_km"], 2),
        })

    acc = pd.DataFrame(rows)
    acc.to_csv(OUT / "mca_village_access.csv", index=False)
    print(f"\nwrote {OUT/'mca_village_access.csv'}")

    served = acc[acc.road_reachable == "yes"]
    print(f"{len(served)} of {len(acc)} villages reachable by road; "
          f"{served['households'].sum()} of {acc['households'].sum()} households "
          f"({served['households'].sum()/acc['households'].sum()*100:.1f}%)")

    # ---- service areas -----------------------------------------------------
    polys = []
    for (d, s, lat, lon, z), k in zip(stops_def, stop_nodes):
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
    sa.to_file(OUT / "mca_service_areas.geojson", driver="GeoJSON")
    print(f"wrote {OUT/'mca_service_areas.geojson'}  ({len(sa)} polygons)")

    meta = {"crs_analysis": UTM, "crs_output": WGS84, "dem": dem.name,
            "walking_model": "Tobler hiking function",
            "snap_max_m": SNAP_MAX_M, "service_bands_km": list(SERVICE_BANDS_KM),
            "osm_available": False}
    (OUT / "method.json").write_text(json.dumps(meta, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
