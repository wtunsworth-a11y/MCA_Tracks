"""The Ward Profile villages we have no position for, as pins to drag.

outputs/access/unmapped_villages.kml

The Afore LLG Ward Profiles list 79 villages. Reconciling them against
mca_villages.kml leaves 22 with no mapped position - 524 households and
3,007 people, about one person in seven.

Each pin starts near the middle of the villages we DO hold in the same ward,
so it opens somewhere in the right valley rather than in the sea. That start
point carries no information: the whole point is to drag it.

Same round trip that placed the unlocated track names: pins out, pins back,
positions read off the returned file.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import csv
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)
from make_villages_kml import collect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POP = ROOT / "data" / "reference" / "afore_llg_population.csv"
OUT = ROOT / "outputs" / "access" / "unmapped_villages.kml"


def rows():
    with POP.open() as fh:
        return [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))
                if r["village"] and not r["village"].startswith("Total")]


def variants(name):
    """The ways the Ward Profile writes a name that we might file differently."""
    yield name
    s = re.sub(r"\s*\b(village|station|govt station|government station)\b\s*$",
               "", name, flags=re.I).strip()
    if s and s != name:
        yield s
    m = re.match(r"(.+?)\s*[12]$", name)          # Anatua 1, Sila 2, Kawowoki 1
    if m:
        yield m.group(1).strip()
    for part in re.split(r"[/()]", name):         # Numba/Siurana, Buanfuo (Jakiro)
        part = part.strip()
        if part and part != name:
            yield part


def main():
    places, aliases = load_places(), load_aliases()
    mapped = collect()

    def canon(n):
        al = aliases.get(str(n).strip().lower())
        return al["to"] if al and al["to"] else n

    def known(name):
        for v in variants(name):
            if v.lower() in mapped:
                return mapped[v.lower()]
            hit = best_tier(candidates(v, places, aliases))
            if hit:
                c = canon(hit[0]["name"])
                if c.lower() in mapped:
                    return mapped[c.lower()]
        return None

    data = rows()
    unmapped = [r for r in data if not known(r["village"])]

    # Ward -> middle of the villages we hold in it, as a starting point only.
    by_ward = {}
    for r in data:
        hit = known(r["village"])
        if hit:
            by_ward.setdefault(r["ward"], []).append((hit["lon"], hit["lat"]))
    anchors = {w: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v))
               for w, v in by_ward.items()}
    fallback = (sum(a[0] for a in anchors.values()) / len(anchors),
                sum(a[1] for a in anchors.values()) / len(anchors))

    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         '<name>Managalas - Ward Profile villages with no position</name>',
         '<description><![CDATA[22 villages from the Afore LLG Ward Profiles '
         'that we cannot place. Every pin starts at the middle of its own '
         'ward and is in the wrong spot by design - drag it to where the '
         'village is. If a pin is really a village we already have under '
         'another name, say which and delete it.]]></description>',
         '<Style id="place"><IconStyle><color>ff2d8cff</color><scale>1.15</scale>'
         '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-blank.png'
         '</href></Icon></IconStyle></Style>',
         '<Style id="ref"><IconStyle><color>ff9c9a94</color><scale>0.7</scale>'
         '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
         '</href></Icon></IconStyle></Style>']

    # spread pins in a ring so a ward's several unknowns do not stack up
    per_ward = {}
    L.append(f'  <Folder><name>PLACE THESE - {len(unmapped)} villages</name>'
             f'<open>1</open>')
    for r in sorted(unmapped, key=lambda r: (r["ward"], r["village"])):
        lon, lat = anchors.get(r["ward"], fallback)
        k = per_ward.get(r["ward"], 0)
        per_ward[r["ward"]] = k + 1
        lon += 0.0075 * ((k % 3) - 1)
        lat += 0.0075 * ((k // 3) - 1)
        desc = (f'<b>{escape(r["village"])}</b><br/>'
                f'ward {escape(r["ward"])}, zone {escape(r["zone"])}<br/>'
                f'{r["households"]} households, {r["population"]} people<br/><br/>'
                f'From the Afore LLG Ward Profiles. We have no position for it.'
                f'<br/><br/><b>This pin is in the wrong place on purpose</b> - it '
                f'starts at the middle of ward {escape(r["ward"])}. Drag it to the '
                f'village. If it is somewhere we already map under a different '
                f'name, write that name here instead and delete the pin.')
        L.append(f'    <Placemark><name>{escape(r["village"])}</name>'
                 f'<styleUrl>#place</styleUrl>'
                 f'<description><![CDATA[{desc}]]></description>'
                 f'<Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point>'
                 f'</Placemark>')
    L.append('  </Folder>')

    L.append('  <Folder><name>Villages we do hold (for bearings - correct any '
             'that are wrong)</name><open>0</open>')
    for r in sorted(data, key=lambda r: r["village"]):
        hit = known(r["village"])
        if not hit:
            continue
        L.append(f'    <Placemark><name>{escape(hit["name"])}</name>'
                 f'<styleUrl>#ref</styleUrl>'
                 f'<description><![CDATA[{escape(r["village"])} in the Ward '
                 f'Profile, ward {escape(r["ward"])}, zone {escape(r["zone"])}'
                 f'<br/>{r["households"]} households, {r["population"]} people'
                 f'<br/>position: {hit["src"]}]]></description>'
                 f'<Point><coordinates>{hit["lon"]:.6f},{hit["lat"]:.6f},0'
                 f'</coordinates></Point></Placemark>')
    L.append('  </Folder>')
    L.append('</Document></kml>')

    OUT.write_text("\n".join(L) + "\n")
    hh = sum(int(r["households"] or 0) for r in unmapped)
    pop = sum(int(r["population"] or 0) for r in unmapped)
    print(f"wrote {OUT}")
    print(f"  {len(unmapped)} to place ({hh:,} households, {pop:,} people)")
    print(f"  {len(data) - len(unmapped)} shown for bearings")


if __name__ == "__main__":
    main()
