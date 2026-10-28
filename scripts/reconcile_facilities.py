"""Which facilities on the to-do list has Russell actually collected?

    python3 scripts/reconcile_facilities.py

Writes outputs/access/facilities_reconciled.csv and prints the table.

data/reference/facilities.csv is the list of facility points still wanted.
data/reference/waypoints_facilities.csv is what came back from the field on
27 Oct 2026. Deciding which rows of the first are answered by the second is
not a string comparison: the list says "Afore Govt Station" where the field
says "Afore Airstrip", says "Aid Post" with no village at all in nine rows,
and distinguishes elementary from primary from high school where a loose
match would collapse all three.

So a row is only called COLLECTED on two independent agreements:

  KIND   elementary / primary / high school / aid post / health / airstrip /
         office / church, read from both sides. Elementary and primary are
         never treated as the same thing - they are separate rows on the list
         and separate buildings on the ground.
  PLACE  the village named on the list is in the point's name, OR the point
         sits within 1.5 km of where we map that village.

Agreeing on kind alone is reported as LIKELY, not collected, because "Aid
Post" with no village matches nineteen different aid posts. Nothing is struck
off a field document on a LIKELY.

The nine rows with no village named can only ever be LIKELY. They are the
ones to put in front of someone who knows the ground.
"""
from pathlib import Path
import csv
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)
from make_villages_kml import collect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAC = ROOT / "data" / "reference" / "facilities.csv"
WP = ROOT / "data" / "reference" / "waypoints_facilities.csv"
NOTES = ROOT / "data" / "reference" / "facility_field_notes.csv"
OUT = ROOT / "outputs" / "access" / "facilities_reconciled.csv"

NEAR_KM = 1.5

# The kinds that identify a FACILITY. Sub-buildings - a teacher's house, a
# dormitory, a library - are deliberately NOT in this list. They were, and a
# point called "Koruwo Primary School Head Teacher's house" then satisfied the
# row asking for Koruwo ELEMENTARY School, because both mention a teacher's
# house. A sub-building is evidence about the school named in its own name and
# about no other.
KINDS = [
    ("elementary school", "elementary school"),
    ("primary school", "primary school"),
    ("high school", "high school"),
    ("community aid post", "aid post"),
    ("aid post", "aid post"),
    ("health centre", "health centre"),
    ("health center", "health centre"),
    ("chw house", "chw house"),
    ("airstrip", "airstrip"),
    ("church", "church"),
    ("office", "office"),
    ("guest house", "guest house"),
]


def kinds_of(text):
    """Every kind of facility this text names.

    A to-do row often names several at once - "Afore Health Centre, clinic +
    3 CHW houses" wants a health centre AND CHW houses - so this returns a
    set, and a row counts as collected only when every kind in it was found.
    Half of it found is PARTIAL, which is a different thing and is not struck
    off anything.
    """
    t = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
    t = " ".join(t.split())
    found = {v for k, v in KINDS if k in t}
    if not found and "school" in t:
        found = {"school"}
    return found


KIND_WORDS = {"elementary", "primary", "high", "school", "aid", "post",
              "health", "centre", "center", "chw", "house", "houses",
              "airstrip", "church", "office", "dda", "sub", "district",
              "teacher", "building", "clinic", "male", "female", "and",
              "dormitories", "dormitory"}


def tokens(village):
    t = re.sub(r"[^a-z0-9 ]", " ", (village or "").lower()).split()
    drop = {"govt", "station", "village", "not", "named", "1", "2"}
    return [x for x in t if x not in drop]


def km(a, b):
    from math import radians, sin, cos, asin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


def main():
    with FAC.open() as fh:
        fac = list(csv.DictReader(l for l in fh if not l.startswith("#")))

    # What Russell said, which outranks anything worked out here. It names the
    # village where the ward table left it blank, and it says where there is
    # nothing to collect at all - a school meeting in a borrowed shelter is
    # not a point, and asking for it again costs a day's walk.
    notes = []
    if NOTES.exists():
        with NOTES.open() as fh:
            notes = list(csv.DictReader(l for l in fh if not l.startswith("#")))

    def note_for(row):
        for n in notes:
            if (n["ward"].strip() == row["ward"].strip()
                    and n["village"].strip().lower() == row["village"].strip().lower()
                    and row["facility"].strip().lower().startswith(
                        n["facility_startswith"].strip().lower())):
                return n
        return None

    for r in fac:
        n = note_for(r)
        r["village_on_list"] = r["village"]
        if n and n["resolution"] == "village_named" and n["village_is"].strip():
            r["village"] = n["village_is"].strip()
            r["field_note"] = n["note"]
    with WP.open() as fh:
        wp = list(csv.DictReader(l for l in fh if not l.startswith("#")))
    for w in wp:
        w["lon"], w["lat"] = float(w["lon"]), float(w["lat"])
        w["kinds"] = kinds_of(w["name"])
        w["flat"] = " ".join(re.sub(r"[^a-z0-9 ]", " ", w["name"].lower()).split())

    mapped = collect()
    places, aliases = load_places(), load_aliases()

    # Every village name we hold, for the guard above. "Gora" is inside
    # "Gorobuna", but the guard compares both ways round, so a Gorobuna row is
    # not vetoed by a point naming Gora.
    known = {n for n in mapped if len(n) >= 4}

    # Every spelling of a place, both ways through the alias file. The field
    # writes Naokanane where the list writes Naukanane, Bodoimo where it
    # writes Boidomo, Umbuara where it writes Umbuwara. Matching on the
    # written form alone left all three as uncollected when Russell had
    # already recorded them.
    variants = {}
    for k, al in aliases.items():
        to = (al.get("to") or "").strip().lower()
        if not to:
            continue
        variants.setdefault(to, set()).update({to, k})
        variants.setdefault(k, set()).update({to, k})

    def spellings(name):
        n = (name or "").strip().lower()
        if not n:
            return set()
        out = set(variants.get(n, {n}))
        hit = best_tier(candidates(name, places, aliases))
        if hit:
            c = str(hit[0]["name"]).strip().lower()
            # The gazetteer carries a double-named place as one row, literally
            # "Sila/Sakarina", and place_aliases.csv deliberately forces
            # neither spelling. Split it, or the Sakarina row never sees
            # Russell's "Sila Airstrip".
            for part in [c] + [x.strip() for x in c.split("/")]:
                out |= variants.get(part, {part})
        return {x for x in out if x}

    def place_words(row):
        """The places this row is about: the village column, and the name the
        facility itself carries. The list files Aguido Elementary School under
        the village Yoivi, so the village column alone never finds it."""
        out = set()
        for v in (row["village"], row["facility"].split(",")[0]):
            for t in tokens(v):
                # Three letters, not four: "Dea" is a village, and dropping it
                # left the Dea rows with no name to match on at all, so they
                # fell through to proximity and collected Ugunomo's school.
                if len(t) >= 3 and t not in KIND_WORDS:
                    out |= spellings(t)
        return out

    def names_another_village(flat, mine, pos):
        """Is this point named for a DIFFERENT place than the row is about?

        Two names for one place are not a different place. Sila and Sakarina
        are the same village - Will, 18 Oct 2026, "used almost
        interchangeably" - and the gazetteer carries them as one row, so
        vetoing Russell's "Sila Airstrip" from the Sakarina row would be the
        veto working against the thing it is for. Anything mapped within
        500 m of the row's own village is taken to be that village under
        another name.
        """
        for v in known:
            if v not in flat or any(v in m or m in v for m in mine):
                continue
            other = mapped.get(v)
            if pos and other and km(pos, (other["lon"], other["lat"])) <= 0.5:
                continue
            return True
        return False

    def where(village):
        """Where we map the village a to-do row names, if we map it at all."""
        for v in (village, re.sub(r"\s*\d$", "", village or "").strip()):
            if not v:
                continue
            if v.lower() in mapped:
                r = mapped[v.lower()]
                return (r["lon"], r["lat"])
            hit = best_tier(candidates(v, places, aliases))
            if hit:
                al = aliases.get(str(hit[0]["name"]).strip().lower())
                nm = (al["to"] if al and al["to"] else hit[0]["name"])
                if str(nm).lower() in mapped:
                    r = mapped[str(nm).lower()]
                    return (r["lon"], r["lat"])
        return None

    rows = []
    for f in fac:
        want = kinds_of(f["facility"])
        toks = tokens(f["village"])
        mine = place_words(f)
        pos = where(f["village"]) if toks else None

        by_name, by_place = [], []
        for w in wp:
            if want and not (want & w["kinds"]):
                continue
            named = any(m in w["flat"] for m in mine)
            near = pos is not None and km(pos, (w["lon"], w["lat"])) <= NEAR_KM
            if named:
                by_name.append(w)
            elif near and not names_another_village(w["flat"], mine, pos):
                # Serefuna sits within 1.5 km of both Anatua and Kokoro, so
                # proximity alone handed it their two elementary schools. A
                # point that names a village of its own is about THAT village,
                # whatever it is near.
                by_place.append(w)

        hits = by_name or by_place
        found_kinds = set().union(*(h["kinds"] for h in hits)) if hits else set()
        missing = (want - found_kinds) if want else set()

        n = note_for(f)
        res = n["resolution"] if n else ""
        if res in ("no_point", "deferred"):
            # His answer stands whatever the matching says. "no_point" is not
            # a failure to find something; it is the finding.
            verdict = ("NO POINT TO COLLECT" if res == "no_point"
                       else "RUSSELL WILL COLLECT")
        elif hits and not missing:
            verdict = "COLLECTED"
        elif hits:
            verdict = "PARTIAL"
        elif want and any(want & w["kinds"] for w in wp):
            verdict = "LIKELY"
        else:
            verdict = "NOT FOUND"

        rows.append({
            "ward": f["ward"], "zone": f["zone"], "village": f["village"],
            # The village AS THE WARD TABLE WROTE IT, often "not named".
            # Without it nothing downstream can find the row again once
            # Russell has told us which village it really is.
            "village_on_list": f.get("village_on_list", f["village"]),
            "facility": f["facility"], "status_on_list": f.get("status", ""),
            "verdict": verdict,
            "matched_on": ("name" if by_name else "position" if by_place else ""),
            "kinds_wanted": ", ".join(sorted(want)),
            "kinds_found": ", ".join(sorted(want & found_kinds)),
            "kinds_missing": ", ".join(sorted(missing)),
            "n_points": len(hits) or "",
            "points": " | ".join(sorted({h["name"] for h in hits})[:6]),
            "notes_from_field": " | ".join(
                sorted({h["note"] for h in hits if h["note"]})[:3]),
            "russell_says": (n["note"] if n else f.get("field_note", "")),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    for v in ("COLLECTED", "NO POINT TO COLLECT", "RUSSELL WILL COLLECT",
              "PARTIAL", "LIKELY", "NOT FOUND"):
        grp = [r for r in rows if r["verdict"] == v]
        print(f"\n{v}  ({len(grp)} of {len(rows)})")
        for r in sorted(grp, key=lambda r: (r["ward"], r["village"])):
            fac_short = r["facility"].split(",")[0][:44]
            extra = (f"  <- {r['points'][:58]}" if v == "COLLECTED"
                     else f"  <- has {r['kinds_found']}; STILL WANTS "
                          f"{r['kinds_missing']}" if v == "PARTIAL" else "")
            print(f"  {r['ward']:<14} {r['village']:<18} {fac_short:<45}{extra}")
    print(f"\nwrote {OUT}")
    return rows


if __name__ == "__main__":
    main()
