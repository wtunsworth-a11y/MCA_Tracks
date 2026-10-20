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
    load_places, load_placed, load_aliases,
)

ROOT = Path(__file__).resolve().parent.parent
ACCESS = ROOT / "outputs" / "access" / "mca_village_access.csv"
WAYPOINTS = ROOT / "data" / "reference" / "waypoints_mca.csv"
STATUS = ROOT / "data" / "reference" / "village_status.csv"
OUT = ROOT / "outputs" / "access" / "mca_villages.kml"

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

    for key, rec in load_placed().items():
        offer(rec["name"], rec["lon"], rec["lat"], "placed by the team",
              rec.get("note", ""))

    for written, al in load_aliases().items():
        if al["lon"] is not None and al["to"]:
            offer(al["to"], al["lon"], al["lat"], "field evidence", al["note"])

    for name, cands in load_places().items():
        if "/" in name:
            continue
        for c in cands:
            offer(name, c["lon"], c["lat"], c.get("src", "GPS-inferred"),
                  c.get("note", ""))

    for w in waypoint_places():
        offer(w["name"], w["lon"], w["lat"], "waypoint file", w["note"])

    return best


def pin(rec, acc, notes):
    bits = []
    a = acc.get(rec["name"].lower())
    if a:
        bits.append(f'<b>{a["households"]} households</b>, zone {a["zone"]}, '
                    f'ward {a["ward"]}')
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
    return (f'    <Placemark><name>{escape(rec["name"])}</name>'
            f'<styleUrl>#{rec["src"].replace(" ", "_").replace("-", "_")}</styleUrl>'
            f'<description><![CDATA[{body}]]></description>'
            f'<Point><coordinates>{rec["lon"]:.6f},{rec["lat"]:.6f},0</coordinates>'
            f'</Point></Placemark>')


def main():
    best = collect()
    acc, notes = access_rows(), status_notes()

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
        L.extend(pin(r, acc, notes) for r in group)
        L.append('  </Folder>')

    L.append('</Document></kml>')
    OUT.write_text("\n".join(L) + "\n")

    print(f"wrote {OUT}")
    print(f"  {total} places")
    for src, title, *_ in TIERS:
        n = sum(1 for r in best.values() if r["src"] == src)
        if n:
            print(f"    {n:4d}  {title}")


if __name__ == "__main__":
    main()
