"""Cross-reference the team's planned track list against what has been recorded.

outputs/access/track_checklist.csv   one row per leg, with the measurements
outputs/access/TRACK_CHECKLIST.md    the checklist to hand to the team

The question is not whether a recording carries a matching name - names are
unreliable here, and most of the Russell Muraba segments carry no name at all.
It is whether the recorded network actually joins the two places. So each leg of
each planned route is tested geometrically:

  1. both ends must sit within ENDPOINT_M of a recorded line, and
  2. a route must exist between them over the noded network, no longer than
     DETOUR_MAX times the straight line.

Test 2 is what stops a leg being called done because both its ends happen to lie
on the network at opposite ends of the plateau. Test 1 is what stops a leg being
called done because some unrelated line passes the midpoint.

A leg whose places we cannot position is reported as unlocated, not as missing:
the two are different problems and only one of them is solved by walking.
"""

import re
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_access import bridge_gaps, build_graph, snap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
OUT = ROOT / "outputs" / "access"

WGS84 = "EPSG:4326"
UTM = "EPSG:32755"

# A village position is a cluster centroid or a gazetteer point, not a doorstep;
# the gazetteer's own spread_km runs to 2.3 km for the larger villages. 500 m is
# tight enough that an unrelated line nearby will not satisfy it, and the
# measured distance is reported either way so the call can be checked.
ENDPOINT_M = 500.0
# Two villages 3 km apart joined only by a 9 km recorded route are not joined by
# the track the list is asking for.
DETOUR_MAX = 1.8
# Over a short leg the terrain detour is proportionally much larger: 2 km of
# straight line between two hamlets either side of a gully is routinely a 4 km
# walk, and that walk is the track, not a detour around a missing one.
SHORT_LEG_M = 2500.0
DETOUR_MAX_SHORT = 2.5
# Some legs in the list are historic long-distance routes off the plateau, not a
# morning's work - Jaura to Kwikila is 75 km into Central Province. Flagged so
# nobody is sent out to walk one between breakfast and the afternoon rain.
LONG_LEG_KM = 25.0


def load_placed():
    """Positions the team placed by hand. These win outright, not on a tie.

    Someone who has walked the ground outranks a gazetteer and outranks our
    inference, so a name found here returns that one position and no others -
    there is nothing for the leg to choose between.
    """
    path = REF / "placed_by_team.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#")
    return {str(r["place"]).strip().lower():
            dict(name=str(r["place"]).strip(), lon=float(r["lon"]),
                 lat=float(r["lat"]), src="placed by the team",
                 note=str(r.get("note", "")))
            for _, r in df.iterrows()
            if not (pd.isna(r["lon"]) or pd.isna(r["lat"]))}


def load_places():
    """Name -> list of candidate positions, gazetteer first then GPS-inferred.

    A name can have several positions and often does: the gazetteer and the GPS
    inference disagree by a kilometre or two in places, and some names are simply
    reused - there are two Kauras, two Kuharas, two Sigaras and two Siribus in
    the recordings, kilometres apart. Keeping every candidate and letting each
    leg pick is better than picking here and being wrong half the time.
    """
    places = {}
    bad = set()
    bp = REF / "bad_positions.csv"
    if bp.exists():
        for _, r in pd.read_csv(bp, comment="#").iterrows():
            bad.add((str(r["source"]).strip(), str(r["name"]).strip().lower()))

    def add(nm, src=None, **kw):
        if (src, nm.strip().lower()) in bad:
            return
        places.setdefault(nm.strip(), []).append(dict(src=src, **kw))

    gaz = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")
    for _, r in gaz.iterrows():
        nm = str(r["vil_name"]).strip()
        rec = dict(lon=float(r["lon"]), lat=float(r["lat"]), src="gazetteer",
                   note=f"zone {r['zone']}, {int(r['est_hh'])} hh")
        add(nm, **rec)
        # "Sila/Sakarina" is one row standing for two names; answer to either.
        if "/" in nm:
            for half in nm.split("/"):
                add(half, **rec)

    inf = gpd.read_file(PROCESSED / "villages.gpkg")
    inf = inf[~inf["village"].str.startswith("unnamed")]
    for _, r in inf.sort_values("confidence", ascending=False).iterrows():
        add(str(r["village"]), lon=float(r.geometry.x), lat=float(r.geometry.y),
            src="GPS-inferred", note=f"confidence {r['confidence']}")
    return places


def load_aliases():
    """Written spelling -> canonical name, position override, and any note.

    A row with resolved_to blank locates nothing; it carries a note about a
    candidate we are not willing to assume, which the checklist repeats back so
    the team can confirm or reject it.
    """
    a = pd.read_csv(REF / "place_aliases.csv", comment="#")
    out = {}
    for _, r in a.iterrows():
        out[str(r["as_written"]).strip().lower()] = dict(
            to="" if pd.isna(r["resolved_to"]) else str(r["resolved_to"]).strip(),
            lon=None if pd.isna(r["lon"]) else float(r["lon"]),
            lat=None if pd.isna(r["lat"]) else float(r["lat"]),
            note="" if pd.isna(r.get("note")) else str(r["note"]))
    return out


PLACED = None          # filled on first use; the team's placements win outright


def candidates(name, places, aliases):
    """Written place name -> every position it could be, or [] if none."""
    global PLACED
    if PLACED is None:
        PLACED = load_placed()
    raw = name.strip()
    hit = PLACED.get(raw.lower())
    if hit:
        return [dict(hit)]
    al = aliases.get(raw.lower())
    if al:
        if al["lon"] is not None:
            return [dict(name=al["to"], lon=al["lon"], lat=al["lat"],
                         src="field evidence", note=al["note"])]
        if al["to"]:
            raw = al["to"]
            hit = PLACED.get(raw.lower())
            if hit:
                return [dict(hit)]
    for pn, cands in places.items():
        if pn.lower() == raw.lower():
            return [dict(name=pn, **c) for c in cands]
    return []


def spread_km(cands):
    """How far apart the candidate positions for one name are, in km."""
    if len(cands) < 2:
        return 0.0
    xs = np.array([[c["lon"], c["lat"]] for c in cands])
    lat = float(np.mean(xs[:, 1]))
    m = np.column_stack([xs[:, 0] * 110_000 * np.cos(np.radians(lat)),
                         xs[:, 1] * 110_000])
    return float(np.max(np.hypot(*(m[:, None, :] - m[None, :, :]).T))) / 1000


TIER = {"placed by the team": 0, "field evidence": 0, "gazetteer": 1}


def best_tier(cands):
    """Keep only the best-sourced candidates for a name.

    Source outranks distance. The team's own placements come first, then the
    surveyed gazetteer, then our GPS inference - and the inference is known to
    contain errors the team has pointed out: Ondoro and Vouka placed where there
    is no village, and a "Sigara" that is probably where a road named for Sigara
    ends rather than the village. Letting the nearest candidate win regardless
    of source picked the northern Kaura over the surveyed one for "Kaura-Sigara"
    on a 0.3 km margin, which is not a judgement distance can make.
    """
    if not cands:
        return cands
    rank = min(TIER.get(c.get("src", ""), 2) for c in cands)
    return [c for c in cands if TIER.get(c.get("src", ""), 2) == rank]


def pick_pair(ca, cb):
    """Of the candidate positions for each end, the pair that is one track.

    Within the best-sourced candidates, where a name is still on more than one
    place the leg itself settles which is meant: the list is naming a walk
    between two places, so the closest pairing is the one it is about.
    """
    ca, cb = best_tier(ca), best_tier(cb)
    best, bestkey = None, None
    for a in ca:
        for b in cb:
            d = float(np.hypot((a["lon"] - b["lon"]) * 110_000 *
                               np.cos(np.radians(a["lat"])),
                               (a["lat"] - b["lat"]) * 110_000))
            key = (d,)
            if bestkey is None or key < bestkey:
                best, bestkey = (a, b), key
    return best


def road_at_place(pr, place, places, aliases, road_net):
    """Is a recorded motorable road at this place? The test for a named road."""
    rec = dict(route_id=pr["id"], leg=f"{pr['id']}.1", category=pr["category"],
               as_written=pr["as_written"], from_place=place,
               to_place="(the road itself)", from_resolved="", to_resolved="",
               name_evidence="", ambiguous_name="", multi_day="")
    cands = candidates(place, places, aliases)
    if not cands:
        rec["status"] = "unlocated"
        rec["detail"] = f"no position for {place}"
        return rec
    c = cands[0]
    rec["from_resolved"] = c["name"]
    p = (gpd.GeoSeries([Point(c["lon"], c["lat"])], crs=WGS84)
         .to_crs(UTM).iloc[0])
    off = float(road_net.distance(p)) if not road_net.is_empty else float("inf")
    rec["from_off_network_m"] = round(off)
    if off <= ENDPOINT_M:
        rec["status"] = "recorded"
        rec["detail"] = (f"a recorded motorable road runs within {off:.0f} m of "
                         f"{c['name']}")
    else:
        rec["status"] = "missing"
        rec["detail"] = (f"no recorded motorable road within {off/1000:.1f} km of "
                         f"{c['name']} - the road itself is not recorded")
    return rec


def main():
    planned = pd.read_csv(REF / "planned_tracks.csv", comment="#")
    places = load_places()
    aliases = load_aliases()

    tracks = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    tr_u = tracks.to_crs(UTM)
    lines = list(tr_u.geometry)
    net = unary_union(lines)

    G, _ = build_graph(lines)
    n_br, len_br = bridge_gaps(G, 450.0)
    print(f"network: {len(tracks)} recordings, {tr_u.length.sum()/1000:.0f} km, "
          f"{n_br} gaps bridged ({len_br/1000:.1f} km)")

    # The highway is a place in this list ("Highway-Bioi"). Resolve it per-leg as
    # the nearest point on the recorded motorable network to the other end.
    roads_u = tr_u[tr_u["type"].astype(str).str.contains("Road", na=False)]
    road_net = unary_union(list(roads_u.geometry))

    # Name evidence, as corroboration only - never as a substitute for the
    # geometry. Tokens of 4+ letters so "Dea" does not match "Dareki".
    hay = (tracks["name"].fillna("") + " | " + tracks["source_name"].fillna("")
           + " | " + tracks["source_file"].fillna("")).str.lower().tolist()

    def named_for(a, b):
        ta, tb = a.lower()[:5], b.lower()[:5]
        if len(ta) < 4 or len(tb) < 4:
            return ""
        hits = [tracks["name"].iloc[i] for i, h in enumerate(hay)
                if ta in h and tb in h]
        return hits[0] if hits else ""

    rows = []
    for _, pr in planned.iterrows():
        chain = [c.strip() for c in str(pr["chain"]).split(">")]

        # A chain of one place is a named road rather than a journey between two
        # points: "Road 3 is the road to get there". The question is whether a
        # recorded motorable road reaches the place it serves.
        if len(chain) == 1:
            rows.append(road_at_place(pr, chain[0], places, aliases, road_net))
            continue

        for i, (a_w, b_w) in enumerate(zip(chain[:-1], chain[1:]), start=1):
            leg = f"{pr['id']}.{i}"
            rec = dict(route_id=pr["id"], leg=leg, category=pr["category"],
                       as_written=pr["as_written"], from_place=a_w, to_place=b_w)

            ca = candidates(a_w, places, aliases)
            cb = candidates(b_w, places, aliases)
            a = b = None
            if ca and cb:
                a, b = pick_pair(ca, cb)
            elif ca:
                a = ca[0]
            elif cb:
                b = cb[0]
            # Flag a name only where its candidate positions are genuinely far
            # apart. The gazetteer and the GPS inference routinely differ by a
            # few hundred metres on the same village, which settles nothing and
            # is not worth warning about; two Kauras 10 km apart is.
            n_amb = max(spread_km(best_tier(ca)), spread_km(best_tier(cb)))

            # "Highway" / "Road 1/2/3" are the trunk and the numbered feeder
            # stubs; the highway we can test against the recorded roads, the
            # numbered roads we cannot place without being told where they are.
            for side, nm, other in (("a", a_w, b), ("b", b_w, a)):
                if nm.strip().lower() == "highway" and other is not None and not road_net.is_empty:
                    p = gpd.GeoSeries([Point(other["lon"], other["lat"])],
                                      crs=WGS84).to_crs(UTM).iloc[0]
                    from shapely.ops import nearest_points
                    np_pt = nearest_points(road_net, p)[0]
                    ll = gpd.GeoSeries([np_pt], crs=UTM).to_crs(WGS84).iloc[0]
                    filled = dict(name="nearest recorded road", lon=ll.x, lat=ll.y,
                                  src="recorded road network", note="")
                    if side == "a":
                        a = filled
                    else:
                        b = filled

            rec["from_resolved"] = a["name"] if a else ""
            rec["to_resolved"] = b["name"] if b else ""
            rec["name_evidence"] = named_for(a_w, b_w)

            rec["ambiguous_name"] = f"{n_amb:.1f} km apart" if n_amb > 2.0 else ""

            if a is None or b is None:
                rec["status"] = "unlocated"
                missing = [w for w, c in ((a_w, ca), (b_w, cb)) if not c]
                rec["detail"] = "no position for " + " and ".join(missing)
                rows.append(rec)
                continue

            pa, pb = (gpd.GeoSeries([Point(a["lon"], a["lat"]),
                                     Point(b["lon"], b["lat"])], crs=WGS84)
                      .to_crs(UTM))
            straight = pa.distance(pb)
            off_a, off_b = net.distance(pa), net.distance(pb)
            rec["straight_km"] = round(straight / 1000, 2)
            rec["multi_day"] = "yes" if straight / 1000 >= LONG_LEG_KM else ""
            rec["from_off_network_m"] = round(off_a)
            rec["to_off_network_m"] = round(off_b)

            ka, da = snap(G, pa)
            kb, db = snap(G, pb)
            route_km, ratio = np.nan, np.nan
            if nx.has_path(G, ka, kb):
                route = nx.shortest_path_length(G, ka, kb, weight="weight")
                route_km = (route + da + db) / 1000
                ratio = route_km * 1000 / max(straight, 1.0)
            rec["route_km"] = None if np.isnan(route_km) else round(route_km, 2)
            rec["detour_ratio"] = None if np.isnan(ratio) else round(ratio, 2)

            limit = DETOUR_MAX_SHORT if straight <= SHORT_LEG_M else DETOUR_MAX
            ends_ok = off_a <= ENDPOINT_M and off_b <= ENDPOINT_M

            # Some pairs of names are one place in our data - the gazetteer
            # carries Sila/Sakarina as a single settlement, and Suari and Jaure
            # 70 m apart. There is no leg to walk; whether it is recorded is
            # just whether that one place is.
            if straight < 200.0:
                rec["status"] = "recorded" if ends_ok else "missing"
                rec["detail"] = (f"{a['name']} and {b['name']} are the same point in "
                                 f"our data ({straight:.0f} m apart), so there is no "
                                 f"leg here - "
                                 + ("that place is recorded" if ends_ok else
                                    f"and that place is {max(off_a, off_b)/1000:.1f} km "
                                    f"off anything recorded"))
            elif ends_ok and np.isnan(ratio):
                # Both ends have recordings and nothing joins them: the network
                # is in two pieces here, which is the gap the list is naming.
                rec["status"] = "missing"
                rec["detail"] = ("both ends have recordings but nothing recorded joins "
                                 "them - the connecting track is the gap")
            elif ends_ok and ratio <= limit:
                rec["status"] = "recorded"
                rec["detail"] = f"routes in {route_km:.1f} km vs {straight/1000:.1f} km straight"
            elif ends_ok:
                rec["status"] = "partial"
                rec["detail"] = (f"both ends on the network but only linked the long "
                                 f"way round ({route_km:.1f} km for {straight/1000:.1f} km "
                                 f"straight) - the direct track is not recorded")
            elif off_a <= ENDPOINT_M or off_b <= ENDPOINT_M:
                near = a["name"] if off_a <= ENDPOINT_M else b["name"]
                far = b["name"] if off_a <= ENDPOINT_M else a["name"]
                rec["status"] = "partial"
                rec["detail"] = (f"{near} end is on the network, {far} is "
                                 f"{max(off_a, off_b)/1000:.1f} km off it")
            else:
                rec["status"] = "missing"
                rec["detail"] = (f"neither end on the network "
                                 f"({off_a/1000:.1f} km and {off_b/1000:.1f} km off)")
            rows.append(rec)

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["route_id", "leg", "category", "as_written", "from_place", "to_place",
            "from_resolved", "to_resolved", "status", "detail", "straight_km",
            "route_km", "detour_ratio", "from_off_network_m", "to_off_network_m",
            "ambiguous_name", "multi_day", "name_evidence"]
    df[cols].to_csv(OUT / "track_checklist.csv", index=False)

    # Route-level roll-up: a route is only done when every leg of it is.
    order = {"missing": 0, "unlocated": 1, "partial": 2, "recorded": 3}
    route = (df.assign(rank=df["status"].map(order))
               .groupby("route_id")
               .agg(category=("category", "first"),
                    as_written=("as_written", "first"),
                    legs=("leg", "count"),
                    worst=("rank", "min"),
                    done=("status", lambda s: (s == "recorded").sum())))
    inv = {v: k for k, v in order.items()}
    route["status"] = route["worst"].map(inv)

    # A route can be a multi-day walk without any single leg of it measuring
    # long, because the middle of it is unlocated: Jaura-Vovosik-Kwikila has no
    # measurable leg and is still 75 km end to end. Measure the ends.
    span = {}
    for _, pr in planned.iterrows():
        chain = [c.strip() for c in str(pr["chain"]).split(">")]
        ca = candidates(chain[0], places, aliases)
        cb = candidates(chain[-1], places, aliases)
        if ca and cb:
            a, b = pick_pair(ca, cb)
            pa, pb = (gpd.GeoSeries([Point(a["lon"], a["lat"]),
                                     Point(b["lon"], b["lat"])], crs=WGS84)
                      .to_crs(UTM))
            span[pr["id"]] = float(pa.distance(pb)) / 1000
    route["span_km"] = route.index.map(lambda i: span.get(i, float("nan")))
    route["multi_day"] = route["span_km"] >= LONG_LEG_KM

    print()
    print(df["status"].value_counts().to_string())
    print()
    print("routes by status:")
    print(route["status"].value_counts().to_string())

    write_markdown(df, route, aliases)
    print(f"\nwrote {OUT/'track_checklist.csv'} and {OUT/'TRACK_CHECKLIST.md'}")
    return 0


def write_markdown(df, route, aliases):
    mark = {"recorded": "[x]", "partial": "[~]", "missing": "[ ]", "unlocated": "[?]"}
    L = []
    L.append("# Track recording checklist - Managalas Conservation Area")
    L.append("")
    L.append("Generated by `scripts/cross_reference_tracks.py` from the team's list in")
    L.append("`data/reference/planned_tracks.csv` against the GPS recordings held in")
    L.append("`data/processed/tracks.gpkg`. Re-run it after each new drop of recordings.")
    L.append("")
    L.append("A leg counts as recorded only when both its ends sit within 500 m of a")
    L.append("recorded line **and** the recorded network routes between them without a")
    L.append("long detour. Matching names were not enough to pass a leg: most of the")
    L.append("recordings in hand carry no route name at all.")
    L.append("")
    L.append("| | meaning | what to do |")
    L.append("|---|---|---|")
    L.append("| `[x]` | recorded | nothing |")
    L.append("| `[~]` | partly recorded | walk the part that is missing |")
    L.append("| `[ ]` | not recorded | walk it |")
    L.append("| `[?]` | place not located | tell us roughly where it is, then walk it |")
    L.append("")
    n = len(df)
    for st in ("recorded", "partial", "missing", "unlocated"):
        c = int((df["status"] == st).sum())
        L.append(f"- {mark[st]} **{c}** of {n} legs {st}")
    L.append("")

    for cat, title in (("foot", "Foot tracks"),
                       ("feeder road", "Feeder roads (member's roads)"),
                       ("national highway", "National highways")):
        sub = route[route["category"] == cat]
        if sub.empty:
            continue
        L.append(f"## {title}")
        L.append("")
        for st in ("missing", "unlocated", "partial", "recorded"):
            rs = sub[sub["status"] == st]
            if rs.empty:
                continue
            heading = {"missing": "Not recorded - these are the gap",
                       "unlocated": "Cannot be checked until the place is located",
                       "partial": "Partly recorded",
                       "recorded": "Recorded"}[st]
            L.append(f"### {heading} ({len(rs)})")
            L.append("")
            for rid, r in rs.iterrows():
                tag = (f" — **{r['span_km']:.0f} km end to end: a multi-day walk**"
                       if r.get("multi_day") else "")
                L.append(f"- {mark[st]} **{r['as_written']}**  `{rid}`{tag}")
                legs = df[df["route_id"] == rid]
                if len(legs) > 1 or st != "recorded":
                    for _, lg in legs.iterrows():
                        extra = ""
                        if isinstance(lg.get("name_evidence"), str) and lg["name_evidence"]:
                            extra += f" — a recording is named for it: *{lg['name_evidence']}*"
                        amb = lg.get("ambiguous_name")
                        if lg.get("multi_day") == "yes":
                            extra += (f" — **{lg['straight_km']:.0f} km in a straight "
                                      f"line: a multi-day walk, not a day trip**")
                        if isinstance(amb, str) and amb:
                            extra += (f" — **this name is on two places {amb}; the "
                                      f"nearer pairing was assumed**")
                        L.append(f"  - {mark[lg['status']]} {lg['from_place']} → "
                                 f"{lg['to_place']}: {lg['detail']}{extra}")
            L.append("")
    # One list of the names we cannot place. Until these are positioned we
    # cannot say whether their tracks are recorded, so this is the first ask.
    unl = {}
    for _, r in df[df["status"] == "unlocated"].iterrows():
        for w in str(r["detail"]).replace("no position for ", "").split(" and "):
            unl.setdefault(w.strip(), []).append(r["route_id"])
    L.append("## Places we hold no position for")
    L.append("")
    L.append(f"These {len(unl)} names appear in the list and in nothing we hold - not the")
    L.append("village gazetteer, not the GPS recordings. A rough latitude/longitude, or")
    L.append("even \"two hours' walk east of X\", is enough to put each route on the map")
    L.append("and say whether it still needs walking.")
    L.append("")
    L.append("| place | appears in | note |")
    L.append("|---|---|---|")
    for nm in sorted(unl):
        note = (aliases.get(nm.lower(), {}) or {}).get("note", "")
        ids = ", ".join(sorted(set(unl[nm])))
        L.append(f"| {nm} | {ids} | {note} |")
    L.append("")
    (OUT / "TRACK_CHECKLIST.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
