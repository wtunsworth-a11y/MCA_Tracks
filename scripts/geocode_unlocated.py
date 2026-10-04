"""Look up the places we cannot find in the public gazetteers now reachable.

outputs/access/geocode_candidates.csv

Queries Nominatim (OpenStreetMap) and the GeoNames search page for every place
the cross-reference could not position, and reports the candidates with enough
context to accept or reject each one. It writes nothing into
data/reference/place_aliases.csv: a hit is a candidate, and a candidate becomes
a position only when a person has looked at it.

That caution is not theoretical. GeoNames' only "Itokama" in Papua New Guinea is
an airport at 147.30 in Central Province - 106 km from the Itokama this project
is about. Accepting gazetteer hits on name alone would have moved a village
across the country. So every candidate is reported with

  - its administrative division and feature class, which is what exposes that
    kind of error, and
  - its distance from the anchor the KML already guessed for the place, which is
    derived from the neighbours the team's own list names beside it.

Nominatim's usage policy allows one request a second from an identified client;
both are honoured, and results are cached in data/reference/geocode_cache.json
so a re-run costs nothing.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import candidates, load_aliases, load_places  # noqa: E402
from make_unlocated_kml import anchor_all, canonical  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
OUT = ROOT / "outputs" / "access"
CACHE = REF / "geocode_cache.json"

UA = "MCA-Tracks/1.0 (Managalas Conservation Area mapping; wtunsworth@gmail.com)"
PAUSE_S = 1.1          # Nominatim asks for no more than one request a second
# Anything further than this from the anchor its own route implies is reported
# but marked suspect - that is the Itokama-airport failure mode.
SUSPECT_KM = 30.0


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def nominatim(name, cache):
    key = f"nominatim:{name}"
    if key in cache:
        return cache[key]
    q = urllib.parse.urlencode({"q": name, "countrycodes": "pg",
                                "format": "jsonv2", "limit": "10",
                                "accept-language": "en"})
    try:
        rows = json.loads(get(f"https://nominatim.openstreetmap.org/search?{q}"))
    except Exception as e:                                  # noqa: BLE001
        print(f"  nominatim {name}: {e}")
        return []
    out = [dict(source="OSM/Nominatim", name=r.get("name") or name,
                lat=float(r["lat"]), lon=float(r["lon"]),
                kind=r.get("type", ""), where=r.get("display_name", ""))
           for r in rows]
    cache[key] = out
    time.sleep(PAUSE_S)
    return out


def geonames(name, cache):
    key = f"geonames:{name}"
    if key in cache:
        return cache[key]
    q = urllib.parse.urlencode({"q": name, "country": "PG"})
    try:
        html = get(f"https://www.geonames.org/search.html?{q}")
    except Exception as e:                                  # noqa: BLE001
        print(f"  geonames {name}: {e}")
        return []
    out = []
    # One table row per hit; the coordinates are in a hidden span pair and the
    # division and feature class in the cells after the name.
    for row in re.findall(r"<tr><td><small>\d+</small>.*?</tr>", html, re.S):
        lat = re.search(r'class="latitude">([-\d.]+)<', row)
        lon = re.search(r'class="longitude">([-\d.]+)<', row)
        nm = re.search(r'<a href="/\d+/[^"]+">([^<]+)</a>', row)
        if not (lat and lon):
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        plain = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in cells]
        out.append(dict(source="GeoNames", name=(nm.group(1) if nm else name),
                        lat=float(lat.group(1)), lon=float(lon.group(1)),
                        kind=plain[3] if len(plain) > 3 else "",
                        where=plain[2] if len(plain) > 2 else ""))
    cache[key] = out
    time.sleep(0.4)
    return out


def km(lon1, lat1, lon2, lat2):
    lat = np.radians((lat1 + lat2) / 2)
    return float(np.hypot((lon1 - lon2) * 110.574 * np.cos(lat),
                          (lat1 - lat2) * 110.574))


def main():
    planned = pd.read_csv(REF / "planned_tracks.csv", comment="#")
    places = load_places()
    aliases = load_aliases()
    chk = pd.read_csv(OUT / "track_checklist.csv")

    unl = {}
    for _, r in chk[chk["status"] == "unlocated"].iterrows():
        for w in str(r["detail"]).replace("no position for ", "").split(" and "):
            unl.setdefault(canonical(w, aliases), set()).add(r["route_id"])

    fixed, _hops = anchor_all(set(unl), planned, places, aliases)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    rows = []
    for nm in sorted(unl):
        # Numbered feeder-road stubs and a person's house are not gazetteer
        # entries; asking wastes a request and clutters the report.
        if re.fullmatch(r"Road \d+", nm) or "'s place" in nm:
            continue
        print(f"looking up {nm} ...")
        hits = nominatim(nm, cache) + geonames(nm, cache)
        anchor = fixed.get(nm)
        for h in hits:
            d = (km(h["lon"], h["lat"], anchor[0], anchor[1])
                 if anchor else float("nan"))
            rows.append(dict(
                place=nm, appears_in=", ".join(sorted(unl[nm])),
                hit_name=h["name"], source=h["source"], feature=h["kind"],
                lat=round(h["lat"], 5), lon=round(h["lon"], 5),
                km_from_anchor=None if np.isnan(d) else round(d, 1),
                verdict=("no anchor to judge against" if np.isnan(d)
                         else "plausible" if d <= SUSPECT_KM
                         else "SUSPECT - far from where the route implies"),
                division=h["where"]))
        if not hits:
            rows.append(dict(place=nm, appears_in=", ".join(sorted(unl[nm])),
                             hit_name="", source="", feature="", lat=None,
                             lon=None, km_from_anchor=None,
                             verdict="not in either gazetteer", division=""))

    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "geocode_candidates.csv", index=False)

    found = df[df["verdict"] == "plausible"]
    print()
    print(f"{df['place'].nunique()} places queried")
    print(f"  {found['place'].nunique()} with a plausible candidate")
    print(f"  {df[df.verdict.str.startswith('SUSPECT')]['place'].nunique()} "
          f"with hits only far from where the route implies")
    print(f"  {df[df.verdict == 'not in either gazetteer']['place'].nunique()} "
          f"in neither gazetteer")
    if not found.empty:
        print()
        print(found[["place", "hit_name", "source", "feature", "lat", "lon",
                     "km_from_anchor"]].to_string(index=False))
    print(f"\nwrote {OUT/'geocode_candidates.csv'} - review before trusting any of it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
