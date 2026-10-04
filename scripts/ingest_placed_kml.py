"""Read back a KML or KMZ the team has placed pins in: positions and comments.

Usage: python3 scripts/ingest_placed_kml.py <file.kmz|file.kml>

Writes data/reference/placed_by_team.csv, which the cross-reference reads ahead
of every other source: a position someone put on the map from knowledge of the
ground outranks a gazetteer hit, and a gazetteer hit outranks our own inference.

A pin is only taken as placed if it has MOVED from the guess it was sent out at,
by more than MOVED_M. A pin left sitting on its guess says nothing - the guess
was ours, not theirs - and recording it as a field position would launder our
own arithmetic into evidence.

EVERY folder is diffed, not just the editable one. The reference folders are
labelled "do not move", and reading only the editable folder on the first batch
missed five corrections the team had made in them - including the real position
of Suari, 10.5 km from where the gazetteer had it. A village corrected in the
reference folder is the team fixing our data, which is worth more than a pin
placed in the folder we asked them to use.

The file sent out may not be the latest one: pins get placed over days while the
checklist moves on. So the comparison is against whichever version's anchors
match, found by trying the current pin file and then its git history.

It also extracts every comment typed into a pin's description, to
data/reference/field_comments.csv. The first batch came back with 17 of them and
they were nearly missed by reading only the coordinates - several were
corrections to our own reference data ("Suari - this was WRONG", "Ondoro is
roadside", "no village here"), which no amount of looking at the geometry would
have found. Comments on the locked reference folders are collected too, and
those are the most valuable kind: they are the team marking our errors.
"""

import subprocess
import sys
import warnings
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
OUT = ROOT / "outputs" / "access"
SENT = OUT / "unlocated_places.kml"
K = "{http://www.opengis.net/kml/2.2}"

# A pin nudged by a few metres while panning the map has not been placed. 50 m
# is below the width of any village and above any accidental drag.
MOVED_M = 50.0


def read_all(source):
    """Placemark name -> (folder, lon, lat, description) for every pin."""
    root = _root(source)
    out = {}

    def walk(el, folder=""):
        for ch in el:
            tag = ch.tag.replace(K, "")
            if tag in ("Folder", "Document"):
                nm = ch.find(K + "name")
                walk(ch, nm.text if nm is not None else folder)
            elif tag == "Placemark":
                nm = ch.find(K + "name")
                if nm is None:
                    continue
                pt = ch.find(K + "Point")
                d = ch.find(K + "description")
                lon = lat = None
                if pt is not None:
                    c = pt.find(K + "coordinates").text.strip().split(",")
                    lon, lat = float(c[0]), float(c[1])
                out[nm.text.strip()] = (folder, lon, lat,
                                        (d.text or "") if d is not None else "")

    walk(root)
    return out


def _root(source):
    if isinstance(source, bytes):
        return ET.fromstring(source)
    p = Path(source)
    if p.suffix.lower() == ".kmz":
        with zipfile.ZipFile(p) as z:
            name = next(n for n in z.namelist() if n.endswith(".kml"))
            return ET.fromstring(z.read(name))
    return ET.parse(p).getroot()


def read_pins(source, folder_must_contain="PLACE"):
    """Placemark name -> (lon, lat) for the pins in the editable folder."""
    root = _root(source)
    out = {}

    def walk(el, folder=""):
        for ch in el:
            tag = ch.tag.replace(K, "")
            if tag in ("Folder", "Document"):
                nm = ch.find(K + "name")
                walk(ch, nm.text if nm is not None else folder)
            elif tag == "Placemark":
                pt, nm = ch.find(K + "Point"), ch.find(K + "name")
                if pt is None or nm is None:
                    continue
                if folder_must_contain not in (folder or ""):
                    continue
                c = pt.find(K + "coordinates").text.strip().split(",")
                out[nm.text.strip()] = (float(c[0]), float(c[1]))

    walk(root)
    return out


def km(a, b):
    lat = np.radians((a[1] + b[1]) / 2)
    return float(np.hypot((a[0] - b[0]) * 110.574 * np.cos(lat),
                          (a[1] - b[1]) * 110.574))


def candidate_sent_versions():
    """The current pin file, then each earlier one from git, newest first."""
    if SENT.exists():
        yield "working tree", read_pins(SENT)
    rel = SENT.relative_to(ROOT)
    try:
        log = subprocess.run(["git", "log", "--format=%h", "--", str(rel)],
                             cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    except subprocess.CalledProcessError:
        return
    for sha in log:
        try:
            blob = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=ROOT,
                                  capture_output=True, check=True).stdout
            yield sha, read_pins(blob)
        except subprocess.CalledProcessError:
            continue


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    back = read_pins(argv[1])
    if not back:
        print("no pins found in the editable folder of that file")
        return 1

    # Match against the version whose pin names the returned file actually has.
    best, best_sha, best_overlap = None, None, -1
    for sha, sent in candidate_sent_versions():
        overlap = len(set(sent) & set(back))
        if overlap > best_overlap:
            best, best_sha, best_overlap = sent, sha, overlap
    sent = best or {}
    print(f"returned file has {len(back)} pins; comparing against the version "
          f"sent at {best_sha} ({best_overlap} names in common)")

    # Every folder, so a correction made in a reference folder is not lost.
    back_all = read_all(argv[1])
    sent_all = {}
    try:
        sent_all = read_all(subprocess.run(
            ["git", "show", f"{best_sha}:{SENT.relative_to(ROOT)}"], cwd=ROOT,
            capture_output=True, check=True).stdout)
    except Exception:                                       # noqa: BLE001
        sent_all = read_all(SENT) if SENT.exists() else {}

    rows, unmoved, new = [], [], []
    for nm, (folder, lon, lat, _d) in sorted(back_all.items()):
        if lon is None:
            continue
        editable = "PLACE" in (folder or "")
        if nm not in sent_all or sent_all[nm][1] is None:
            new.append(nm)
            rows.append(dict(place=nm, lon=round(lon, 5), lat=round(lat, 5),
                             moved_km="", note="pin added by the team"))
            continue
        d = km((lon, lat), (sent_all[nm][1], sent_all[nm][2]))
        if d * 1000 < MOVED_M:
            if editable:
                unmoved.append(nm)
            continue
        rows.append(dict(
            place=nm, lon=round(lon, 5), lat=round(lat, 5), moved_km=round(d, 2),
            note=(f"placed by the team, {d:.1f} km from the guess" if editable
                  else f"CORRECTION to our own position, moved {d:.1f} km "
                       f"in the reference folder")))

    df = pd.DataFrame(rows)
    path = REF / "placed_by_team.csv"
    header = (
        "# Positions the team placed by dragging pins in Google Earth.\n"
        "# Read AHEAD of the gazetteer and of our own inference: someone who\n"
        "# knows the ground outranks both. Written by\n"
        "# scripts/ingest_placed_kml.py; only pins that MOVED from the guess\n"
        "# they were sent out at are here, because a pin left on its guess is\n"
        "# our arithmetic and not their knowledge.\n")
    path.write_text(header + df.to_csv(index=False))

    print(f"\n{len(df)} placed:")
    for _, r in df.sort_values("place").iterrows():
        print(f"  {r['place']:<22} {r['lat']:.5f}, {r['lon']:.5f}   {r['note']}")
    corr = df[df["note"].str.startswith("CORRECTION")]
    if not corr.empty:
        print(f"\n{len(corr)} of those are corrections to positions WE held:")
        for _, r in corr.iterrows():
            print(f"  !! {r['place']:<20} moved {r['moved_km']} km")
    if unmoved:
        print(f"\n{len(unmoved)} left on the guess, so not taken as placed:")
        print("  " + ", ".join(unmoved))
    if new:
        print(f"\n{len(new)} pins the team added: " + ", ".join(new))

    # Where we had already found a position another way, say whether the two
    # agree. Disagreement is the interesting case and must not be silent.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cross_reference_tracks import candidates, load_aliases, load_places
    places, aliases = load_places(), load_aliases()
    checks = []
    for _, r in df.iterrows():
        cands = candidates(r["place"], places, aliases)
        if not cands:
            continue
        c = cands[0]
        checks.append((r["place"], km((r["lon"], r["lat"]), (c["lon"], c["lat"])),
                       c["src"]))
    if checks:
        print("\nagainst positions we already held:")
        for nm, d, src in sorted(checks, key=lambda x: x[1]):
            verdict = ("agrees" if d < 1.0 else "close" if d < 3.0
                       else "DISAGREES - check which is right")
            print(f"  {nm:<22} {d:6.2f} km from the {src} position — {verdict}")
    harvest_comments(argv[1], best_sha)
    print(f"\nwrote {path}")
    return 0


def harvest_comments(returned, sent_sha):
    """Pull out anything typed into a pin's description and keep all of it."""
    import re
    back = read_all(returned)
    try:
        sent = read_all(subprocess.run(
            ["git", "show", f"{sent_sha}:{SENT.relative_to(ROOT)}"], cwd=ROOT,
            capture_output=True, check=True).stdout)
    except Exception:                                       # noqa: BLE001
        sent = read_all(SENT) if SENT.exists() else {}

    def flat(h):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()

    rows = []
    for nm, (folder, _lon, _lat, desc) in sorted(back.items()):
        before, after = flat(sent.get(nm, ("", None, None, ""))[3]), flat(desc)
        if before == after:
            continue
        # Keep whatever is in the returned text and not in ours. Comments are
        # typed into the middle of the description we wrote, so a plain
        # difference is the reliable way to find them.
        import difflib
        added = [after[j1:j2] for tag, _i1, _i2, j1, j2
                 in difflib.SequenceMatcher(None, before, after).get_opcodes()
                 if tag in ("insert", "replace")]
        txt = " ".join(x.strip() for x in added if x.strip())
        if not txt:
            continue
        rows.append(dict(place=nm, folder=(folder or "").split("—")[0].strip(),
                         about=("our reference data" if "Known" in (folder or "")
                                or "Recorded" in (folder or "")
                                else "a place to be located"),
                         comment=txt))
    if not rows:
        print("\nno comments found in the returned file")
        return
    df = pd.DataFrame(rows)
    path = REF / "field_comments.csv"
    path.write_text(
        "# Comments the team typed into the pin descriptions, kept verbatim.\n"
        "# Written by scripts/ingest_placed_kml.py. Comments filed against the\n"
        "# locked reference folders are corrections to OUR data and matter most.\n"
        + df.to_csv(index=False))
    print(f"\n{len(df)} comments, kept in {path}:")
    for _, r in df.iterrows():
        mark = "!!" if r["about"] == "our reference data" else "  "
        print(f" {mark} {r['place']:<20} {r['comment'][:92]}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
