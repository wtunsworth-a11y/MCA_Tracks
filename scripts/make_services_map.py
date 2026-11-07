"""Government services across the conservation area, and which still work.

    python3 scripts/make_services_map.py            all three maps

Writes outputs/access/services.csv and three maps:

    fig_services_schools.png   28 schools         Will, 7 Nov 2026: priority
    fig_services_health.png     8 health posts    Will, 7 Nov 2026: priority
    fig_services.png            everything, 43

Schools and health get their own sheet because they are what the ward
profiles are asked about, and because a map carrying all 43 marks has to drop
most of its labels to stay readable. On their own sheet every school and
every aid post can be named.

Schools, health posts, airstrips and government offices. Churches are left
out: there are 27 of them and they are not a government service, however much
they matter to the places they stand in.

THE POINT OF THIS MAP IS THE DIFFERENCE BETWEEN BUILT AND WORKING. Russell
walked onto sites that the ward tables still list as facilities and found an
airstrip no aircraft has ever landed on, an aid post closed since about 1979
and a school with no buildings left. A map that drew those the same as
Itokama's health centre would be worse than no map, so a facility that is
closed, abandoned or was never used is drawn hollow and labelled.

Status comes from two places and the field wins:

  * what Russell typed standing in front of it - "Building in use", "Closed
    down", "Airstrip is not in operation", "No Elementary or Community School
    buildings can be seen here today"
  * failing that, the status column of the Afore LLG ward tables

Where neither says anything the mark is drawn as unknown rather than assumed
working, because assuming is how a closed aid post ends up on a plan.
"""
from pathlib import Path
import csv
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe          # noqa: E402
import matplotlib.pyplot as plt              # noqa: E402
from matplotlib.lines import Line2D          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_access_figures import (             # noqa: E402
    BOUNDARY_EDGE, INK, INK_SOFT, LAND, load, north_arrow, relief, scalebar,
)
from make_ward_map import institution_of      # noqa: E402
from reconcile_facilities import kinds_of     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WP_FILES = [ROOT / "data" / "reference" / "waypoints_facilities.csv",
            ROOT / "data" / "reference" / "waypoints_zone4.csv"]
FAC = ROOT / "data" / "reference" / "facilities.csv"
OUT_DIR = ROOT / "outputs" / "access"
# The layers go somewhere a person looking for them would look. Everything
# spatial in this repository had been landing in outputs/access, which is a
# workings folder named after a different question.
GIS = ROOT / "outputs" / "gis"
OUT_CSV = GIS / "mca_government_services.csv"

# Government services only. A church is not one.
SERVICE = {
    "elementary school": ("s", "#58A55C", 7.0, "Elementary school"),
    "primary school":    ("s", "#1B7A3E", 9.0, "Primary school"),
    "high school":       ("s", "#0B3D23", 11.0, "High / secondary school"),
    "aid post":          ("P", "#E07B39", 9.0, "Aid post"),
    "health centre":     ("P", "#A5281B", 11.0, "Health centre"),
    "airstrip":          ("X", "#6C3483", 11.0, "Airstrip"),
    "office":            ("D", "#34495E", 8.5, "Government office"),
}
ORDER = list(SERVICE)

# Each sheet: the kinds on it, the file, and the words for its title.
SHEETS = {
    "schools": (("elementary school", "primary school", "high school"),
                "fig_services_schools.png", "Schools"),
    "health":  (("aid post", "health centre"),
                "fig_services_health.png", "Health facilities"),
    "all":     (tuple(SERVICE), "fig_services.png", "Government services"),
}

# Somebody lives or cooks or stores things here. Seeing one of these standing
# is not seeing the facility.
ANCILLARY = re.compile(
    r"\b(teacher'?s?|head teacher'?s?|priest'?s?|dormitor|house|houses|"
    r"kitchen|mass|storage|store|toilet|ablution|oic'?s?)\b", re.I)

CLOSED = re.compile(
    r"\b(closed|not in operation|no longer|abandoned|never|stopped|"
    r"no elementary|no buildings|relocated|rundown|run down|disused)\b", re.I)
WORKING = re.compile(r"\b(in use|currently in use|operational|functioning)\b", re.I)


def status_of(name, notes):
    """working / closed / unknown, the field read before the ward table."""
    if re.search(r"\bold\b|\bformer\b", name, re.I):
        return "closed"
    for n in notes:
        if not n:
            continue
        if CLOSED.search(n):
            return "closed"
        if WORKING.search(n):
            return "working"
    return "unknown"


def collect_services():
    pts = []
    for path in WP_FILES:
        if path.exists():
            with path.open() as fh:
                pts += [r for r in csv.DictReader(
                    l for l in fh if not l.startswith("#"))]

    insts = {}
    for p in pts:
        key = institution_of(p["name"])
        if not key:
            continue
        kind = next((k for k in ORDER if k in kinds_of(key)), None)
        if kind is None:
            continue                      # a church, or something unclassified
        g = insts.setdefault(key, dict(kind=kind, pts=[], notes=[]))
        g["pts"].append(p)
        g["notes"].append(p["note"])

    # The ward tables' own status, as a fallback when the field said nothing.
    ward_status = {}
    if FAC.exists():
        with FAC.open() as fh:
            for r in csv.DictReader(l for l in fh if not l.startswith("#")):
                ward_status.setdefault(r["village"].strip().lower(), []).append(
                    (r["facility"], r.get("status", "")))

    rows = []
    for name, g in sorted(insts.items()):
        lon = sum(float(p["lon"]) for p in g["pts"]) / len(g["pts"])
        lat = sum(float(p["lat"]) for p in g["pts"]) / len(g["pts"])
        st = status_of(name, g["notes"])
        # "Building in use" written against a teacher's house does not make
        # the school working. Aiari's elementary school was drawn as open on
        # the strength of its teacher's house, when Russell had recorded, on
        # the same trip, that no school buildings can be seen there and
        # classes stopped in early 2025.
        if st == "working" and all(ANCILLARY.search(q["name"]) for q in g["pts"]):
            st = "unknown"
        if st == "unknown":
            first = name.split()[0].lower()
            for fac, s in ward_status.get(first, []):
                if s and (CLOSED.search(s) or WORKING.search(s)):
                    st = "closed" if CLOSED.search(s) else "working"
                    break
        rows.append(dict(facility=name, kind=g["kind"], status=st,
                         lon=f"{lon:.7f}", lat=f"{lat:.7f}",
                         buildings=len(g["pts"]),
                         seen_only_as=("ancillary buildings only"
                                       if all(ANCILLARY.search(q["name"])
                                              for q in g["pts"]) else ""),
                         evidence=" | ".join(n for n in g["notes"] if n)[:300]))
    return rows


def main():
    rows = collect_services()
    GIS.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        fh.write("# Government services in the MCA, one row per facility.\n"
                 "# status: working / closed / unknown. The field note is read\n"
                 "# before the ward table, and nothing is assumed working.\n")
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT_CSV}")

    import collections
    byk = collections.Counter((r["kind"], r["status"]) for r in rows)
    print(f"  {len(rows)} government services")
    for k in ORDER:
        tot = sum(v for (kk, _s), v in byk.items() if kk == k)
        if not tot:
            continue
        bits = ", ".join(f"{byk[(k, s)]} {s}" for s in ("working", "closed", "unknown")
                         if byk[(k, s)])
        print(f"    {tot:3d}  {SERVICE[k][3]:24s} ({bits})")
    write_layers(rows)

    for key, (kinds, fname, title) in SHEETS.items():
        sub = [r for r in rows if r["kind"] in kinds]
        if sub:
            draw(sub, OUT_DIR / fname, title, key == "all")


def write_layers(rows):
    """The same facilities as GIS layers, in the formats the team uses.

    KML because the team works in Google Earth, GeoPackage and shapefile
    because QGIS does, GeoJSON because everything else does. One set of
    attributes across all of them, and the evidence travels with the point:
    a status of "closed" is only worth anything next to the sentence that
    says why.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame(
        [{k: v for k, v in r.items() if k not in ("lon", "lat")} for r in rows],
        geometry=[Point(float(r["lon"]), float(r["lat"])) for r in rows],
        crs="EPSG:4326")

    gpkg = GIS / "mca_government_services.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    gdf.to_file(gpkg, layer="all_services", driver="GPKG")
    gdf.to_file(GIS / "mca_government_services.geojson", driver="GeoJSON")
    shp = GIS / "mca_government_services_shp"
    shp.mkdir(exist_ok=True)
    gdf.to_file(shp / "mca_government_services.shp")

    for key, (kinds, _f, title) in SHEETS.items():
        sub = gdf[gdf["kind"].isin(kinds)]
        if key == "all" or sub.empty:
            continue
        sub.to_file(gpkg, layer=key, driver="GPKG", mode="a")
        write_kml(sub, GIS / f"mca_{key}.kml", title)
    write_kml(gdf, GIS / "mca_government_services.kml", "Government services")
    print(f"wrote GIS layers to {GIS}")


def write_kml(gdf, path, title):
    """Foldered by kind, then by whether it works, because that is the
    question someone opens this file to answer."""
    from xml.sax.saxutils import escape
    ICON = {"working": "ff4CAF50", "closed": "ff3A3AB0", "unknown": "ff9A9A9A"}
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         f'<name>{escape(title)} — Managalas Conservation Area</name>',
         '<description><![CDATA[Status is what the recorder wrote standing in '
         'front of the building. <b>Nothing is assumed to be working.</b> '
         'Green is in use, red is closed or a former site, grey is not '
         'known.]]></description>']
    for st, col in ICON.items():
        L.append(f'<Style id="{st}"><IconStyle><color>{col}</color>'
                 f'<scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/'
                 f'kml/paddle/wht-blank.png</href></Icon></IconStyle></Style>')
    for kind in sorted(gdf["kind"].unique()):
        part = gdf[gdf["kind"] == kind]
        L.append(f'  <Folder><name>{escape(kind)} ({len(part)})</name><open>1</open>')
        for st in ("working", "closed", "unknown"):
            grp = part[part["status"] == st]
            if grp.empty:
                continue
            L.append(f'    <Folder><name>{st} ({len(grp)})</name><open>0</open>')
            for _i, r in grp.iterrows():
                bits = [f'<b>{escape(str(r["kind"]))}</b>, status: {st}',
                        f'{r["buildings"]} building(s) recorded']
                if r.get("seen_only_as"):
                    bits.append(f'<i>{escape(str(r["seen_only_as"]))}</i>')
                if r.get("evidence"):
                    bits.append(f'Recorded in the field: "{escape(str(r["evidence"]))}"')
                L.append(
                    f'      <Placemark><name>{escape(str(r["facility"]))}</name>'
                    f'<styleUrl>#{st}</styleUrl>'
                    f'<description><![CDATA[{"<br/>".join(bits)}]]></description>'
                    f'<Point><coordinates>{r.geometry.x:.7f},'
                    f'{r.geometry.y:.7f},0</coordinates></Point></Placemark>')
            L.append('    </Folder>')
        L.append('  </Folder>')
    L.append('</Document></kml>')
    path.write_text("\n".join(L) + "\n")


def draw(rows, out_fig, title_words, crowded):
    roads, foot, boundary, _vg, _sa = load()
    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)

    fig = plt.figure(figsize=(13.4, 9.0), facecolor="#FFFFFF")
    ax = fig.add_axes([0.012, 0.02, 0.73, 0.91])
    minx, miny, maxx, maxy = boundary.total_bounds
    padx, pady = (maxx - minx) * 0.05, (maxy - miny) * 0.05
    extent = (minx - padx, maxx + padx, miny - pady, maxy + pady)
    relief(ax, extent)
    boundary.plot(ax=ax, facecolor=LAND, edgecolor="none", alpha=0.22, zorder=1)
    boundary.boundary.plot(ax=ax, color=BOUNDARY_EDGE, lw=1.1,
                           linestyle=(0, (6, 3)), zorder=2)
    foot.plot(ax=ax, color="#9C9A94", lw=0.5, linestyle=(0, (3, 2)),
              alpha=0.6, zorder=3)
    roads.plot(ax=ax, color="#FFFFFF", lw=2.8, alpha=0.85, zorder=4)
    roads.plot(ax=ax, color="#1F6FB2", lw=1.4, zorder=5)

    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_axis_off()

    used = set()
    placed = []
    for r in rows:
        x, y = to_utm.transform(float(r["lon"]), float(r["lat"]))
        m, c, ms, _lab = SERVICE[r["kind"]]
        used.add(r["kind"])
        if r["status"] == "working":
            ax.plot(x, y, marker=m, ms=ms, mfc=c, mec="#FFFFFF", mew=1.0,
                    ls="none", zorder=9)
        else:
            # Hollow: built but not working, or nothing known.
            ax.plot(x, y, marker=m, ms=ms, mfc="#FFFFFF", mec=c, mew=1.6,
                    ls="none", zorder=8)
        placed.append((r, x, y))

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    # Label the scarce things and every closure. 26 schools in use would bury
    # the map, and a working school is the one case the symbol alone tells.
    def worth_naming(r):
        # On the combined sheet 26 working schools would bury the map, and a
        # working school is the one case the symbol alone already tells. On a
        # sheet of its own there is room for every name.
        if not crowded:
            return True
        return r["status"] != "working" or r["kind"] not in (
            "elementary school", "primary school")
    for r, x, y in sorted(placed, key=lambda t: -SERVICE[t[0]["kind"]][2]):
        if not worth_naming(r):
            continue
        txt = r["facility"]
        inward = -1 if x > (extent[0] + extent[1]) / 2 else 1
        for ox, dy in ((9, 3), (9, -11), (0, 11), (0, -16), (9, 15), (9, -24),
                       (18, 7), (18, -19)):
            t = ax.annotate(txt, (x, y), xytext=(ox * inward, dy),
                            textcoords="offset points",
                            ha="left" if inward > 0 else "right",
                            fontsize=7.4,
                            color=INK if r["status"] == "working" else INK_SOFT,
                            zorder=12)
            t.set_path_effects([pe.withStroke(linewidth=2.6,
                                              foreground="#FFFFFF")])
            b = t.get_window_extent(renderer=renderer).expanded(1.05, 1.25)
            if not any(b.overlaps(o) for o in boxes):
                boxes.append(b); break
            t.remove()

    handles = []
    for k in ORDER:
        if k in used:
            m, c, ms, lab = SERVICE[k]
            handles.append(Line2D([], [], marker=m, ls="none", ms=ms, mfc=c,
                                  mec="#FFFFFF", label=lab))
    handles += [
        Line2D([], [], marker="s", ls="none", ms=9, mfc="#777777",
               mec="#FFFFFF", label="filled = in use"),
        Line2D([], [], marker="s", ls="none", ms=9, mfc="#FFFFFF",
               mec="#777777", mew=1.6,
               label="hollow = closed, former site, or not known"),
        Line2D([], [], color="#1F6FB2", lw=1.4, label="Motorable road (recorded)"),
        Line2D([], [], color="#9C9A94", lw=0.8, linestyle=(0, (3, 2)),
               label="Foot track (recorded)"),
        Line2D([], [], color=BOUNDARY_EDGE, lw=1.1, linestyle=(0, (6, 3)),
               label="Conservation Area (WDPA)"),
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.015, 1.0),
              frameon=True, framealpha=1.0, fontsize=8.6, borderpad=0.8,
              labelspacing=0.6, edgecolor="#D5D8DC").set_zorder(14)

    work = sum(1 for r in rows if r["status"] == "working")
    shut = sum(1 for r in rows if r["status"] == "closed")
    ax.set_title(f"{title_words} in the Managalas Conservation Area — "
                 f"{len(rows)} recorded, {work} in use, {shut} closed or former",
                 fontsize=13, color=INK, pad=12, loc="left")
    ax.annotate("status is what the recorder wrote "
                "standing in front of the building, and nothing is assumed "
                "to be working",
                xy=(0.0, 1.004), xycoords="axes fraction", fontsize=8.4,
                color=INK_SOFT)
    north_arrow(ax); scalebar(ax)
    fig.savefig(out_fig, dpi=170, facecolor="#FFFFFF", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_fig}  ({len(rows)} marks)")


if __name__ == "__main__":
    main()
