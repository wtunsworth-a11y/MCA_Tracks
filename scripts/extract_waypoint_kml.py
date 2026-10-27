"""Turn a Locus waypoint doc.kml into a plain CSV, leaving the photos in Drive.

    python3 scripts/extract_waypoint_kml.py <doc.kml> <out.csv>

The KMZ exports Russell uploads are almost entirely JPEG - 1.28 GB of archive
around 375 KB of placemarks - so only doc.kml is ever fetched, by ranged
request (scripts/fetch_kmz_member.py). THE PHOTOS STAY IN GOOGLE DRIVE. They
are many times GitHub's blob limit and they show identifiable people and
precise settlement locations.

What is kept, per placemark:

  name        as recorded in the field, with the capture timestamp split off
  recorded    that timestamp
  lon lat ele
  accuracy_m  Locus writes it into the description table
  note        what the recorder TYPED, which is the part no coordinate can
              replace - "Non-operational. Now covered in tall kunai grasses"
  photos      how many images hang off the point, so it is possible to tell
              what is still in Drive without opening the archive again

Nothing is renamed or reconciled. Names come across exactly as recorded, so
that the reconciliation against our own places stays somewhere it can be
reviewed rather than buried in an extraction.
"""
from pathlib import Path
import csv
import html
import re
import sys
import xml.etree.ElementTree as ET

NS = {"k": "http://www.opengis.net/kml/2.2",
      "lc": "https://www.locusmap.app"}

# Locus wraps whatever the recorder typed in these markers. Everything else in
# the description is a generated table of altitude, speed and azimuth.
USER = re.compile(r"<!--\s*desc_user:start\s*-->(.*?)<!--\s*desc_user:end\s*-->",
                  re.S)
STAMP = re.compile(r"\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\s*$")
ACC = re.compile(r"Accuracy</b></small></td><td[^>]*>([\d.]+)\s*m", re.I)


def text(el, path):
    found = el.find(path, NS)
    return (found.text or "").strip() if found is not None else ""


def note_of(desc):
    m = USER.search(desc or "")
    if not m:
        return ""
    # Strip the markup Locus leaves around the typed text.
    plain = re.sub(r"<[^>]+>", " ", m.group(1))
    return " ".join(html.unescape(plain).split())


def main(src, dest):
    root = ET.parse(src).getroot()
    rows = []
    for pm in root.findall(".//k:Placemark", NS):
        coords = pm.find(".//k:coordinates", NS)
        if coords is None or not (coords.text or "").strip():
            continue
        parts = coords.text.strip().split(",")
        lon, lat = float(parts[0]), float(parts[1])
        ele = float(parts[2]) if len(parts) > 2 and parts[2] else ""
        raw = text(pm, "k:name")
        stamp = STAMP.search(raw)
        desc = text(pm, "k:description")
        acc = ACC.search(desc or "")
        rows.append({
            "name": STAMP.sub("", raw).strip(),
            "recorded": stamp.group(1).replace(" ", "T") if stamp else "",
            "lon": f"{lon:.7f}",
            "lat": f"{lat:.7f}",
            "ele_m": f"{ele:.1f}" if ele != "" else "",
            "accuracy_m": acc.group(1) if acc else "",
            "note": note_of(desc),
            "photos": len(pm.findall(".//lc:attachment", NS)),
        })

    rows.sort(key=lambda r: (r["name"].lower(), r["recorded"]))
    header = Path(__file__).with_name("_waypoint_header.txt")
    with open(dest, "w", newline="") as fh:
        if header.exists():
            fh.write(header.read_text())
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    noted = sum(1 for r in rows if r["note"])
    pics = sum(r["photos"] for r in rows)
    print(f"wrote {dest}")
    print(f"  {len(rows)} waypoints, {noted} carrying a typed note, "
          f"{pics} photos left in Drive")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
