"""Where is the road slow, and what makes it slow?

Method
------
Every driven GPS recording is broken into point-to-point steps, each of which
carries a distance and a time and therefore a speed. Those steps are attached to
the nearest 500 m chunk of the road and averaged, so what is mapped is measured
travel, not a road class or an assumption.

Two things are deliberately excluded from the average:

  stopped time   steps below 3 km/h are dropped. A vehicle parked at a village
                 would otherwise drag a chunk's mean down and read as bad road.
  long gaps      steps spanning more than 120 s, or more than 500 m, are dropped
                 as recorder dropouts rather than real travel.
  walked legs    a recording can be part driven and part walked - one of these
                 files is called "track AND road to Afore" and is exactly that.
                 Filtering whole recordings let its walked leg through as 3 km/h
                 road, which read as catastrophically bad surface. A stretch
                 therefore counts as driven only if the vehicle reached road
                 speed somewhere within a two-minute window of it; walking never
                 does, so the walked leg drops out while a genuine crawl on a bad
                 stretch of a driven road is kept.

Each chunk then gets its terrain measured from the Copernicus 30 m DEM and its
curvature from its own geometry, so the slow chunks can be asked why they are
slow rather than just labelled. Gradient, curvature and elevation are reported
against speed; nothing is asserted as a cause that the numbers do not support.

A chunk with few observations is not evidence. The number of steps and the
number of distinct runs behind each chunk are carried through to the output and
chunks below a minimum are left unclassified rather than shown pale.

Writes outputs/access/mca_road_speed.geojson and fig_road_speed.png
"""

import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.lines import Line2D
from rasterio.merge import merge
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_mode import collect, DRIVE_MIN_KMH, FAST_POINT_KMH, haversine

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "access"
DEM_DIR = ROOT / "data" / "dem"

WGS84 = "EPSG:4326"
UTM = "EPSG:32755"

CHUNK_M = 500.0
MOVING_MIN_KMH = 3.0      # below this the vehicle was stopped, not travelling
DRIVEN_WINDOW_S = 120.0   # the neighbourhood a stretch is judged over
DRIVEN_WINDOW_KMH = 10.0  # road speed reached within that window = a vehicle
MAX_SNAP_M = 60.0         # a step further than this from the road is not on it
MIN_STEPS = 8             # fewer observations than this is not evidence

SURFACE = "#fcfcfb"
INK = "#1c1b19"
INK_SOFT = "#6b6963"
BOUNDARY_FILL = "#f2f1ec"
BOUNDARY_EDGE = "#898781"


def chunks_of(line, step=CHUNK_M):
    """Cut a line into pieces of roughly `step` metres."""
    L = line.length
    if L <= step:
        return [line]
    n = max(int(round(L / step)), 1)
    out = []
    for i in range(n):
        a, b = L * i / n, L * (i + 1) / n
        pts = [line.interpolate(a)]
        # keep the real vertices in between so the shape is not lost
        for c in line.coords:
            d = line.project(Point(c))
            if a < d < b:
                pts.append(Point(c))
        pts.append(line.interpolate(b))
        if len(pts) >= 2:
            out.append(LineString([(p.x, p.y) for p in pts]))
    return out


def driven_steps():
    """Every point-to-point step from a recording that was driven."""
    runs = collect()
    if runs.empty:
        return gpd.GeoDataFrame()
    motor = runs[(runs["median"] >= DRIVE_MIN_KMH) |
                 (runs["frac_fast"] >= 0.25)]
    print(f"{len(motor)} driven runs, from {motor['source_file'].nunique()} files:")
    for f, g in motor.groupby("source_file"):
        print(f"   {f[:56]:<56} {len(g)} run(s), median {g['median'].median():.1f} km/h")

    # collect() discarded the raw points, so re-walk the sources it kept
    from classify_mode import parse_gpx, parse_kmz, parse_kml_text, RAW
    rows = []
    wanted = set(motor["source_file"])
    for path in sorted(RAW.glob("*")):
        if path.name not in wanted:
            continue
        if path.suffix.lower() == ".gpx":
            gen = parse_gpx(path)
        elif path.suffix.lower() == ".kmz":
            gen = parse_kmz(path)
        elif path.suffix.lower() == ".kml":
            gen = parse_kml_text(path.read_text(errors="ignore"))
        else:
            continue
        for run_i, (lat, lon, t) in enumerate(gen):
            lat, lon, t = np.array(lat), np.array(lon), np.array(t)
            d = haversine(lat[:-1], lon[:-1], lat[1:], lon[1:])
            dt = np.diff(t)
            ok = (dt > 0) & (dt < 120) & (d < 500)
            v = np.full(len(d), np.nan)
            v[ok] = d[ok] / dt[ok] * 3.6
            mlat = (lat[:-1] + lat[1:]) / 2
            mlon = (lon[:-1] + lon[1:]) / 2

            # Was the traveller in a vehicle just here? Take the fastest step
            # within a two-minute window either side; a walker never reaches
            # road speed, a vehicle crawling over a bad patch did so recently.
            mt = (t[:-1] + t[1:]) / 2
            local_max = np.zeros(len(v))
            for i in range(len(v)):
                w = np.abs(mt - mt[i]) <= DRIVEN_WINDOW_S
                vals = v[w & ok]
                local_max[i] = np.nanmax(vals) if len(vals) else np.nan
            driven = local_max >= DRIVEN_WINDOW_KMH

            kept = ok & (v > MOVING_MIN_KMH) & driven
            dropped = int((ok & (v > MOVING_MIN_KMH) & ~driven).sum())
            if dropped:
                print(f"      {path.name}#{run_i}: {dropped} steps dropped as walked")
            for i in np.where(kept)[0]:
                rows.append({"run": f"{path.name}#{run_i}", "source_file": path.name,
                             "kmh": float(v[i]), "m": float(d[i]),
                             "geometry": Point(mlon[i], mlat[i])})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)


class Dem:
    def __init__(self):
        files = sorted(DEM_DIR.glob("*.tif"))
        self.arr, self.tf = merge([rasterio.open(f) for f in files])
        self.arr = self.arr[0].astype(float)

    def z(self, lons, lats):
        r, c = rasterio.transform.rowcol(self.tf, lons, lats)
        r = np.clip(np.asarray(r), 0, self.arr.shape[0] - 1)
        c = np.clip(np.asarray(c), 0, self.arr.shape[1] - 1)
        return self.arr[r, c]


def terrain(chunk_u, chunk_ll, dem):
    """Gradient, curvature and mean elevation of one chunk."""
    n = max(int(chunk_u.length // 50), 3)
    fr = np.linspace(0, 1, n + 1)
    pu = [chunk_u.interpolate(x, normalized=True) for x in fr]
    pl = [chunk_ll.interpolate(x, normalized=True) for x in fr]
    z = dem.z(np.array([p.x for p in pl]), np.array([p.y for p in pl]))
    d = np.maximum(np.hypot(np.diff([p.x for p in pu]), np.diff([p.y for p in pu])), 1e-6)
    grad = np.abs(np.diff(z)) / d * 100
    # curvature: how much longer the road is than the straight line across it
    straight = Point(pu[0].x, pu[0].y).distance(Point(pu[-1].x, pu[-1].y))
    sinuosity = chunk_u.length / straight if straight > 1 else np.nan
    return (float(np.mean(grad)), float(np.max(grad)), float(np.mean(z)),
            float(sinuosity))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dem = Dem()

    steps = driven_steps()
    if steps.empty:
        print("no driven steps found")
        return 1
    print(f"\n{len(steps)} moving steps, {steps['m'].sum()/1000:.0f} km of travel")

    tracks = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    roads_u = tracks[tracks["mode"] == "Motor road"].to_crs(UTM)

    merged = unary_union(list(roads_u.geometry))
    parts = [merged] if merged.geom_type == "LineString" else \
        [g for g in merged.geoms if g.geom_type == "LineString"]
    pieces = [c for p in parts for c in chunks_of(p)]
    print(f"road split into {len(pieces)} chunks of ~{CHUNK_M:.0f} m")

    ch = gpd.GeoDataFrame({"geometry": pieces}, crs=UTM)
    su = steps.to_crs(UTM)

    # attach each step to its nearest chunk
    joined = gpd.sjoin_nearest(su, ch.reset_index().rename(columns={"index": "chunk"}),
                               how="left", max_distance=MAX_SNAP_M,
                               distance_col="snap_m")
    joined = joined.dropna(subset=["chunk"])
    print(f"{len(joined)} of {len(su)} steps fall within {MAX_SNAP_M:.0f} m of the road")

    agg = joined.groupby("chunk").agg(
        kmh_mean=("kmh", "mean"), kmh_median=("kmh", "median"),
        kmh_p15=("kmh", lambda s: float(np.percentile(s, 15))),
        steps=("kmh", "size"), runs=("run", "nunique"),
        metres=("m", "sum")).reset_index()

    ch = ch.reset_index().rename(columns={"index": "chunk"}).merge(agg, on="chunk", how="left")
    ch_ll = ch.to_crs(WGS84)
    ter = [terrain(gu, gl, dem) for gu, gl in zip(ch.geometry, ch_ll.geometry)]
    ch["grad_mean_pct"] = np.round([t[0] for t in ter], 2)
    ch["grad_max_pct"] = np.round([t[1] for t in ter], 2)
    ch["elev_m"] = np.round([t[2] for t in ter], 0)
    ch["sinuosity"] = np.round([t[3] for t in ter], 3)
    ch["length_m"] = np.round(ch.geometry.length, 1)
    ch["observed"] = ch["steps"].fillna(0) >= MIN_STEPS

    obs = ch[ch["observed"]].copy()
    print(f"\n{len(obs)} chunks have >= {MIN_STEPS} observations "
          f"({obs['length_m'].sum()/1000:.0f} km of the {ch['length_m'].sum()/1000:.0f} km network)")

    if obs.empty:
        print("nothing observed well enough to map")
        return 1

    print(f"speed over observed road: median {obs['kmh_median'].median():.1f} km/h, "
          f"slowest chunk {obs['kmh_median'].min():.1f}, fastest {obs['kmh_median'].max():.1f}")

    # --- what goes with slow? ------------------------------------------------
    print("\nrelation of speed to terrain, over observed chunks "
          "(Spearman, so monotonic not linear):")
    for col in ("grad_mean_pct", "grad_max_pct", "sinuosity", "elev_m"):
        sub = obs[["kmh_median", col]].dropna()
        if len(sub) > 10:
            r = sub["kmh_median"].corr(sub[col], method="spearman")
            print(f"   {col:<16} rho {r:+.3f}   (n={len(sub)})")

    q = obs["kmh_median"].quantile(0.20)
    slow = obs[obs["kmh_median"] <= q]
    fast = obs[obs["kmh_median"] >= obs["kmh_median"].quantile(0.80)]
    print(f"\nslowest fifth (<= {q:.1f} km/h, {len(slow)} chunks, "
          f"{slow['length_m'].sum()/1000:.1f} km) against fastest fifth:")
    for col, unit in (("grad_mean_pct", "%"), ("grad_max_pct", "%"),
                      ("sinuosity", ""), ("elev_m", " m")):
        print(f"   {col:<16} slow {slow[col].median():7.2f}{unit}"
              f"     fast {fast[col].median():7.2f}{unit}")

    ch.to_crs(WGS84).to_file(OUT / "mca_road_speed.geojson", driver="GeoJSON")
    print(f"\nwrote {OUT/'mca_road_speed.geojson'}")

    # --- the map -------------------------------------------------------------
    boundary = gpd.read_file(PROCESSED / "mca_boundary.gpkg", layer="boundary").to_crs(UTM)
    villages = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")

    fig, (ax, axh) = plt.subplots(
        1, 2, figsize=(15.5, 8.4), facecolor=SURFACE,
        gridspec_kw={"width_ratios": [2.55, 1]})
    ax.set_facecolor(SURFACE)

    boundary.plot(ax=ax, facecolor=BOUNDARY_FILL, edgecolor="none", zorder=0)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.2,
                           linestyle=(0, (6, 3)), zorder=1)

    # unobserved road drawn thin and grey: absence of measurement, not slowness
    un = ch[~ch["observed"]]
    if not un.empty:
        un.plot(ax=ax, color="#c9c7c1", lw=1.3, zorder=2)

    # sequential ramp, one hue, dark = slow. Speed is a magnitude, not a category.
    bands = [(0, 10, "#7f2704", "under 10 km/h"),
             (10, 15, "#d94801", "10–15"),
             (15, 20, "#fd8d3c", "15–20"),
             (20, 99, "#fdd0a2", "over 20")]
    for lo, hi, colour, _ in bands:
        sel = obs[(obs["kmh_median"] >= lo) & (obs["kmh_median"] < hi)]
        if sel.empty:
            continue
        sel.plot(ax=ax, color="#ffffff", lw=4.6, zorder=3)
        sel.plot(ax=ax, color=colour, lw=3.0, zorder=4)

    # the worst chunks, ringed and labelled
    worst = obs.nsmallest(5, "kmh_median")
    wc = worst.to_crs(UTM).geometry.centroid
    ax.scatter(wc.x, wc.y, s=190, facecolor="none", edgecolor=INK, lw=1.5, zorder=6)
    # fan the labels so five callouts in a small area do not sit on each other
    offsets = [(11, 11), (11, -16), (-64, 12), (-64, -18), (11, 26)]
    for k, ((x, y), (_, r)) in enumerate(zip(zip(wc.x, wc.y), worst.iterrows())):
        ax.annotate(f"{r['kmh_median']:.0f} km/h\n{r['grad_max_pct']:.0f}% max grade",
                    (x, y), xytext=offsets[k % len(offsets)],
                    textcoords="offset points", fontsize=7.4, color=INK,
                    arrowprops=dict(arrowstyle="-", color="#8a8880", lw=0.7),
                    bbox=dict(boxstyle="round,pad=0.25", fc="#ffffffdd", ec="none"))

    vg = gpd.GeoSeries([Point(r.lon, r.lat) for r in villages.itertuples()],
                       crs=WGS84).to_crs(UTM)
    ax.scatter(vg.x, vg.y, s=9, color="#6b6963", zorder=5, linewidths=0)

    ax.set_axis_off()
    ax.set_aspect("equal")
    minx, miny, maxx, maxy = obs.total_bounds
    pad = max(maxx - minx, maxy - miny) * 0.10
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)

    handles = [Line2D([], [], color=c, lw=3.2, label=lab) for _, _, c, lab in bands]
    handles.append(Line2D([], [], color="#c9c7c1", lw=1.6,
                          label="road with too few passes to measure"))
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8.4,
              title="median driven speed", title_fontsize=8.8)

    # gradient against speed, which is the relationship worth showing
    axh.set_facecolor(SURFACE)
    axh.scatter(obs["grad_max_pct"], obs["kmh_median"], s=16, color="#d94801",
                alpha=0.55, linewidths=0)
    axh.set_xlabel("steepest gradient in the chunk (%)", fontsize=8.6, color=INK)
    axh.set_ylabel("median driven speed (km/h)", fontsize=8.6, color=INK)
    axh.tick_params(labelsize=8, colors=INK_SOFT)
    for sp in ("top", "right"):
        axh.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        axh.spines[sp].set_color("#d8d6d0")
    axh.grid(axis="y", color="#ecebe6", lw=0.8)
    axh.set_axisbelow(True)
    sub = obs[["grad_max_pct", "kmh_median"]].dropna()
    if len(sub) > 10:
        rho = sub["kmh_median"].corr(sub["grad_max_pct"], method="spearman")
        axh.set_title(f"Spearman rho {rho:+.2f}", fontsize=9, color=INK_SOFT, loc="left")

    fig.suptitle("Where the Managalas road is slow, and whether the terrain explains it",
                 fontsize=14.5, color=INK, x=0.5, y=0.97, weight="bold")
    fig.text(0.5, 0.935,
             f"Measured from {steps['run'].nunique()} driven GPS recordings · "
             f"{CHUNK_M:.0f} m chunks · stopped time excluded · "
             f"gradient from Copernicus 30 m DEM",
             ha="center", fontsize=8.8, color=INK_SOFT)
    fig.tight_layout(rect=[0, 0.02, 1, 0.92])
    out_png = ROOT / "outputs" / "access" / "fig_road_speed.png"
    fig.savefig(out_png, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {out_png}")

    print("\nthe five slowest measured chunks:")
    cols = ["kmh_median", "kmh_p15", "steps", "runs", "grad_mean_pct",
            "grad_max_pct", "sinuosity", "elev_m"]
    print(worst[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
