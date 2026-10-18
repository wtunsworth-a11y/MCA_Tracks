"""The waypoints that need a name, as pins someone local can label.

outputs/access/waypoints_to_name.kml

Sixteen of the 246 waypoints in the MCA file are water features recorded as
"Creek", "River", "Creek name unknown" or "Dry Creek (name unknown)". Every
village and hamlet is named; it is only the water that is blank.

That is not a survey problem. Russell is from Managalas and knows these
creeks - he just did not type the names in at the time. So this does not ask
anyone to walk anywhere: it puts the blank points on a map he can open on his
phone, see where they are, and name from memory in one sitting.

Two conflicts ride along in their own folder, for the same reason.

Mirrors make_unlocated_kml.py, which is how the unlocated villages were sent
out and came back placed.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import csv
import re

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "reference" / "waypoints_mca.csv"
OUT = ROOT / "outputs" / "access" / "waypoints_to_name.kml"

# A name that identifies nothing: a bare type word, or one that says so.
BLANK = re.compile(r"unknown|^\s*(river|creek|stream)\s*$", re.I)
# Points whose name describes where the track goes, not what the point is.
HEADING = re.compile(r"^\s*(trek|trail|alternate)\b", re.I)


def load():
    with SRC.open() as fh:
        return [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))]


def pin(name, lon, lat, desc, style):
    return (f"    <Placemark><name>{escape(name)}</name>"
            f"<styleUrl>#{style}</styleUrl>"
            f"<description><![CDATA[{desc}]]></description>"
            f"<Point><coordinates>{lon},{lat},0</coordinates></Point>"
            f"</Placemark>")


def coincident(rows, limit_m=25.0):
    """Different names sitting on the same spot - one of them is wrong."""
    out = []
    deg = limit_m / 111_320.0
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if abs(float(a["lat"]) - float(b["lat"])) > deg:
                continue
            if abs(float(a["lon"]) - float(b["lon"])) > deg:
                continue
            if a["name"].strip().lower() != b["name"].strip().lower():
                out.append((a, b))
    return out


def main():
    rows = load()
    blank = [r for r in rows if BLANK.search(r["name"])]
    clashes = coincident(rows)

    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         '<name>Managalas - waypoints that need a name</name>',
         '<Style id="blank"><IconStyle><color>ff2d8cff</color><scale>1.1</scale>'
         '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-blank.png</href>'
         '</Icon></IconStyle></Style>',
         '<Style id="clash"><IconStyle><color>ff3a3ab0</color><scale>1.1</scale>'
         '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/red-stars.png</href>'
         '</Icon></IconStyle></Style>',
         '<Style id="ref"><IconStyle><color>ff9c9a94</color><scale>0.7</scale>'
         '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png</href>'
         '</Icon></IconStyle></Style>']

    L.append(f'  <Folder><name>NAME THESE - {len(blank)} creeks and rivers'
             f'</name><open>1</open>')
    for r in blank:
        L.append(pin(r["name"], r["lon"], r["lat"],
                     f'Recorded {r["recorded"] or "date not kept"} as '
                     f'"{escape(r["name"])}".<br/><br/>'
                     'What is this water called? Type the name over the top of '
                     'this one. If it has no name, say so - that is an answer too.',
                     "blank"))
    L.append('  </Folder>')

    if clashes:
        L.append(f'  <Folder><name>TWO NAMES, ONE SPOT - {len(clashes)}'
                 f'</name><open>1</open>')
        for a, b in clashes:
            L.append(pin(f'{a["name"]} / {b["name"]}', a["lon"], a["lat"],
                         f'Two waypoints sit within 25 m of each other here, '
                         f'recorded as "{escape(a["name"])}" and '
                         f'"{escape(b["name"])}".<br/><br/>'
                         'Are these one place with two names, two things side by '
                         'side, or was one of them saved by mistake?',
                         "clash"))
        L.append('  </Folder>')

    named = [r for r in rows if r not in blank and not HEADING.match(r["name"])]
    L.append(f'  <Folder><name>Already named (for bearings only)</name>'
             f'<open>0</open><visibility>0</visibility>')
    for r in named:
        L.append(pin(r["name"], r["lon"], r["lat"],
                     f'{escape(r["name"])}<br/>recorded '
                     f'{r["recorded"] or "date not kept"}', "ref"))
    L.append('  </Folder>')
    L.append('</Document></kml>')

    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    print(f"  {len(blank)} to name, {len(clashes)} conflict(s), "
          f"{len(named)} shown for bearings")


if __name__ == "__main__":
    main()
