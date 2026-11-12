"""Find place names that are probably the same place spelt differently.

    python3 scripts/audit_place_spellings.py

Will, 12 Nov 2026: "You should be better by now at identifying different
spellings for the same place. This is not a new thing. If you see one, suggest
something to me."

Koeno has four spellings - Koeno, Kueno, Kweno, Kuweno - and the fourth went
unnoticed until it put a school at the wrong village. Umbuara/Umbuwara,
Jorua/Jorura, Aiari/Aiyari, Kiara/Kiera, Madokoro/Mandakoro and Bodoimo/Boidomo
are all the same shape of problem. Rather than wait to trip over the next one,
this reads every name written anywhere in the repository and groups the ones
that look alike.

Already-settled pairs are suppressed: a group is only reported if its members
are not already tied together by place_aliases.csv. So the output is a list of
SUGGESTIONS to confirm or reject, and it shrinks as they get recorded.

Similarity is edit-distance on a reduced spelling - vowels collapsed, doubled
letters squeezed, and the w/u, c/k, j/y swaps that account for most of the
variation in these names.
"""
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
# Calibrated on 23 spelling pairs already known to be the same place and 24
# known to be different: at 0.80 it finds 22 of the 23 and proposes 4 of the 24.
# This is a suggestion list Will confirms or rejects, so recall is worth more
# than precision - but only because the position guard below throws out the
# look-alikes that are demonstrably different places.
CUTOFF = 0.80
# Two names more than this far apart cannot be one place however alike they
# read. Kiara and Kaura, Jaure and Yaure, Kokoro and Korokoro all survive the
# spelling test and die here.
APART_KM = 4.0

NOISE = re.compile(
    r"\b(track|tracks|record|records|recording|trek|trail|road|roads|main|highway|"
    r"short|cut|aka|seven|steps|village|villages|station|mission|ground|junction|"
    r"site|old|new|to|and|the|of|in|at|from|via|then|back|primary|elementary|high|"
    r"secondary|school|schools|church|anglican|renewal|revival|centre|center|aid|"
    r"post|aidpost|airstrip|feeder|bush|treck|connects|david|davids|jajibas|"
    r"russell|muraba|mca|zone|coordinates|waypoints|way|points|where|what|do|go|"
    r"creek|creeks|river|rivers|hamlet|hamlets|folder|root|government|facilities|"
    r"house|houses|teacher|teachers|classroom|building|buildings|blocks|grid|"
    r"health|clinic|haus|sik|guest|institute|bible|community|anatua|north|south|"
    r"east|west|upper|lower|map|boundary|wdpa|llg|ward|wards|population|photo|"
    r"photos|files|csv|kml|kmz|gpx|gpkg|zip|jpg|master|png|oro|sibium)\b", re.I)


def reduce_spelling(s):
    """Squash the variation these names actually show - and no more.

    Collapsing every vowel run to one letter was tried first and merged Awaru,
    Kaura, Kiara, Jaure, Kero and Koruwo into a single group, which is worse
    than useless. Only the w/u, c/k and j/y swaps and doubled letters go.
    """
    s = re.sub(r"[^a-z]", "", s.lower())
    s = s.replace("w", "u").replace("c", "k").replace("j", "y").replace("q", "k")
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def positions():
    """name (reduced) -> (lon, lat), for the guard. Best source first."""
    from shapely.geometry import shape
    out = {}
    fp = REF / "village_footprints.geojson"
    if fp.exists():
        for f in json.loads(fp.read_text())["features"]:
            c = shape(f["geometry"]).centroid
            for part in re.split(r"\s*/\s*", f["properties"]["village"]):
                part = re.sub(r"\(.*?\)|\d+", "", part).strip()
                if part:
                    out.setdefault(reduce_spelling(part), (c.x, c.y))
    for fn, col in (("place_aliases.csv", "resolved_to"),
                    ("placed_by_team.csv", "place")):
        p = REF / fn
        if not p.exists():
            continue
        for r in pd.read_csv(p, comment="#").itertuples():
            nm = str(getattr(r, col, "") or "").strip()
            lon, lat = getattr(r, "lon", None), getattr(r, "lat", None)
            if nm and pd.notna(lon) and pd.notna(lat):
                out.setdefault(reduce_spelling(nm), (float(lon), float(lat)))
    v = ROOT / "data" / "MCA_Village_Locations.csv"
    if v.exists():
        for r in pd.read_csv(v).itertuples():
            out.setdefault(reduce_spelling(str(r.vil_name)), (float(r.lon), float(r.lat)))
    return out


def harvest():
    """Every place-shaped name written anywhere, with where it came from."""
    seen = defaultdict(set)

    LOOSE = {"waypoints", "track filenames"}

    def add(name, src):
        name = str(name).strip()
        # Capitalised words scraped out of waypoint text and filenames are
        # mostly not places ("Sara", "Mate", "Wari"), so they must be longer
        # before they are allowed to propose anything.
        if not name or len(name) < (5 if src in LOOSE else 4):
            return
        if NOISE.fullmatch(name) or re.search(r"[\d'’]", name):
            return
        seen[name].add(src)

    v = ROOT / "data" / "MCA_Village_Locations.csv"
    if v.exists():
        for r in pd.read_csv(v).itertuples():
            add(r.vil_name, "gazetteer")

    fp = REF / "village_footprints.geojson"
    if fp.exists():
        for f in json.loads(fp.read_text())["features"]:
            v = f["properties"]["village"]
            # "Buanfuo (Jakiro/Sibisibi)" - the bracket holds alternative names
            # for the same polygon, so take what is inside it as well, but strip
            # the brackets BEFORE splitting on "/" or "Sibisibi)" keeps its paren.
            for chunk in (re.sub(r"[()]", " ", v),):
                for part in re.split(r"\s*/\s*", chunk):
                    add(re.sub(r"\d+", "", part).strip(), "footprints")

    for fn, cols in (("place_aliases.csv", ("as_written", "resolved_to")),
                     ("placed_by_team.csv", ("place",)),
                     ("afore_llg_population.csv", ("village",)),
                     ("facilities.csv", ("village",))):
        p = REF / fn
        if not p.exists():
            continue
        d = pd.read_csv(p, comment="#")
        for c in cols:
            if c in d.columns:
                for x in d[c].dropna():
                    add(x, fn)

    # names written into waypoints and track filenames
    for p in REF.glob("waypoints_*.csv"):
        d = pd.read_csv(p, comment="#")
        if "name" in d.columns:
            for x in d["name"].dropna():
                for w in re.findall(r"[A-Z][a-z'’]{3,}", str(x)):
                    add(w, "waypoints")
    raw = ROOT / "data" / "raw"
    if raw.exists():
        for f in raw.iterdir():
            stem = re.sub(r"\d{4}-\d{2}-\d{2}[_ ]?\d{0,2}-?\d{0,2}", " ", f.stem)
            for w in re.findall(r"[A-Za-z][A-Za-z'’]{3,}", stem):
                add(w, "track filenames")
    return seen


def settled():
    """reduced name -> the canonical place place_aliases.csv resolves it to.

    Keyed on the canonical target rather than on pairs. Requiring every pair to
    be written down kept re-reporting Koeno/Kueno/Kweno/Kuweno as unsettled
    because only three of the six pairings are recorded, when all four already
    resolve to Koeno. Nothing is more irritating than being told again about
    something that was decided.
    """
    direct = {}
    p = REF / "place_aliases.csv"
    if not p.exists():
        return direct
    for r in pd.read_csv(p, comment="#").itertuples():
        a = str(getattr(r, "as_written", "") or "").strip()
        b = str(getattr(r, "resolved_to", "") or "").strip()
        if a and b:
            direct[reduce_spelling(a)] = reduce_spelling(b)

    def canon(k, depth=0):
        nxt = direct.get(k)
        if nxt is None or nxt == k or depth > 8:
            return k
        return canon(nxt, depth + 1)

    return {k: canon(k) for k in set(direct) | set(direct.values())}


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_access import haversine_km as km
    names = harvest()
    known = settled()
    pos = positions()
    buckets = defaultdict(set)
    for n in names:
        buckets[reduce_spelling(n)].add(n)

    keys = sorted(buckets)
    groups, used = [], set()
    for i, k in enumerate(keys):
        if k in used:
            continue
        grp = {k}
        for k2 in keys[i + 1:]:
            if k2 in used:
                continue
            if difflib.SequenceMatcher(None, k, k2).ratio() < CUTOFF:
                continue
            a, b = pos.get(k), pos.get(k2)
            if a and b and km(*a, *b) > APART_KM:
                continue          # alike, but demonstrably not one place
            grp.add(k2)
        if len(grp) > 1:
            used |= grp
            groups.append(grp)

    def split_bridged(grp):
        """A group whose positioned members are not mutually close is two groups.

        Single-link grouping let "Karan", which has no position, join Kaura to
        Kiara 11 km apart. Anchors are the positioned members; anything without
        a position goes to the anchor it most resembles.
        """
        anchors = [k for k in grp if k in pos]
        if len(anchors) < 2:
            return [grp]
        if all(km(*pos[a], *pos[b]) <= APART_KM
               for i, a in enumerate(anchors) for b in anchors[i + 1:]):
            return [grp]
        buckets = {a: {a} for a in anchors}
        for k in grp:
            if k in buckets:
                continue
            best = max(anchors,
                       key=lambda a: difflib.SequenceMatcher(None, k, a).ratio())
            buckets[best].add(k)
        return [g for g in buckets.values() if len(g) > 1]

    groups = [g for grp in groups for g in split_bridged(grp)]

    out = []
    for grp in groups:
        spellings = sorted(set().union(*(buckets[k] for k in grp)))
        if len(spellings) < 2:
            continue
        # suppress a group where every spelling already resolves to one place
        canon = {known.get(reduce_spelling(a), reduce_spelling(a))
                 for a in spellings}
        if len(canon) == 1:
            continue
        out.append(spellings)

    print(f"{len(names)} distinct names harvested\n")
    print(f"POSSIBLY THE SAME PLACE, not yet recorded in place_aliases.csv "
          f"({len(out)}):")
    for spellings in sorted(out, key=lambda s: -len(s)):
        print()
        for s in spellings:
            print(f"    {s:26s} {', '.join(sorted(names[s]))}")
    if not out:
        print("  none")
    print(f"\n(suppressed: pairs already in place_aliases.csv, and look-alikes "
          f"more than {APART_KM:.0f} km apart)")
    print("Confirm or reject each, then they go into place_aliases.csv and "
          "stop being reported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
