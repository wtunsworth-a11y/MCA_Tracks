"""Every Ward Profile village, with its population, at the best position we have.

outputs/access/mca_population.kml

One placemark per SPREADSHEET ROW, not per mapped place. That is the whole
point: the population total in this file has to equal the spreadsheet's own
total for villages inside the conservation area, so no row may be merged into
another, dropped for want of a position, or counted twice.

Where that differs from mca_villages.kml: there, Kawowoki 1 and Kawowoki 2
are summed onto our single Kawowoki dot. Here they are two placemarks, both
on that one position, because we do not know which end is which. Two pins on
one spot is honest; one pin carrying both populations would be a village that
does not exist.

Position, best first, and every placemark says which it got:

  1. surveyed, placed or confirmed - a position we stand behind
  2. a hamlet or cluster from the field data
  3. INDICATIVE - Will's dragged pin, some of which he said are guesses
  4. NO POSITION - dropped on the ward centre so the total stays whole, and
     flagged as such in the name itself

The script fails rather than writes if the total comes out wrong.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)
from make_villages_kml import collect  # noqa: E402
from ward_profile import load_profile, variants  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INDICATIVE = ROOT / "data" / "reference" / "indicative_positions.csv"
OUT = ROOT / "outputs" / "access" / "mca_population.kml"

OUTSIDE = "Outside MCA"

STYLES = {
    "known": ("ffc9681f", "Position we stand behind"),
    "field": ("ffb06a9c", "From the field data"),
    "indicative": ("ff2d8cff", "INDICATIVE - Will's pin, some are guesses"),
    "none": ("ff3a3ab0", "NO POSITION - on the ward centre to keep the total whole"),
}


def indicative():
    if not INDICATIVE.exists():
        return {}
    with INDICATIVE.open() as fh:
        return {r["place"].strip().lower(): (float(r["lon"]), float(r["lat"]))
                for r in csv.DictReader(l for l in fh if not l.startswith("#"))}


def main():
    rows = load_profile()
    mapped = collect()
    places, aliases = load_places(), load_aliases()
    ind = indicative()

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

    # Ward centres, from the villages in that ward we can place. Used only as
    # a last resort so a village with no position still carries its people.
    anchor = {}
    for r in rows:
        hit = known(r["village"])
        if hit:
            anchor.setdefault(r["ward"], []).append((hit["lon"], hit["lat"]))
    anchor = {w: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v))
              for w, v in anchor.items()}

    placed = []
    for r in rows:
        hit = known(r["village"])
        if hit:
            kind = "field" if hit["src"] in ("waypoint file", "GPS-inferred") else "known"
            lon, lat, src = hit["lon"], hit["lat"], hit["src"]
            at = hit["name"]
        elif r["village"].strip().lower() in ind:
            lon, lat = ind[r["village"].strip().lower()]
            kind, src, at = "indicative", "indicative pin placed by Will", None
        else:
            lon, lat = anchor.get(r["ward"], (148.33, -9.13))
            kind, src, at = "none", "no position at all", None
        placed.append(dict(row=r, lon=lon, lat=lat, kind=kind, src=src, at=at))

    inside = [p for p in placed if p["row"]["zone"] != OUTSIDE]
    outside = [p for p in placed if p["row"]["zone"] == OUTSIDE]
    total_in = sum(p["row"]["population"] for p in inside)
    total_out = sum(p["row"]["population"] for p in outside)

    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         f'<name>Managalas population - {total_in:,} people inside the MCA</name>',
         f'<description><![CDATA[Every village in the Afore LLG Ward Profiles, '
         f'one placemark each, carrying its own population.<br/><br/>'
         f'<b>Inside the conservation area: {len(inside)} villages, '
         f'{total_in:,} people</b> - the same total as the spreadsheet.<br/>'
         f'Outside: {len(outside)} villages, {total_out:,} people, in their own '
         f'folder and not counted in that total.<br/><br/>'
         f'Pin colour shows how good the position is. Blue pins are indicative '
         f'- dragged by hand, some admitted guesses. Red pins have no position '
         f'at all and sit on their ward centre purely so their people are not '
         f'missing from the file.]]></description>']
    for sid, (colour, _why) in STYLES.items():
        L.append(f'<Style id="{sid}"><IconStyle><color>{colour}</color>'
                 f'<scale>1.05</scale><Icon><href>http://maps.google.com/mapfiles/'
                 f'kml/paddle/wht-circle.png</href></Icon></IconStyle>'
                 f'<LabelStyle><scale>0.8</scale></LabelStyle></Style>')

    def pin(p):
        r = p["row"]
        name = r["village"] + (" [NO POSITION]" if p["kind"] == "none" else "")
        bits = [f'<b>{r["population"]:,} people</b>, {r["households"]} households',
                f'ward {escape(r["ward"])}, zone {escape(r["zone"])}',
                f'position: {escape(p["src"])}']
        if p["at"] and p["at"].lower() != r["village"].strip().lower():
            bits.append(f'mapped by us as <b>{escape(p["at"])}</b>')
        if p["kind"] == "indicative":
            bits.append('<b>INDICATIVE ONLY.</b> Dragged by hand on 23 Oct 2026 '
                        'and some of these were described as guesses. Do not '
                        'measure anything from it.')
        if p["kind"] == "none":
            bits.append('<b>WE HAVE NO POSITION FOR THIS VILLAGE.</b> The pin is '
                        'on the middle of its ward so that its people are still '
                        'in the file. It is not where the village is.')
        return (f'    <Placemark><name>{escape(name)}</name>'
                f'<styleUrl>#{p["kind"]}</styleUrl>'
                f'<description><![CDATA[{"<br/>".join(bits)}]]></description>'
                f'<ExtendedData>'
                f'<Data name="population"><value>{r["population"]}</value></Data>'
                f'<Data name="households"><value>{r["households"]}</value></Data>'
                f'<Data name="ward"><value>{escape(r["ward"])}</value></Data>'
                f'<Data name="zone"><value>{escape(r["zone"])}</value></Data>'
                f'<Data name="position_quality"><value>{p["kind"]}</value></Data>'
                f'<Data name="position_source"><value>{escape(p["src"])}</value></Data>'
                f'</ExtendedData>'
                f'<Point><coordinates>{p["lon"]:.6f},{p["lat"]:.6f},0</coordinates>'
                f'</Point></Placemark>')

    def zone_key(z):
        head = z.rstrip("ab")
        return (int(head) if head.isdigit() else 99, z)

    L.append(f'  <Folder><name>Inside the MCA - {len(inside)} villages, '
             f'{total_in:,} people</name><open>1</open>')
    for z in sorted({p["row"]["zone"] for p in inside}, key=zone_key):
        grp = [p for p in inside if p["row"]["zone"] == z]
        pop = sum(p["row"]["population"] for p in grp)
        L.append(f'    <Folder><name>Zone {escape(z)} - {len(grp)} villages, '
                 f'{pop:,} people</name><open>0</open>')
        L.extend(pin(p) for p in sorted(grp, key=lambda p: -p["row"]["population"]))
        L.append('    </Folder>')
    L.append('  </Folder>')

    L.append(f'  <Folder><name>Outside the MCA - {len(outside)} villages, '
             f'{total_out:,} people (not in the total)</name><open>0</open>')
    L.extend(pin(p) for p in sorted(outside, key=lambda p: -p["row"]["population"]))
    L.append('  </Folder>')
    L.append('</Document></kml>')

    # The whole requirement in one line: the file must carry every person the
    # spreadsheet carries. Write nothing if it does not.
    expect = sum(r["population"] for r in rows if r["zone"] != OUTSIDE)
    assert total_in == expect, f"inside-MCA population {total_in} != {expect}"
    assert len(inside) + len(outside) == len(rows), "a row was lost or duplicated"

    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    print(f"  inside the MCA : {len(inside)} villages, {total_in:,} people "
          f"(spreadsheet says {expect:,})")
    print(f"  outside        : {len(outside)} villages, {total_out:,} people")
    for kind in STYLES:
        n = sum(1 for p in placed if p["kind"] == kind)
        pop = sum(p["row"]["population"] for p in placed if p["kind"] == kind)
        if n:
            print(f"    {n:3d} villages, {pop:6,} people  {kind}")


if __name__ == "__main__":
    main()
