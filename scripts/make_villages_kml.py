"""Every village and hamlet we hold a position for, as one KML.

outputs/access/mca_villages.kml

Positions come from five places and they do not agree, so the file keeps them
in separate folders rather than flattening them into one list of dots. Where
the same name appears in more than one source, the best-sourced position wins
and the others are dropped - the same precedence the checklist routes on:

    placed by the team  >  confirmed in the field  >  surveyed gazetteer
                        >  field waypoint file     >  our own GPS inference

Someone who has walked the ground outranks a gazetteer, and a gazetteer
outranks a cluster we inferred from where tracks happen to bunch up. The
folder a pin sits in says how much to trust it.

Surveyed villages carry their households and access class from
outputs/access/mca_village_access.csv, so the file answers "how many people
and how far from a road" as well as "where".
"""
from pathlib import Path
from xml.sax.saxutils import escape
import csv
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_placed, load_aliases, candidates, best_tier,
)

ROOT = Path(__file__).resolve().parent.parent
ACCESS = ROOT / "outputs" / "access" / "mca_village_access.csv"
WAYPOINTS = ROOT / "data" / "reference" / "waypoints_mca.csv"
STATUS = ROOT / "data" / "reference" / "village_status.csv"
OUT = ROOT / "outputs" / "access" / "mca_villages.kml"
OUT_SHP = ROOT / "outputs" / "access" / "mca_villages_shp"
OUT_GPX = ROOT / "outputs" / "access" / "mca_villages.gpx"

# Folder, pin colour (KML is aabbggrr), and how far to trust it.
TIERS = [
    ("placed by the team", "Placed by the team", "ff3ac0ff",
     "A pin someone dragged onto the spot. Trusted above everything else."),
    ("field evidence", "Confirmed in the field", "ff4ba34b",
     "Fixed by something said or walked in the field, recorded in "
     "place_aliases.csv with the reason."),
    ("gazetteer", "Surveyed villages", "ffc9681f",
     "The household survey's own positions, with its household counts."),
    ("waypoint file", "From the field waypoint file", "ffb06a9c",
     "Taken from the 246 waypoints Russell recorded across the MCA. Villages "
     "and hamlets only; creeks, rivers and junctions are left out."),
    ("GPS-inferred", "Inferred from the recordings", "ff949494",
     "Where recorded tracks bunch up. Weakest of the five - a cluster is not "
     "a village until somebody says so."),
]
ORDER = {k: i for i, (k, *_rest) in enumerate(TIERS)}


def access_rows():
    if not ACCESS.exists():
        return {}
    with ACCESS.open() as fh:
        return {r["village"].strip().lower(): r for r in csv.DictReader(fh)}


def status_notes():
    notes = {}
    if not STATUS.exists():
        return notes
    with STATUS.open() as fh:
        for r in csv.DictReader(l for l in fh if not l.startswith("#")):
            key = (r.get("village") or r.get("name") or "").strip().lower()
            if key:
                notes[key] = " ".join(v for k, v in r.items()
                                      if k not in ("village", "name") and v)
    return notes


def waypoint_places():
    """Villages and hamlets from the field waypoint file, named plainly."""
    if not WAYPOINTS.exists():
        return []
    out = []
    with WAYPOINTS.open() as fh:
        for r in csv.DictReader(l for l in fh if not l.startswith("#")):
            name = r["name"].strip()
            if not re.search(r"village|hamlet", name, re.I):
                continue
            # "Namieta, hamlet of Kokoro" keeps its whole name; "Natanga
            # Village" loses the bare type word so it matches what we call it.
            if "," not in name:
                name = re.sub(r"\s*\b(village|hamlet)\b\s*", " ", name,
                              flags=re.I).strip() or name
            out.append(dict(name=name, lon=float(r["lon"]), lat=float(r["lat"]),
                            src="waypoint file", note=f'recorded {r["recorded"]}'
                            if r["recorded"] else ""))
    return out


def collect():
    """name -> the single best position we hold for it."""
    best = {}

    def offer(name, lon, lat, src, note=""):
        name = name.strip()
        if not name or name.lower().startswith("unnamed"):
            return
        key = name.lower()
        rank = ORDER.get(src, 99)
        if key not in best or rank < best[key]["rank"]:
            best[key] = dict(name=name, lon=float(lon), lat=float(lat),
                             src=src, note=note, rank=rank)

    # Every source is canonicalised through the alias file before being
    # offered. Doing it for the gazetteer alone still left Gadzot beside Gajot
    # and Organ beside Ogan, because those two are team placements.
    aliases = load_aliases()

    def canon(name):
        al = aliases.get(str(name).strip().lower())
        return al["to"] if al and al["to"] else name

    for key, rec in load_placed().items():
        offer(canon(rec["name"]), rec["lon"], rec["lat"], "placed by the team",
              rec.get("note", ""))

    for written, al in aliases.items():
        if al["lon"] is not None and al["to"]:
            offer(al["to"], al["lon"], al["lat"], "field evidence", al["note"])
        _ = written

    for name, cands in load_places().items():
        if "/" in name:
            continue
        for c in cands:
            offer(canon(name), c["lon"], c["lat"], c.get("src", "GPS-inferred"),
                  c.get("note", ""))

    for w in waypoint_places():
        offer(canon(w["name"]), w["lon"], w["lat"], "waypoint file", w["note"])

    return best


def ext(fields):
    """ExtendedData, so QGIS and Earth both get the numbers as fields."""
    rows = "".join(f'<Data name="{k}"><value>{escape(str(v))}</value></Data>'
                   for k, v in fields.items() if v not in (None, ""))
    return f"<ExtendedData>{rows}</ExtendedData>" if rows else ""


def pin(rec, acc, notes, prof=None):
    bits = []
    rows = (prof or {}).get(rec["name"], [])
    if rows:
        hh = sum(r["households"] for r in rows)
        pop = sum(r["population"] for r in rows)
        names = ", ".join(r["village"] for r in rows)
        bits.append(f'<b>{pop:,} people, {hh} households</b> '
                    f'(Afore LLG Ward Profile)')
        bits.append(f'ward {rows[0]["ward"]}, zone {rows[0]["zone"]}')
        if len(rows) > 1 or names.lower() != rec["name"].lower():
            bits.append(f'listed there as: {escape(names)}')
    a = acc.get(rec["name"].lower())
    if a:
        bits.append(f'{a["households"]} households in the household survey, '
                    f'zone {a["zone"]}, ward {a["ward"]}')
        bits.append(f'{a["access_class"]}')
        if a.get("road_km"):
            bits.append(f'{a["road_km"]} km by road to {a["nearest_stop"]}')
    bits.append(f'position: {rec["src"]}')
    note = str(rec["note"] or "")
    # The gazetteer's own note is "zone N, M hh", which the access line above
    # has already said in full. Printing it twice just makes the bubble longer.
    if note and not (a and re.fullmatch(r"zone \S+, \d+ hh", note.strip())):
        bits.append(escape(note[:400]))
    flag = notes.get(rec["name"].lower())
    if flag:
        bits.append(f'<b>{escape(flag[:300])}</b>')
    body = "<br/>".join(bits)
    fields = {
        "source": rec["src"],
        "ward": rows[0]["ward"] if rows else (a["ward"] if a else ""),
        "zone": rows[0]["zone"] if rows else (a["zone"] if a else ""),
        "population": sum(r["population"] for r in rows) if rows else "",
        "households_profile": sum(r["households"] for r in rows) if rows else "",
        "households_hhs": a["households"] if a else "",
        "access_class": a["access_class"] if a else "",
        "road_km": a["road_km"] if a else "",
        "profile_names": ", ".join(r["village"] for r in rows) if rows else "",
    }
    return (f'    <Placemark><name>{escape(rec["name"])}</name>'
            f'<styleUrl>#{rec["src"].replace(" ", "_").replace("-", "_")}</styleUrl>'
            f'<description><![CDATA[{body}]]></description>'
            f'{ext(fields)}'
            f'<Point><coordinates>{rec["lon"]:.6f},{rec["lat"]:.6f},0</coordinates>'
            f'</Point></Placemark>')


def write_gis(best, acc, prof):
    """The same table as a shapefile and as GPX waypoints.

    Shapefile field names are capped at 10 characters by the format, hence
    the abbreviations; the KML keeps the full names.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    recs = []
    for rec in sorted(best.values(), key=lambda r: r["name"].lower()):
        rows = prof.get(rec["name"], [])
        a = acc.get(rec["name"].lower())
        recs.append(dict(
            name=rec["name"], source=rec["src"],
            ward=(rows[0]["ward"] if rows else (a["ward"] if a else "")),
            zone=(rows[0]["zone"] if rows else (a["zone"] if a else "")),
            pop=(sum(r["population"] for r in rows) if rows else None),
            hh_prof=(sum(r["households"] for r in rows) if rows else None),
            hh_hhs=(int(a["households"]) if a else None),
            access=(a["access_class"] if a else ""),
            road_km=(float(a["road_km"]) if a and a["road_km"] else None),
            prof_name=", ".join(r["village"] for r in rows) if rows else "",
            geometry=Point(rec["lon"], rec["lat"])))
    gdf = gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:4326")

    OUT_SHP.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT_SHP / "mca_villages.shp")

    # GPX carries only a name and a description per waypoint, so the numbers
    # are folded into the description rather than lost.
    g = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<gpx version="1.1" creator="MCA_Tracks" '
         'xmlns="http://www.topografix.com/GPX/1/1">']
    for r in recs:
        desc = "; ".join(filter(None, [
            f'{r["pop"]:,} people' if r["pop"] else "",
            f'{r["hh_prof"]} households (ward profile)' if r["hh_prof"] else "",
            f'{r["hh_hhs"]} households (HHS)' if r["hh_hhs"] else "",
            f'ward {r["ward"]}' if r["ward"] else "",
            f'zone {r["zone"]}' if r["zone"] else "",
            r["access"], f'position: {r["source"]}']))
        g.append(f'  <wpt lat="{r["geometry"].y:.6f}" lon="{r["geometry"].x:.6f}">'
                 f'<name>{escape(r["name"])}</name>'
                 f'<desc>{escape(desc)}</desc></wpt>')
    g.append('</gpx>')
    OUT_GPX.write_text("\n".join(g) + "\n")
    return len(recs)


def main():
    best = collect()
    acc, notes = access_rows(), status_notes()

    # The Afore LLG Ward Profile population, joined on. One mapped place can
    # carry several profile rows - Kawowoki 1 and Kawowoki 2 are both our one
    # Kawowoki - so they are summed, never picked between.
    from ward_profile import match_to_mapped
    prof, unmatched = match_to_mapped(best, load_places(), load_aliases(),
                                      candidates, best_tier)

    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         '<name>Managalas - villages and hamlets we have positions for</name>',
         '<description><![CDATA[Folders are sources, strongest first. Where a '
         'name appears in more than one source the best-sourced position is '
         'kept and the rest dropped.]]></description>']
    for src, _title, colour, _why in TIERS:
        sid = src.replace(" ", "_").replace("-", "_")
        L.append(f'<Style id="{sid}"><IconStyle><color>{colour}</color>'
                 f'<scale>1.0</scale><Icon><href>http://maps.google.com/mapfiles/'
                 f'kml/paddle/wht-circle.png</href></Icon></IconStyle>'
                 f'<LabelStyle><scale>0.8</scale></LabelStyle></Style>')

    total = 0
    for src, title, _colour, why in TIERS:
        group = sorted((r for r in best.values() if r["src"] == src),
                       key=lambda r: r["name"].lower())
        if not group:
            continue
        total += len(group)
        L.append(f'  <Folder><name>{escape(title)} ({len(group)})</name>'
                 f'<description><![CDATA[{escape(why)}]]></description>'
                 f'<open>0</open>')
        L.extend(pin(r, acc, notes, prof) for r in group)
        L.append('  </Folder>')

    L.append('</Document></kml>')
    OUT.write_text("\n".join(L) + "\n")

    n = write_gis(best, acc, prof)
    print(f"wrote {OUT}")
    print(f"       {OUT_SHP / 'mca_villages.shp'}")
    print(f"       {OUT_GPX}")
    print(f"  {total} places, {n} rows in the GIS files")
    pop = sum(r["population"] for rows in prof.values() for r in rows)
    print(f"  population joined: {pop:,} across {len(prof)} places; "
          f"{len(unmatched)} profile villages have no position")
    for src, title, *_ in TIERS:
        n = sum(1 for r in best.values() if r["src"] == src)
        if n:
            print(f"    {n:4d}  {title}")


if __name__ == "__main__":
    main()
