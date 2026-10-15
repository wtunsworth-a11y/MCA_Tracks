"""The job list for the field team: tracks to walk, and points to collect.

outputs/access/TODO.md

TRACK_CHECKLIST.md is organised by route, which is how the team's own list is
written. This one is organised by JOB, because a route is not a unit of work:
one missing coordinate blocks a whole route, and one short unrecorded link
closes several routes at once. The same rows, cut the other way.

Two inputs:

  * cross_reference_tracks.py's CSV, for the walking;
  * data/reference/facilities.csv, the schools, aid posts, health centres and
    airstrips whose positions have still to be recorded.

Village names are resolved through cross_reference_tracks' own loaders rather
than a second copy of the rules here, so a name cannot mean one thing in the
checklist and another in this list. That makes this script depend on the same
geo stack; run it after the cross-reference, which is the order the pipeline
runs anyway.
"""
from pathlib import Path
import csv
import difflib
import re
import sys
from collections import defaultdict, OrderedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_aliases, load_placed, candidates, best_tier,
)

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "outputs" / "access" / "track_checklist.csv"
ALIASES = ROOT / "data" / "reference" / "place_aliases.csv"
FACILITIES = ROOT / "data" / "reference" / "facilities.csv"
OUT = ROOT / "outputs" / "access" / "TODO.md"

# Below this, two ends are the same place to anyone standing there.
OFF_NETWORK_M = 500.0
# A direct link worth singling out: short enough to be a morning's work.
QUICK_WIN_KM = 3.0


def load():
    with CHECKLIST.open() as fh:
        return list(csv.DictReader(fh))


def notes_by_place():
    """What the field has already told us about a name.

    Without this the list asks for things we have been told. Will said on
    3 Oct that Tetebedi/Tedebedi is outside the conservation area and on
    4 Oct that Emoriva is probably Emo River and also outside it; a job list
    that ignores that sends someone to ask again.
    """
    notes = {}
    if not ALIASES.exists():
        return notes
    with ALIASES.open() as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#") or len(row) < 5:
                continue
            name, note = row[0].strip(), row[4].strip()
            if name.lower() == "as_written" or not note or note == "spelling":
                continue
            notes.setdefault(name.lower(), note)
    return notes


def canonical(row, end):
    """The resolved name, falling back to what the team wrote.

    Aggregating on the written name counts Jaure and Jaura, or Tedebedi and
    Tetebedi, as two places and invents a question about whether they are
    one. The resolved name is empty only when the place has no position,
    which is exactly the case where the written name is all we have.
    """
    return row[f"{end}_resolved"].strip() or row[f"{end}_place"].strip()


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def routes_of(rows):
    out = OrderedDict()
    for r in rows:
        out.setdefault(r["route_id"], []).append(r)
    return out


def unlocated(rows):
    """Place -> the routes it blocks, and the places that would pin it down.

    A missing coordinate is the cheapest thing on this list to fix and the
    most expensive to leave: it stops the route being checked at all, so we
    cannot even say whether the walking has been done.
    """
    places = OrderedDict()
    for r in rows:
        if r["status"] != "unlocated":
            continue
        m = re.search(r"no position for (.+?)\s*$", r["detail"])
        if not m:
            continue
        name = m.group(1)
        rec = places.setdefault(name, {"routes": set(), "neighbours": set(),
                                       "as_written": set()})
        rec["routes"].add(r["route_id"])
        rec["as_written"].add(r["as_written"])
        for end in (r["from_place"], r["to_place"]):
            if end != name:
                rec["neighbours"].add(end)
    return places


def never_reached(rows):
    """Place -> how far it sits from anything recorded, and where it appears.

    Keyed on the resolved name so one place written two ways is one row.
    """
    off = defaultdict(lambda: {"m": 0.0, "routes": set(), "written": set()})
    for r in rows:
        if r["status"] not in ("partial", "missing"):
            continue
        for end, dist_key in (("from", "from_off_network_m"),
                              ("to", "to_off_network_m")):
            d = fnum(r[dist_key])
            if d is None or d <= OFF_NETWORK_M:
                continue
            name = canonical(r, end)
            off[name]["m"] = max(off[name]["m"], d)
            off[name]["routes"].add(r["route_id"])
            written = r[f"{end}_place"].strip()
            if written and written != name:
                off[name]["written"].add(written)
    return OrderedDict(sorted(off.items(), key=lambda kv: -kv[1]["m"]))


def unjoined(rows):
    """Legs whose two ends are both recorded but which nothing directly links.

    These are tracks that exist on the ground - the team walks them - but no
    recording follows them. Sorted by straight-line distance, so the short
    ones come first: they are the best value per hour walked.
    """
    out = []
    for r in rows:
        if "the long way round" not in r["detail"] and \
           "nothing recorded joins" not in r["detail"]:
            continue
        out.append(r)
    return sorted(out, key=lambda r: fnum(r["straight_km"]) or 0.0)


def never_walked(rows):
    return [r for r in rows if r["status"] == "missing"]


UNNAMED = "not named"


def suggest(village, ward, locate, known_names):
    """A place this facility might belong to - offered as a question only.

    Three tries, strongest first:

      1. the village name with trailing words dropped, so "Afore Govt Station"
         reaches Afore and "Anatua 2" reaches Anatua;
      2. a near-spelling of a name we hold, which is what connects Boidomo to
         Bodoimo and Umbuwara to Umbuara;
      3. the ward name, since wards are usually named after a village in them.

    Never applied silently. Umbara and Umbuara are a one-letter apart and are
    different villages; only the field could tell us that, and the same trap is
    waiting in half these names.
    """
    if village != UNNAMED:
        words = village.split()
        for cut in range(len(words) - 1, 0, -1):
            stem = " ".join(words[:cut])
            hit = locate(stem)
            if hit:
                return (stem, hit, "the first part of the name matches")

        close = difflib.get_close_matches(village.lower(),
                                          list(known_names), n=1, cutoff=0.82)
        if not close:
            letters = sorted(village.lower())
            close = [k for k in known_names
                     if len(k) > 4 and sorted(k) == letters]
        if close:
            name = known_names[close[0]]
            hit = locate(name)
            if hit:
                return (name, hit, "it is a near-spelling of a name we hold")

    ward_place = ward.split(" ", 1)[-1].strip()
    hit = locate(ward_place)
    if hit:
        return (ward_place, hit, "the ward is named after it")
    return None


def facilities():
    """The facility list, grouped by the village it is to be collected at.

    Returns groups in the order the ward table gives them, each carrying
    whether we can tell the team where to go. A village position is not the
    facility's position - a school, an aid post and an airstrip in one village
    are three points - but without it we cannot even send someone.
    """
    if not FACILITIES.exists():
        return []
    with FACILITIES.open() as fh:
        rows = list(csv.DictReader(l for l in fh if not l.startswith("#")))

    places, aliases = load_places(), load_aliases()
    # Every name we could send someone to, not just the gazetteer's: the
    # alias targets and the team's own placements carry names the gazetteer
    # never had, and Bodoimo is one of them.
    known_names = {n.lower(): n for n in places}
    for a in aliases.values():
        if a.get("to"):
            known_names.setdefault(a["to"].lower(), a["to"])
    for rec in load_placed().values():
        known_names.setdefault(rec["name"].lower(), rec["name"])

    def locate(name):
        hits = best_tier(candidates(name, places, aliases))
        return hits[0] if hits else None

    groups = OrderedDict()
    for r in rows:
        key = (r["village"].strip(), r["ward"].strip(), r["zone"].strip())
        groups.setdefault(key, []).append(r)

    out = []
    for (village, ward, zone), items in groups.items():
        found = None if village == UNNAMED else locate(village)
        guess = None
        if not found:
            guess = suggest(village, ward, locate, known_names)
        out.append({
            "village": village, "ward": ward, "zone": zone,
            "items": items, "found": found, "guess": guess,
        })
    return out


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def main():
    rows = load()
    by_route = routes_of(rows)
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1

    unl = unlocated(rows)
    off = never_reached(rows)
    gaps = unjoined(rows)
    missing = never_walked(rows)
    notes = notes_by_place()

    L = []
    w = L.append

    n_fac = sum(len(g["items"]) for g in facilities())

    w("# To do - Managalas tracks and facility points")
    w("")
    w("Built by `scripts/make_todo.py` from `outputs/access/track_checklist.csv`")
    w("and `data/reference/facilities.csv`. `TRACK_CHECKLIST.md` lists the walking")
    w("route by route; this lists everything job by job, because one missing")
    w("coordinate blocks a whole route and one short link closes several.")
    w("")
    w("**Two things outstanding.** The walking: "
      f"of {len(rows)} legs on the team's list, **{counts['recorded']} recorded**, "
      f"**{counts['partial']} partly**, **{counts['missing']} not walked**, "
      f"**{counts['unlocated']} cannot be checked** until a place is located. "
      f"The points: **{n_fac} facility positions** still to collect, none of "
      "which has a coordinate yet.")
    w("")

    # ---- 1. coordinates ----
    w("## 1. Places on the track list that need a coordinate")
    w("")
    w(f"**{len(unl)} {plural(len(unl), 'place')}.** Nothing else on this list is")
    w("cheaper to fix. Until each one has a position we cannot say whether its")
    w("route has been walked or not - it is not missing, it is unknown.")
    w("")
    w("A rough position is enough: the village, or the junction, to within a")
    w("kilometre. Mark it in the KML (`outputs/access/unlocated_places.kml`),")
    w("or just say which known place it is near and how far.")
    w("")
    for name, rec in unl.items():
        routes = ", ".join(sorted(rec["routes"]))
        nb = ", ".join(sorted(rec["neighbours"])) or "-"
        w(f"- [ ] **{name}** — blocks `{routes}` "
          f"({'; '.join(sorted(rec['as_written']))})")
        w(f"  - on the list between: {nb}")
        note = notes.get(name.lower())
        if note:
            w(f"  - already said: {note}")
    w("")
    n = 2

    # ---- facility points ----
    fac = facilities()
    if fac:
        total = sum(len(g["items"]) for g in fac)
        blocked = [g for g in fac if not g["found"]]
        ready = [g for g in fac if g["found"]]
        w(f"## {n}. Facility points to collect")
        w("")
        w(f"**{total} points** across {len(fac)} "
          f"{plural(len(fac), 'village')} - the second list, the schools, aid")
        w("posts, health centres, airstrips and offices.")
        w("")
        w("Each facility is its own point. A school, an aid post and an airstrip")
        w("in one village are three positions, not one, so a village coordinate")
        w("does not cover them. Grouped by village so a single visit collects")
        w("everything there.")
        w("")
        w("Record the status as found as well as the position - several of these")
        w("were last reported closed decades ago, and the table below is what was")
        w("said, not what is there now.")
        w("")

        if blocked:
            n_pts = sum(len(g["items"]) for g in blocked)
            w(f"### First: {len(blocked)} "
              f"{plural(len(blocked), 'village')} we cannot send anyone to "
              f"({n_pts} {plural(n_pts, 'point')})")
            w("")
            w("Either the ward table does not name the village, or the name is one")
            w("we have no position for. Settle these and the points below become")
            w("collectable on the same trip as everything else in the ward.")
            w("")
            for g in blocked:
                label = (f"ward **{g['ward']}** - village not named in the table"
                         if g["village"] == UNNAMED
                         else f"**{g['village']}** (ward {g['ward']})")
                w(f"- [ ] {label} — {len(g['items'])} "
                  f"{plural(len(g['items']), 'point')}")
                if g["guess"]:
                    nm, hit, why = g["guess"]
                    w(f"  - is this at **{nm}**? we hold a position for it "
                      f"({hit.get('src', 'unknown source')}), and {why} "
                      f"— please confirm rather than let us assume")
                for it in g["items"]:
                    w(f"  - {it['facility']} — *{it['status']}*")
            w("")

        if ready:
            n_pts = sum(len(g["items"]) for g in ready)
            w(f"### Then: {n_pts} {plural(n_pts, 'point')} at "
              f"{len(ready)} {plural(len(ready), 'village')} we can find")
            w("")
            w("| village | ward | points | facilities |")
            w("|---|---|---:|---|")
            for g in ready:
                shown = "; ".join(f"{it['facility']} (*{it['status']}*)"
                                  for it in g["items"])
                resolved = g["found"]["name"]
                village = (g["village"] if resolved.lower() == g["village"].lower()
                           else f"{g['village']} → {resolved}")
                w(f"| {village} | {g['ward']} | {len(g['items'])} | {shown} |")
            w("")
        n += 1

    # ---- 3. quick wins ----
    quick = [r for r in gaps if (fnum(r["straight_km"]) or 99) <= QUICK_WIN_KM]
    w(f"## {n}. Short links worth walking first")
    w("")
    w(f"**{len(quick)} {plural(len(quick), 'leg')} under {QUICK_WIN_KM:g} km.** Both ends are")
    w("already recorded, but no recording follows the direct track between them,")
    w("so the map has to send people the long way round. Short walks, each of")
    w("which closes a hole in the network.")
    w("")
    for r in quick:
        straight = fnum(r["straight_km"])
        route_km = fnum(r["route_km"])
        detour = (f", against {route_km:.1f} km the long way round"
                  if route_km else "")
        w(f"- [ ] **{r['from_place']} → {r['to_place']}** — "
          f"{straight:.1f} km direct{detour}  `{r['route_id']}`")
    w("")
    n += 1

    # ---- 4. the rest of the unjoined ----
    rest = [r for r in gaps if (fnum(r["straight_km"]) or 99) > QUICK_WIN_KM]
    w(f"## {n}. Longer links, same problem")
    w("")
    w(f"**{len(rest)} {plural(len(rest), 'leg')}.** Both ends recorded, the direct track not.")
    w("")
    for r in rest:
        straight = fnum(r["straight_km"])
        route_km = fnum(r["route_km"])
        detour = (f", against {route_km:.1f} km the long way round"
                  if route_km else "")
        w(f"- [ ] **{r['from_place']} → {r['to_place']}** — "
          f"{straight:.1f} km direct{detour}  `{r['route_id']}`")
    w("")
    n += 1

    # ---- 5. never reached ----
    w(f"## {n}. Places no recording has ever reached")
    w("")
    w(f"**{len(off)} {plural(len(off), 'place')}**, furthest first. The number is how far the")
    w("place sits from the nearest recorded line - that is the walk needed to")
    w("tie it in, not the length of any particular track.")
    w("")
    w("| place | km off the network | routes | note |")
    w("|---|---:|---|---|")
    for name, rec in off.items():
        routes = ", ".join(sorted(rec["routes"]))
        bits = []
        if rec["written"]:
            bits.append("also written " + ", ".join(sorted(rec["written"])))
        note = notes.get(name.lower())
        if note:
            bits.append(note)
        w(f"| {name} | {rec['m'] / 1000:.1f} | {routes} | {'; '.join(bits)} |")
    w("")
    n += 1

    # ---- 6. never walked ----
    w(f"## {n}. Legs with neither end recorded")
    w("")
    w(f"**{len(missing)} {plural(len(missing), 'leg')}.** Nothing nearby has been recorded at")
    w("either end, so these are whole journeys rather than gaps to close.")
    w("")
    for rid, legs in by_route.items():
        mine = [l for l in legs if l["status"] == "missing"]
        if not mine:
            continue
        w(f"- **{legs[0]['as_written']}**  `{rid}`")
        for l in mine:
            straight = fnum(l["straight_km"])
            # Two legs have no distance: one where the team's two names turned
            # out to be the same place, one where the "leg" is a named road
            # rather than a journey. The checklist already explains each, so
            # carry its wording rather than printing a blank.
            dist = f"{straight:.1f} km straight" if straight else l["detail"]
            flag = "  **multi-day walk, not a day trip**" if l["multi_day"] == "yes" else ""
            w(f"  - [ ] {l['from_place']} → {l['to_place']} — {dist}{flag}")
    w("")
    n += 1

    # ---- 7. questions ----
    w(f"## {n}. Questions we need answered, not walked")
    w("")
    w("- [ ] **Ogan.** It burned down on or before 4 Oct 2026. The access figures")
    w("  still count it as 69 households, road-served, 1.48 km by road to Afore -")
    w("  2.6 % of the road-served households. Where have those households gone?")
    w("  Until we know, the published figures are flagged but not corrected.")
    w("- [ ] **Road 1 and Ogan** came back 52 m apart, so `R05` has no leg to walk.")
    w("  Is that right, or did two pins land on one feature?")
    w("- [ ] **The off-plateau routes** - Safia, Kwikila, Oro Bay, Popondetta - are")
    w("  they in scope at all, or only the portion inside the conservation area?")
    w("  Four of the longest jobs on this list are off-plateau, and `F30`")
    w("  (Aiari-Safia) is 54 km in a straight line.")
    w("")

    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    print(f"  {len(unl)} places need a coordinate")
    print(f"  {len(quick)} short links, {len(rest)} longer links")
    print(f"  {len(off)} places never reached, {len(missing)} legs never walked")


if __name__ == "__main__":
    main()
