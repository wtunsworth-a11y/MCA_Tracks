"""Decide which recorded tracks are motorable roads and which are walked.

Why this exists
---------------
The track names cannot be used. Locally a foot track is called a road, so
"Bioi village to Omajeap main road" and "Kuhenei to Dakanatam main road" are
both walked, and an earlier classification in this repository that trusted the
names got them wrong. Something measured has to decide it instead.

The evidence, strongest first
-----------------------------
1. SPEED. The recordings carry per-point timestamps, so the actual travel speed
   is in the data and needs nothing external. A vehicle and a person on foot are
   not confusable: measured over these files the walked recordings sit at 2.7 to
   4.4 km/h median and never exceed 12 km/h, while the driven ones sit at 11.7
   to 15.1 km/h with half their moving time above 12 km/h. The gap between 4.4
   and 11.7 is empty, so the cut is put in the middle of it.

2. THE 1973 SURVEY. Five KMZ files carry no timestamps. For those, the T683
   sheets decide: the surveyors drew road, vehicle track and foot track as
   separate classes, so a modern line lying along a 1973 red line is motorable
   and one lying along black, or along nothing, is not. This is weaker than
   speed - a road can have been built since 1973 - so it is recorded as such.

3. GRADIENT, from the Copernicus 30 m DEM. Measured against the tracks that
   speed had already settled, every driven one has an 85th-percentile gradient
   of 15.8 per cent or less, while walked ones run to 36.9 per cent. The two
   overlap between 11 and 16 per cent, so gradient cannot confirm a road - but
   nothing above the observed ceiling is one. It is therefore used only to rule
   out, never to rule in.

4. OVERLAP with a track that speed already proved motorable. The same road
   often got recorded more than once, and a second recording of a road is a
   road. This is what identifies the Popondetta to Anatua road, a 151 km KMZ
   with no timestamps that runs along a GPX driven at 15 km/h.

Every track carries the evidence that classified it, so nothing rests on a
judgement that cannot be re-examined.

Writes data/processed/tracks.gpkg layer "tracks" back with mode, mode_evidence,
speed_kmh_median and speed_frac_over_12.
"""

import glob
import re
import sqlite3
import warnings
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# The empty band between the fastest walked track and the slowest driven one.
WALK_MAX_KMH = 4.5
DRIVE_MIN_KMH = 11.0
# The steepest 85th-percentile gradient seen on any speed-confirmed motor road
# was 15.8 per cent. Allow a little headroom and treat anything beyond as not
# motorable. One-sided on purpose: gentle gradient proves nothing on its own.
MAX_ROAD_GRADIENT_PCT = 18.0
# How much of a track must lie along a proven road before it is itself called
# one. Set from the data, which is sharply bimodal: 23 of the 27 promotions sit
# at 98-100 per cent - a second recording of the same road - and 4 sit at 68 to
# 85 per cent, which is a foot track running alongside a road for part of its
# way. At 0.60 the looser four were promoted, and one of them, named "Siribu
# Bush Track", is what made Siribu look road-served when it is not.
OVERLAP_MIN = 0.95
# Likewise for the 1973 fallback. Exactly one feature was promoted by it, at 52
# per cent, and that too was at Siribu.
SURVEY_1973_MIN = 0.70
FAST_POINT_KMH = 12.0     # a moving point above this is vehicle-like
MIN_POINTS = 20
MAX_GAP_S = 120
MAX_STEP_M = 500
STOPPED_KMH = 0.7         # below this the recorder was not moving

R = 6371000.0


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    return 2 * R * np.arcsin(np.sqrt(
        np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))


def speed_stats(lat, lon, t):
    """Median moving speed and the share of moving time above the vehicle cut."""
    lat, lon, t = np.asarray(lat), np.asarray(lon), np.asarray(t)
    if len(lat) < MIN_POINTS:
        return None
    d = haversine(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dt = np.diff(t)
    ok = (dt > 0) & (dt < MAX_GAP_S) & (d < MAX_STEP_M)
    if ok.sum() < MIN_POINTS:
        return None
    v = d[ok] / dt[ok] * 3.6
    moving = v[v > STOPPED_KMH]
    if len(moving) < MIN_POINTS:
        return None
    return {"median": float(np.median(moving)),
            "p90": float(np.percentile(moving, 90)),
            "frac_fast": float((moving > FAST_POINT_KMH).mean()),
            "n": int(len(moving))}


def parse_gpx(path):
    txt = path.read_text(errors="ignore")
    for seg in re.findall(r"<trkseg>(.*?)</trkseg>", txt, re.S):
        pts = re.findall(
            r'<trkpt[^>]*lat="([-\d.]+)"[^>]*lon="([-\d.]+)"[^>]*>(.*?)</trkpt>',
            seg, re.S)
        lat, lon, t = [], [], []
        for la, lo, body in pts:
            ts = re.search(r"<time>([^<]+)</time>", body)
            if not ts:
                continue
            lat.append(float(la)); lon.append(float(lo))
            t.append(datetime.fromisoformat(
                ts.group(1).replace("Z", "+00:00")).timestamp())
        if len(lat) >= MIN_POINTS:
            yield lat, lon, t


def parse_kml_text(txt):
    """gx:Track pairs <when> with <gx:coord>, which is how Locus writes KML."""
    for blk in re.findall(r"<gx:Track>(.*?)</gx:Track>", txt, re.S):
        whens = re.findall(r"<when>([^<]+)</when>", blk)
        coords = re.findall(r"<gx:coord>([^<]+)</gx:coord>", blk)
        lat, lon, t = [], [], []
        for w, c in zip(whens, coords):
            parts = c.split()
            if len(parts) < 2:
                continue
            try:
                ts = datetime.fromisoformat(w.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            lon.append(float(parts[0])); lat.append(float(parts[1])); t.append(ts)
        if len(lat) >= MIN_POINTS:
            yield lat, lon, t


def parse_kmz(path):
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        for n in names:
            yield from parse_kml_text(zf.read(n).decode("utf8", "ignore"))


def parse_gpkg(path):
    """Point tables with a timestamp column, grouped into runs."""
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("SELECT table_name, column_name FROM gpkg_geometry_columns")
    for table, geom_col in cur.fetchall():
        cur.execute(f"PRAGMA table_info('{table}')")
        cols = [c[1] for c in cur.fetchall()]
        tcol = next((c for c in cols if c.lower() == "timestamp"), None)
        if not tcol:
            continue
        try:
            sub = gpd.read_file(path, layer=table)
        except Exception:
            continue
        if sub.empty or not sub.geom_type.iloc[0].endswith("Point"):
            continue
        ts = []
        for v in sub[tcol]:
            try:
                ts.append(datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp())
            except Exception:
                ts.append(np.nan)
        sub = sub.assign(_t=ts).dropna(subset=["_t"]).sort_values("_t")
        if len(sub) < MIN_POINTS:
            continue
        # split where the recorder was off for more than ten minutes
        gaps = np.where(np.diff(sub["_t"].values) > 600)[0]
        for chunk in np.split(np.arange(len(sub)), gaps + 1):
            if len(chunk) < MIN_POINTS:
                continue
            part = sub.iloc[chunk]
            yield (list(part.geometry.y), list(part.geometry.x), list(part["_t"]))
    con.close()


def collect():
    """Every timestamped run we can find, with its speed and its geometry."""
    runs = []
    for path in sorted(RAW.glob("*")):
        if path.suffix.lower() == ".gpx":
            gen = parse_gpx(path)
        elif path.suffix.lower() == ".kmz":
            gen = parse_kmz(path)
        elif path.suffix.lower() == ".kml":
            gen = parse_kml_text(path.read_text(errors="ignore"))
        elif path.suffix.lower() == ".gpkg":
            gen = parse_gpkg(path)
        else:
            continue
        for lat, lon, t in gen:
            st = speed_stats(lat, lon, t)
            if st is None:
                continue
            runs.append({"source_file": path.name,
                         "geometry": LineString(np.column_stack([lon, lat])),
                         **st})
    return gpd.GeoDataFrame(runs, geometry="geometry", crs="EPSG:4326")


def track_gradients(tracks, tu):
    """85th-percentile absolute gradient along each track, from the DEM."""
    import glob as _glob
    import rasterio
    from rasterio.merge import merge
    files = sorted(_glob.glob(str(ROOT / "data" / "dem" / "*.tif")))
    if not files:
        return np.full(len(tracks), np.nan)
    arr, tf = merge([rasterio.open(f) for f in files])
    arr = arr[0].astype(float)

    out = []
    for geom_u, geom_ll in zip(tu.geometry, tracks.geometry):
        L = geom_u.length
        if L < 300:
            out.append(np.nan)
            continue
        n = max(int(L // 50), 8)
        fr = np.linspace(0, 1, n)
        pu = [geom_u.interpolate(x, normalized=True) for x in fr]
        pl = [geom_ll.interpolate(x, normalized=True) for x in fr]
        r, c = rasterio.transform.rowcol(tf, [p.x for p in pl], [p.y for p in pl])
        r = np.clip(np.asarray(r), 0, arr.shape[0] - 1)
        c = np.clip(np.asarray(c), 0, arr.shape[1] - 1)
        z = arr[r, c]
        d = np.hypot(np.diff([p.x for p in pu]), np.diff([p.y for p in pu]))
        g = np.abs(np.diff(z)) / np.maximum(d, 1e-6) * 100
        g = g[np.isfinite(g)]
        out.append(float(np.percentile(g, 85)) if len(g) else np.nan)
    return np.array(out)


def classify_speed(median, frac_fast):
    if median >= DRIVE_MIN_KMH or frac_fast >= 0.25:
        return "Motor road"
    if median <= WALK_MAX_KMH:
        return "Foot track"
    return None            # in the empty band: let another line of evidence decide


def main():
    tracks = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    runs = collect()
    print(f"{len(runs)} timestamped runs recovered from {runs['source_file'].nunique()} files")

    utm = "EPSG:32755"
    tu = tracks.to_crs(utm)
    ru = runs.to_crs(utm)

    modes, evid, med, frac = [], [], [], []
    for i, geom in enumerate(tu.geometry):
        src = tracks.iloc[i]["source_file"]
        cand = ru[ru["source_file"] == src]
        pick = None
        if not cand.empty:
            # the run whose line lies closest to this track
            d = cand.geometry.apply(lambda g: g.distance(geom))
            j = d.idxmin()
            if d.loc[j] < 200:
                pick = runs.loc[j]
        if pick is not None:
            m = classify_speed(pick["median"], pick["frac_fast"])
            if m:
                modes.append(m)
                evid.append(f"GPS speed: median {pick['median']:.1f} km/h, "
                            f"{pick['frac_fast']*100:.0f}% of moving time >12 km/h")
                med.append(round(pick["median"], 2)); frac.append(round(pick["frac_fast"], 3))
                continue
            med.append(round(pick["median"], 2)); frac.append(round(pick["frac_fast"], 3))
        else:
            med.append(np.nan); frac.append(np.nan)
        modes.append(None); evid.append(None)

    tracks["mode"] = modes
    tracks["mode_evidence"] = evid
    tracks["speed_kmh_median"] = med
    tracks["speed_frac_over_12"] = frac

    # ---- gradient, for the veto -------------------------------------------
    grad = track_gradients(tracks, tu)
    tracks["grad_p85_pct"] = np.round(grad, 1)

    # ---- fallback 1: is this a second recording of a proven road? ----------
    proven = tu[tracks["mode"] == "Motor road"]
    if not proven.empty:
        proven_union = proven.geometry.union_all()
        need = tracks["mode"].isna()
        for i in np.where(need.values)[0]:
            g = tu.geometry.iloc[i]
            pts = [g.interpolate(x, normalized=True) for x in np.linspace(0, 1, 40)]
            share = float(np.mean([p.distance(proven_union) < 150 for p in pts]))
            if share >= OVERLAP_MIN:
                tracks.loc[tracks.index[i], "mode"] = "Motor road"
                tracks.loc[tracks.index[i], "mode_evidence"] = (
                    f"overlap: {share*100:.0f}% of its length runs along a track "
                    f"measured at road speed (no timestamps of its own)")

    # Fallback for the untimestamped: what did the 1973 surveyors draw here?
    hist_path = PROCESSED / "historic_tracks.gpkg"
    if hist_path.exists():
        hist = gpd.read_file(hist_path, layer="tracks_1973").to_crs(utm)
        motor73 = hist[hist["type"].isin(["Road", "Vehicle track"])].geometry.union_all()
        foot73 = hist[hist["type"] == "Foot track"].geometry.union_all()
        need = tracks["mode"].isna()
        print(f"\n{need.sum()} tracks have no usable timestamps; using the 1973 survey")
        for i in np.where(need.values)[0]:
            g = tu.geometry.iloc[i]
            pts = [g.interpolate(x, normalized=True) for x in np.linspace(0, 1, 40)]
            dm = np.array([p.distance(motor73) for p in pts])
            df = np.array([p.distance(foot73) for p in pts])
            near_motor = (dm < 150).mean()
            near_foot = (df < 150).mean()
            g85 = tracks["grad_p85_pct"].iloc[i]
            too_steep = g85 == g85 and g85 > MAX_ROAD_GRADIENT_PCT
            if near_motor >= SURVEY_1973_MIN and near_motor > near_foot and not too_steep:
                tracks.loc[tracks.index[i], "mode"] = "Motor road"
                tracks.loc[tracks.index[i], "mode_evidence"] = (
                    f"1973 survey: {near_motor*100:.0f}% of its length follows a "
                    f"1973 road or vehicle track; gradient {g85:.0f}% is within "
                    f"what a road here does (no timestamps to measure speed)")
            elif too_steep:
                tracks.loc[tracks.index[i], "mode"] = "Foot track"
                tracks.loc[tracks.index[i], "mode_evidence"] = (
                    f"gradient {g85:.0f}% exceeds the {MAX_ROAD_GRADIENT_PCT:.0f}% "
                    f"ceiling seen on every measured road here, so not motorable "
                    f"(no timestamps to measure speed)")
            else:
                tracks.loc[tracks.index[i], "mode"] = "Foot track"
                tracks.loc[tracks.index[i], "mode_evidence"] = (
                    f"1973 survey: only {near_motor*100:.0f}% follows a 1973 motorable "
                    f"line ({near_foot*100:.0f}% follows a foot track); "
                    f"no timestamps to measure speed")

    tracks["mode"] = tracks["mode"].fillna("Foot track")
    tracks["mode_evidence"] = tracks["mode_evidence"].fillna(
        "no timestamps and no 1973 line nearby; defaulted to foot track")

    tracks.to_file(PROCESSED / "tracks.gpkg", layer="tracks", driver="GPKG")

    print("\n--- mode by length")
    print(tracks.groupby("mode")["length_km"].agg(["count", "sum"]).round(1).to_string())
    print("\n--- tracks whose NAME says road but which were walked")
    named_road = tracks[tracks["name"].str.contains("road", case=False, na=False)]
    wrong = named_road[named_road["mode"] == "Foot track"]
    for _, r in wrong.iterrows():
        print(f"  {r['name'][:52]:<52} {r['length_km']:6.2f} km  "
              f"{('%.1f km/h' % r['speed_kmh_median']) if r['speed_kmh_median']==r['speed_kmh_median'] else 'no timestamps'}")
    print(f"\n{len(wrong)} of {len(named_road)} tracks named 'road' are walked "
          f"({wrong['length_km'].sum():.1f} km)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
