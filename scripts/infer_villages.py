"""Infer village locations from where tracks start and finish.

Nobody surveyed the villages directly, but the tracks encode them: a recording
called "Kaura to Sigara Village" almost certainly begins at Kaura and ends at
Sigara, and several independent tracks touching the same spot agree on what it
is called. So:

  1. take the first and last point of every track
  2. cluster endpoints that sit within CLUSTER_RADIUS_M of one another
  3. propose a name for each endpoint from its track's name (first place named
     goes with the start, last with the end)
  4. within each cluster, take the majority proposal

Confidence is the share of endpoints in a cluster that agree, and how many
distinct tracks vouch for it. A place named by one track is a guess; one named
by four is close to certain. Everything is written out with its evidence so the
weak ones are visible rather than buried.

Output: data/processed/villages.gpkg (layer "villages") and villages.csv
"""

import re
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

WGS84 = "EPSG:4326"
UTM55S = "EPSG:32755"

# Endpoints closer than this are treated as the same place. Kept fairly tight
# because union-find is single-linkage and will chain along a corridor: at 500 m
# it merged Sakarina, Kaura and Kuhara into one blob.
CLUSTER_RADIUS_M = 300

# Two clusters that independently resolve to the same name and sit within this
# distance are the same village, approached from different directions. Tracks
# rarely stop at exactly the same spot in a settlement.
MERGE_SAME_NAME_M = 3000

# Words that are never a place name.
STOPWORDS = {
    "track", "tracks", "recording", "record", "records", "survey", "surveys",
    "cropping", "calendar", "calander", "zone", "six", "main", "road", "roads",
    "the", "and", "then", "back", "via", "from", "to", "of", "village",
    "villages", "primary", "school", "guest", "house", "water", "source",
    "grid", "connect", "connects", "davids", "david", "jajibas", "jajiba",
    "seg", "trek", "new", "guinea", "papua", "seg1", "part", "seq",
    # Descriptors that attach to a place name rather than being one. Without
    # these the parser invents places called "Short", "End" and "Alternate"
    # out of names like "Short cut to Siribu village".
    "junction", "river", "creek", "school", "community", "station", "hamlet",
    "trail", "short", "cut", "end", "alternate", "feeder", "leading", "bush",
    "shortcut", "high", "highschool", "camp", "bridge", "crossing",
}


def place_tokens(name):
    """Ordered place-name candidates pulled out of a track name."""
    # Drop possessives and punctuation that is not a separator.
    text = re.sub(r"'s\b", "", name)
    text = re.sub(r"[^\w\s\-–,]", " ", text)
    # Treat separators as boundaries between places.
    parts = re.split(r"\s+to\s+|\s+then\s+|\s*[,–]\s*|\s+and\s+|\s*-\s*", text, flags=re.I)

    places = []
    for part in parts:
        words = [w for w in re.findall(r"[A-Za-z]+\d*", part) if w.lower() not in STOPWORDS]
        # Keep capitalised words: place names are capitalised in these files.
        words = [w for w in words if w[:1].isupper()]
        if words:
            candidate = " ".join(words)
            if candidate not in places:
                places.append(candidate)
    return places


def endpoints(tracks):
    """First and last vertex of each track, with a proposed name for each."""
    rows = []
    for _, track in tracks.iterrows():
        geom = track.geometry
        parts = list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
        coords = [c for p in parts for c in p.coords]
        if len(coords) < 2:
            continue

        places = place_tokens(track["name"])
        first_name = places[0] if places else None
        last_name = places[-1] if len(places) > 1 else None

        for end, place, coord in (
            ("start", first_name, coords[0]),
            ("finish", last_name, coords[-1]),
        ):
            rows.append(
                {
                    "track": track["name"],
                    "source_file": track.get("source_file"),
                    "type": track.get("type"),
                    "end": end,
                    "proposed": place,
                    "geometry": Point(coord[0], coord[1]),
                }
            )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)


def cluster(points_utm, radius):
    """Union-find clustering on a straight distance threshold."""
    n = len(points_utm)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    coords = [(p.x, p.y) for p in points_utm]
    for i in range(n):
        xi, yi = coords[i]
        for j in range(i + 1, n):
            xj, yj = coords[j]
            if (xi - xj) ** 2 + (yi - yj) ** 2 <= radius**2:
                union(i, j)

    return [find(i) for i in range(n)]


def merge_same_name(villages):
    """Fold clusters that resolved to the same name and sit close together.

    Tracks arriving at a village from different directions stop at different
    edges of it, which leaves one settlement split across several clusters —
    "Kaura" came out five times before this pass.
    """
    if villages.empty:
        return villages

    utm = villages.to_crs(UTM55S)
    villages = villages.copy()
    villages["_x"] = utm.geometry.x
    villages["_y"] = utm.geometry.y

    merged, used = [], set()
    for i, row in villages.iterrows():
        if i in used or not row["named"]:
            continue
        group = [i]
        for j, other in villages.iterrows():
            if j <= i or j in used or other["village"] != row["village"]:
                continue
            dist = ((row["_x"] - other["_x"]) ** 2 + (row["_y"] - other["_y"]) ** 2) ** 0.5
            if dist <= MERGE_SAME_NAME_M:
                group.append(j)
        used.update(group)

        block = villages.loc[group]
        centre = gpd.GeoSeries(block.geometry.values, crs=WGS84).union_all().centroid
        merged.append(
            {
                "village": row["village"],
                "named": True,
                "endpoints": int(block["endpoints"].sum()),
                "tracks": int(block["tracks"].sum()),
                "agreeing": int(block["agreeing"].sum()),
                "confidence": round(float(block["confidence"].mean()), 2),
                "clusters_merged": len(group),
                "alternatives": "; ".join(a for a in block["alternatives"] if a),
                "evidence": " | ".join(block["evidence"])[:400],
                "geometry": centre,
            }
        )

    for i, row in villages.iterrows():
        if i not in used:
            record = row.drop(labels=["_x", "_y"]).to_dict()
            record["clusters_merged"] = 1
            merged.append(record)

    return gpd.GeoDataFrame(merged, geometry="geometry", crs=WGS84)


def resolve_conflicts(villages):
    """Where one name lands in two distant places, keep the better-evidenced.

    The naming heuristic assumes a track called "A to B" was walked from A to
    B. When it was actually walked B to A the two names swap, which put Anatua
    both in the south-west (four tracks agreeing) and 45 km north (one track).
    Direction is not recoverable from the file, so settle it by evidence: the
    cluster with more independent tracks keeps the name, the loser is marked
    disputed and goes unlabelled rather than asserting a wrong location.
    """
    villages = villages.copy()
    villages["disputed"] = False

    for name, grp in villages[villages["named"]].groupby("village"):
        if len(grp) < 2:
            continue
        ranked = grp.sort_values(["tracks", "agreeing", "confidence"], ascending=False)
        winner = ranked.index[0]
        losers = list(ranked.index[1:])
        villages.loc[losers, "disputed"] = True
        villages.loc[losers, "named"] = False
        print(
            f"  conflict: {name!r} in {len(grp)} places — keeping the one backed by "
            f"{int(ranked.iloc[0]['tracks'])} track(s), disputing {len(losers)}"
        )

    return villages


def apply_name_overrides(villages):
    """Correct inferred names from data/village_names.csv.

    Inference cannot recover which direction a track was walked, so some names
    land on the wrong end. Ground truth beats the heuristic: this file wins.

    Columns: lon, lat, village  — the nearest inferred cluster to each
    coordinate takes that name. Add `drop` = yes to remove a bogus cluster.
    """
    path = ROOT / "data" / "village_names.csv"
    if not path.exists():
        return villages

    overrides = pd.read_csv(path, comment="#")
    required = {"lon", "lat", "village"}
    if not required <= set(overrides.columns):
        print(f"  !! {path.name} needs columns {sorted(required)}; ignoring")
        return villages

    utm = villages.to_crs(UTM55S)
    pts = gpd.GeoSeries(
        [Point(r["lon"], r["lat"]) for _, r in overrides.iterrows()], crs=WGS84
    ).to_crs(UTM55S)

    villages = villages.copy()
    drop_idx = []
    for i, (_, row) in enumerate(overrides.iterrows()):
        dists = utm.geometry.distance(pts.iloc[i])
        target = dists.idxmin()
        if str(row.get("drop", "")).strip().lower() in ("yes", "true", "1"):
            drop_idx.append(target)
            print(f"  override: dropping cluster at {row['lon']:.4f},{row['lat']:.4f}")
            continue
        print(f"  override: {villages.at[target, 'village']!r} -> {row['village']!r}")
        villages.at[target, "village"] = row["village"]
        villages.at[target, "named"] = True
        villages.at[target, "disputed"] = False
        villages.at[target, "confidence"] = 1.0

    return villages.drop(index=drop_idx)


def main():
    tracks = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    ends = endpoints(tracks)
    if ends.empty:
        print("no usable endpoints")
        return

    ends_utm = ends.to_crs(UTM55S)
    ends["cluster"] = cluster(list(ends_utm.geometry), CLUSTER_RADIUS_M)

    records = []
    for cid, grp in ends.groupby("cluster"):
        named = grp[grp["proposed"].notna()]
        # One vote per source file: the Sakarina GeoPackage holds six segments,
        # and letting each vote made a three-village blob look unanimous.
        votes = (
            named.drop_duplicates(subset=["source_file", "proposed"])["proposed"].value_counts()
        )

        if votes.empty:
            label, agree = None, 0
        else:
            label = votes.index[0]
            agree = int(votes.iloc[0])

        centre_utm = ends_utm.loc[grp.index].geometry.union_all().centroid
        centre = gpd.GeoSeries([centre_utm], crs=UTM55S).to_crs(WGS84).iloc[0]

        records.append(
            {
                "village": label or f"unnamed_{cid}",
                "named": label is not None,
                "endpoints": len(grp),
                "tracks": grp["track"].nunique(),
                "agreeing": agree,
                "confidence": round(agree / len(named), 2) if len(named) else 0.0,
                "alternatives": "; ".join(f"{k}({v})" for k, v in list(votes.items())[1:4]),
                "evidence": " | ".join(sorted(grp["track"].unique()))[:300],
                "geometry": centre,
            }
        )

    villages = gpd.GeoDataFrame(records, geometry="geometry", crs=WGS84)
    villages = merge_same_name(villages)
    villages = villages.sort_values(["tracks", "agreeing"], ascending=False).reset_index(drop=True)
    print("Resolving name conflicts:")
    villages = resolve_conflicts(villages)
    villages = apply_name_overrides(villages)
    villages = villages.sort_values(["named", "tracks", "agreeing"], ascending=False).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    villages.to_file(PROCESSED / "villages.gpkg", layer="villages", driver="GPKG")
    villages.drop(columns="geometry").to_csv(PROCESSED / "villages.csv", index=False)

    multi = villages[villages["tracks"] > 1]
    print(f"{len(villages)} endpoint cluster(s); {len(multi)} confirmed by more than one track\n")
    cols = ["village", "tracks", "endpoints", "agreeing", "confidence"]
    print(villages[cols].to_string(index=False))
    print(f"\nwrote {PROCESSED / 'villages.gpkg'}")


if __name__ == "__main__":
    main()
