"""A KML of draggable pins for the places in the team's track list we cannot find.

outputs/access/unlocated_places.kml

Open in Google Earth, drag each pin in the "PLACE THESE" folder onto the real
village, save, and send the file back. Nothing else in the file needs touching.

Every pin starts at a guess, and the guess is stated in its description so it is
never mistaken for a position we hold. The guess is the midpoint of the places
the list itself puts next to it: "Umbuara-Singata" and "Singata-Gora" between
them say Singata is somewhere near the Umbuara-Gora line, which is a far better
starting point than the middle of the map.

Where every neighbour is also unknown the anchoring runs again over the pins it
has already guessed, so "Numba-Umasi-Embi-Warisota" walks outwards from Numba
rather than dumping Embi and Warisota in the middle of the plateau. How many
steps from a known place each pin is is stated on it, because two steps out is
a direction and not a location. Four pins have no located place anywhere in
their route - Road 1, Road 2, and the Organ and Old Cardamom factory ends of
them - and those say so plainly.

Two reference folders come with it, both locked out of the way:
  Known villages  - so a pin can be placed relative to its neighbours
  Recorded tracks - so it is obvious what has already been walked
"""

import sys
import warnings
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import candidates, load_aliases, load_places  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
OUT = ROOT / "outputs" / "access"

# Pins that land on the same spot are impossible to tell apart or drag, so a
# small ring is spread around a shared anchor. 300 m is visible at the zoom
# level you place a village at and far smaller than the uncertainty.
SPREAD_M = 300.0
# The recorded network is 878 km over ~100,000 vertices. 25 m of simplification
# keeps the shape a reader needs and the file small enough to open on a phone.
SIMPLIFY_M = 25.0


def canonical(name, aliases):
    """The spelling we file a place under - Tetebedi and Tedebedi are one pin."""
    al = aliases.get(name.strip().lower())
    if al and al["to"]:
        return al["to"]
    return name.strip()


def neighbours_in_list(place, planned, aliases):
    """Every place the list names immediately before or after this one."""
    out = []
    for _, pr in planned.iterrows():
        chain = [canonical(c, aliases) for c in str(pr["chain"]).split(">")]
        for i, nm in enumerate(chain):
            if nm.lower() != place.lower():
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(chain):
                    out.append(chain[j])
    return out


def anchor_all(unl, planned, places, aliases):
    """Anchor every unknown place, then re-anchor off the guesses, repeatedly.

    Round 1 uses only places we hold a position for. Each later round may use a
    pin guessed in an earlier one, so a chain of unknowns walks outwards from
    the nearest known place instead of collapsing to the map centre. The round a
    pin was settled in is its distance from solid ground and is reported.
    """
    fixed, hops = {}, {}
    for nm in unl:
        nb = neighbours_in_list(nm, planned, aliases)
        pts, via = [], []
        for b in nb:
            c = candidates(b, places, aliases)
            if c:
                pts.append((c[0]["lon"], c[0]["lat"]))
                via.append(c[0]["name"])
        if pts:
            a = np.array(pts)
            fixed[nm] = (float(a[:, 0].mean()), float(a[:, 1].mean()),
                         sorted(set(via)))
            hops[nm] = 1

    for step in range(2, 6):
        added = False
        for nm in unl:
            if nm in fixed:
                continue
            pts, via = [], []
            for b in neighbours_in_list(nm, planned, aliases):
                if b in fixed:
                    pts.append(fixed[b][:2])
                    via.append(b)
            if pts:
                a = np.array(pts)
                fixed[nm] = (float(a[:, 0].mean()), float(a[:, 1].mean()),
                             sorted(set(via)))
                hops[nm] = step
                added = True
        if not added:
            break
    return fixed, hops


def pin(name, lon, lat, desc, style):
    return (f"    <Placemark>\n"
            f"      <name>{escape(name)}</name>\n"
            f"      <styleUrl>#{style}</styleUrl>\n"
            f"      <description><![CDATA[{desc}]]></description>\n"
            f"      <Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point>\n"
            f"    </Placemark>\n")


def main():
    planned = pd.read_csv(REF / "planned_tracks.csv", comment="#")
    places = load_places()
    aliases = load_aliases()
    chk = pd.read_csv(OUT / "track_checklist.csv")

    # The names the cross-reference could not place, and where each one appears.
    unl = {}
    for _, r in chk[chk["status"] == "unlocated"].iterrows():
        for w in str(r["detail"]).replace("no position for ", "").split(" and "):
            unl.setdefault(canonical(w, aliases), set()).add(r["route_id"])

    tr = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    tr_u = tr.to_crs("EPSG:32755")
    centre_u = tr_u.union_all().centroid
    centre = (gpd.GeoSeries([centre_u], crs="EPSG:32755")
              .to_crs("EPSG:4326").iloc[0])

    # Anchor each pin, then spread the ones that share an anchor.
    fixed, hops = anchor_all(set(unl), planned, places, aliases)
    anchors = {}
    for nm in sorted(unl):
        if nm in fixed:
            lon, lat, via = fixed[nm]
            anchors[nm] = (lon, lat, via, hops[nm])
        else:
            anchors[nm] = (centre.x, centre.y, [], 0)

    groups = {}
    for nm, (lon, lat, via, fb) in anchors.items():
        groups.setdefault((round(lon, 4), round(lat, 4)), []).append(nm)
    placed = {}
    for (glon, glat), names in groups.items():
        for k, nm in enumerate(sorted(names)):
            if len(names) == 1:
                placed[nm] = (glon, glat)
                continue
            ang = 2 * np.pi * k / len(names)
            dlat = SPREAD_M * np.cos(ang) / 110_000
            dlon = SPREAD_M * np.sin(ang) / (110_000 * np.cos(np.radians(glat)))
            placed[nm] = (glon + dlon, glat + dlat)

    L = []
    L.append('<?xml version="1.0" encoding="UTF-8"?>')
    L.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    L.append("<Document>")
    L.append("  <name>Managalas - places we cannot find</name>")
    L.append("  <description><![CDATA["
             "<b>Drag each pin in PLACE THESE onto the real village, then save "
             "the file and send it back.</b><br/><br/>"
             "Every pin in that folder is a <i>guess</i>, placed at the midpoint "
             "of the villages your list puts next to it. None of them is a "
             "position we hold. The other two folders are reference only - the "
             "villages we do have positions for, and the tracks already "
             "recorded.<br/><br/>"
             f"Generated {pd.Timestamp.utcnow():%Y-%m-%d} from "
             "NAMES_OF_FOOT_TRACKS_IN_MANAGALAS_CONSERVATION_AREA.docx"
             "]]></description>")
    for sid, icon, scale, colour in (
            ("todo", "placemark_circle_highlight", "1.3", "ff00ffff"),
            ("known", "placemark_circle", "0.7", "ffcccccc")):
        L.append(f'  <Style id="{sid}">')
        L.append(f'    <IconStyle><color>{colour}</color><scale>{scale}</scale>'
                 f'<Icon><href>http://maps.google.com/mapfiles/kml/shapes/'
                 f'{icon}.png</href></Icon></IconStyle>')
        L.append(f'    <LabelStyle><color>{colour}</color><scale>{scale}</scale>'
                 f'</LabelStyle>')
        L.append("  </Style>")
    L.append('  <Style id="road"><LineStyle><color>ff2a6ec8</color>'
             '<width>3</width></LineStyle></Style>')
    L.append('  <Style id="foot"><LineStyle><color>ff767c7e</color>'
             '<width>2</width></LineStyle></Style>')

    L.append("  <Folder><name>PLACE THESE — pins are guesses, drag them</name>")
    L.append("  <open>1</open>")
    for nm in sorted(unl):
        lon, lat = placed[nm]
        _, _, via, hop = anchors[nm]
        note = (aliases.get(nm.lower(), {}) or {}).get("note", "")
        routes = ", ".join(sorted(unl[nm]))
        rows = [f"<b>{escape(nm)}</b>",
                f"Appears in: {escape(routes)}"]
        for _, pr in planned.iterrows():
            if nm.lower() in [c.strip().lower()
                              for c in str(pr["chain"]).split(">")]:
                rows.append(f"&nbsp;&nbsp;• {escape(str(pr['as_written']))}")
        if hop == 0:
            rows.append("<br/><i>This pin is at the centre of the recorded "
                        "network only. Nothing in its route is a place we can "
                        "find, so it could be anywhere - treat the position as "
                        "meaningless.</i>")
        elif hop == 1:
            rows.append("<br/><i>This pin is a guess: the midpoint of "
                        + escape(", ".join(via))
                        + ", which the list names next to it.</i>")
        else:
            rows.append(f"<br/><i>This pin is a guess {hop} steps out: it sits on "
                        + escape(", ".join(via))
                        + f", which {'is' if len(via) == 1 else 'are'} themselves "
                        "guessed. Treat it as a direction, not a location.</i>")
        if isinstance(note, str) and note:
            rows.append(f"<br/><b>Question:</b> {escape(note)}")
        L.append(pin(nm, lon, lat, "<br/>".join(rows), "todo"))
    L.append("  </Folder>")

    L.append("  <Folder><name>Known villages (reference — do not move)</name>")
    L.append("  <open>0</open><visibility>1</visibility>")
    seen = set()
    for pn, cands in sorted(places.items()):
        if "/" in pn:
            continue
        c = cands[0]
        key = (round(c["lon"], 4), round(c["lat"], 4))
        if key in seen:
            continue
        seen.add(key)
        L.append(pin(pn, c["lon"], c["lat"],
                     f"{escape(pn)}<br/>{escape(c['src'])} — {escape(c['note'])}",
                     "known"))
    L.append("  </Folder>")

    L.append("  <Folder><name>Recorded tracks (reference)</name>")
    L.append("  <open>0</open>")
    simp = tr_u.copy()
    simp["geometry"] = simp.geometry.simplify(SIMPLIFY_M)
    simp = simp.to_crs("EPSG:4326")
    for _, r in simp.iterrows():
        is_road = "Road" in str(r.get("type", ""))
        geoms = (r.geometry.geoms if r.geometry.geom_type == "MultiLineString"
                 else [r.geometry])
        for g in geoms:
            if g.is_empty:
                continue
            crd = " ".join(f"{x:.5f},{y:.5f},0" for x, y in
                           np.asarray(g.coords)[:, :2])
            L.append("    <Placemark>")
            L.append(f"      <name>{escape(str(r['name'])[:60])}</name>")
            L.append(f"      <styleUrl>#{'road' if is_road else 'foot'}</styleUrl>")
            L.append(f"      <LineString><tessellate>1</tessellate>"
                     f"<coordinates>{crd}</coordinates></LineString>")
            L.append("    </Placemark>")
    L.append("  </Folder>")
    L.append("</Document></kml>")

    path = OUT / "unlocated_places.kml"
    path.write_text("\n".join(L) + "\n")
    kb = path.stat().st_size / 1024
    print(f"wrote {path}  ({kb:.0f} KB)")
    by_hop = {}
    for v in anchors.values():
        by_hop[v[3]] = by_hop.get(v[3], 0) + 1
    print(f"  {len(unl)} pins to place: "
          + ", ".join(f"{n} anchored "
                      + ("on known villages" if h == 1 else
                         "nowhere at all" if h == 0 else f"{h} steps out")
                      for h, n in sorted(by_hop.items(), reverse=True)))
    print(f"  {len(seen)} known villages, {len(tr)} recorded tracks as reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
