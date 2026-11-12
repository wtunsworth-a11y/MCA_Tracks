"""Check every track whose filename says where it went, both ways round.

    python3 scripts/audit_track_direction.py

Will, 12 Nov 2026: "This will happen all the time. You should be flexible
enough to look at a file both ways before making raising it with me."

He is right, and the cost of not doing it was real. 'Kaura_to_Koeno' ENDS 43 m
from Kaura Elementary School and STARTS 0.40 km from Koeno - it is the walk
from Koeno to Kaura, named the other way. Reading only the end put Koeno
3.4 km from itself and made one village look like two.

So a filename of the form "A to B" is treated as a claim about the two ENDS of
the track, not about their order. For each file we score both orientations:

    forward  = dist(start, A) + dist(end, B)
    reversed = dist(start, B) + dist(end, A)

and report the file as REVERSED when the reversed reading is substantially
better. A file where both readings are poor is reported as UNPLACED instead -
usually one of the two names has no position yet, which is worth knowing on its
own and is how Koeno, Tahama, Anatua and Awaru were found missing.
"""
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_access import haversine_km as km  # noqa: E402

RAW = ROOT / "data" / "raw"
# A reversed reading must beat the forward one by at least this much, in km,
# before it is worth raising. Below it the track is simply short or circular.
MARGIN_KM = 0.5
# Beyond this from BOTH names in BOTH orientations the filename cannot be
# checked at all - a missing position, not a direction problem.
UNPLACED_KM = 2.5

STOP = re.compile(
    r"\b(track|tracks|record|records|recording|trek|trail|road|roads|main|highway|"
    r"short|cut|aka|seven|steps|village|station|mission|ground|junction|site|old|"
    r"new|to|and|the|of|in|at|from|via|then|back|primary|elementary|high|school|"
    r"church|anglican|renewal|revival|centre|center|aid|post|airstrip|feeder|"
    r"bush|treck|connects|davids|david|jajibas|russell|muraba|mca|zone|coordinates|"
    r"waypoints|way|points|what|do|go|where)\b", re.I)


def gazetteer():
    """name -> (lon, lat), from every source that carries a position."""
    import pandas as pd
    out, alias = {}, {}

    fp = ROOT / "data" / "reference" / "village_footprints.geojson"
    if fp.exists():
        gj = json.loads(fp.read_text())
        for f in gj["features"]:
            from shapely.geometry import shape
            c = shape(f["geometry"]).centroid
            # "Sila 2 / Sakarina / Sila 1" and "Kawowoki 1 / Kawowoki 2" name
            # several places in one polygon; index each of them.
            for part in re.split(r"\s*/\s*", f["properties"]["village"]):
                part = re.sub(r"\(.*?\)", "", part).strip()
                if not part:
                    continue
                out.setdefault(norm(part), (c.x, c.y))
                # "Sila 2 / Sakarina / Sila 1" indexes sila1 and sila2, and a
                # filename saying plain "Sila" then matched neither, which
                # silently dropped four Sila Junction tracks from the check.
                bare = re.sub(r"\s*\d+$", "", part).strip()
                if bare and bare != part:
                    out.setdefault(norm(bare), (c.x, c.y))

    for fn, namecol in (("place_aliases.csv", "resolved_to"),
                        ("placed_by_team.csv", "place")):
        p = ROOT / "data" / "reference" / fn
        if not p.exists():
            continue
        for r in pd.read_csv(p, comment="#").itertuples():
            nm = str(getattr(r, namecol, "") or "").strip()
            lon, lat = getattr(r, "lon", None), getattr(r, "lat", None)
            if nm and pd.notna(lon) and pd.notna(lat):
                out.setdefault(norm(nm), (float(lon), float(lat)))
            if fn == "place_aliases.csv":
                aw = str(getattr(r, "as_written", "") or "").strip()
                if aw and nm:
                    alias[norm(aw)] = norm(nm)

    v = pd.read_csv(ROOT / "data" / "MCA_Village_Locations.csv")
    for r in v.itertuples():
        out.setdefault(norm(str(r.vil_name)), (float(r.lon), float(r.lat)))
    return out, alias


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def resolve(token, gaz, alias):
    """A place name from a filename -> a position, or None. No loose substrings.

    Matching "Umbuara" to "Bua" because one contains the other put two villages
    18 km apart, so containment is not used: exact, then alias, then a high-cutoff
    close match.
    """
    k = norm(token)
    if not k or len(k) < 3:
        return None
    k = alias.get(k, k)
    if k in gaz:
        return gaz[k]
    near = difflib.get_close_matches(k, list(gaz), n=1, cutoff=0.86)
    return gaz[near[0]] if near else None


def ends(path):
    t = path.read_text(errors="replace")
    pts = []
    for b in re.findall(r"<coordinates>(.*?)</coordinates>", t, re.S):
        for tok in b.split():
            try:
                lon, lat, *_ = tok.split(",")
                pts.append((float(lon), float(lat)))
            except ValueError:
                pass
    if not pts:
        pts = [(float(a), float(b)) for b, a in
               re.findall(r'lat="([-\d.]+)"\s+lon="([-\d.]+)"', t)]
    return (pts[0], pts[-1]) if len(pts) >= 2 else None


def names_from(stem):
    """The place names a filename claims, in the order written."""
    s = re.sub(r"\d{4}-\d{2}-\d{2}[_ ]?\d{0,2}-?\d{0,2}", " ", stem)
    s = re.sub(r"[_,]+", " ", s)
    parts = re.split(r"\bto\b", s, flags=re.I)
    if len(parts) < 2:
        return None
    out = []
    for p in parts:
        p = STOP.sub(" ", p)
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’]+", p) if len(w) > 2]
        if words:
            out.append(words[0])
    return out if len(out) >= 2 else None


def main():
    gaz, alias = gazetteer()
    rev, unplaced, ok, skipped = [], [], 0, 0
    for p in sorted(RAW.iterdir()):
        if p.suffix.lower() not in (".kml", ".gpx"):
            continue
        nm = names_from(p.stem)
        if not nm:
            skipped += 1
            continue
        e = ends(p)
        if not e:
            skipped += 1
            continue
        start, end = e
        a, b = resolve(nm[0], gaz, alias), resolve(nm[-1], gaz, alias)
        if not a or not b:
            unplaced.append((p.name, nm[0] if not a else nm[-1]))
            continue
        fwd = km(*start, *a) + km(*end, *b)
        bwd = km(*start, *b) + km(*end, *a)
        if bwd + MARGIN_KM < fwd and bwd / 2 < UNPLACED_KM:
            rev.append((p.name, nm[0], nm[-1], fwd, bwd))
        elif min(fwd, bwd) / 2 > UNPLACED_KM:
            unplaced.append((p.name, f"{nm[0]}/{nm[-1]} both far"))
        else:
            ok += 1

    print(f"checked {ok + len(rev) + len(unplaced)} directional tracks "
          f"({skipped} filenames carry no 'A to B')\n")
    print(f"NAMED BACKWARDS — the track runs the other way ({len(rev)}):")
    for n, a, b, fwd, bwd in sorted(rev, key=lambda r: r[3] - r[4], reverse=True):
        print(f"  {n[:66]:68s}")
        print(f"      says {a} -> {b}; as written the ends are {fwd:.2f} km out, "
              f"reversed {bwd:.2f} km")
    if not rev:
        print("  none")
    print(f"\nCANNOT BE CHECKED — a name with no position ({len(unplaced)}):")
    for n, why in sorted(unplaced):
        print(f"  {n[:66]:68s} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
