"""A walking order for the whole job: where to go, in what order, what to do there.

outputs/access/ITINERARY.md

TODO.md lists the work by job, which is right for planning and wrong for
following. This orders it as a journey - start at Afore, walk to the next
place, collect what is there, walk on - so it can be followed without having
to cross-reference anything.

Two things make the order more than a nearest-neighbour tour:

  * legs that still need recording are DISCOUNTED, so the route prefers to
    travel along a track that has to be walked anyway. Walking a missing leg
    costs nothing extra; he was going to move between those two places.
  * places whose position we do not hold cannot be routed to, so they are
    attached to the stop he can ask at, rather than left in a list of their
    own that he would have to reconcile.

Decisions taken from Will on 16 Oct 2026 are marked in the code where they
change the output. Run after cross_reference_tracks.py.
"""
from pathlib import Path
import csv
import sys
from collections import OrderedDict, defaultdict

import numpy as np
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_reference_tracks import (  # noqa: E402
    load_places, load_aliases, candidates, best_tier,
)

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "outputs" / "access" / "track_checklist.csv"
FACILITIES = ROOT / "data" / "reference" / "facilities.csv"
RECONCILED = ROOT / "outputs" / "access" / "facilities_reconciled.csv"
OUT = ROOT / "outputs" / "access" / "ITINERARY.md"

START = "Afore"                 # Will, 16 Oct: "Afore start point. Can end anywhere"

# Out of the conservation area and out of this trip. Will, 16 Oct: keep them
# visible in a "not now" section so nobody thinks they were forgotten. Note
# Gorobuna is NOT here - he kept it in scope explicitly.
OUT_OF_SCOPE = {"safia", "kwikila", "oro bay", "orobay", "popondetta",
                "tedebedi", "tetebedi", "emoriva", "bua"}

# A leg that still needs recording costs this fraction of its length when the
# route is chosen: he has to travel between the two places anyway, so walking
# the unrecorded track instead of the long way round is nearly free.
JOB_DISCOUNT = 0.3

# Facilities the ward table could not place, and the stop he can ask at.
# Every one of these is Will's own answer on 16 Oct 2026.
ASK_AT = {
    ("Afore Govt Station", "02 Niniuri"): (
        "Afore",
        "the station is slightly different to Afore village - find it from "
        "the village and give each building its own point"),
    ("Anatua 2", "12 Umbuwara"): (
        "Anatua",
        "Anatua is a long village and they have defined Anatua 1 and "
        "Anatua 2 - map both ends, not one point"),
    ("not named", "07 Dea"): (
        "Dea",
        "nobody knows where this airstrip is - ask in the ward"),
    ("not named", "12 Umbuwara"): (
        "Umbuara",
        "the ward table does not say where this aid post is - ask locally"),
    ("not named", "05 Siurani"): (
        "Numba",
        "Siurani is the old name of the village that came before Numba. Try "
        "the NORTHERN end of Numba first - that end is nearest the old site "
        "and is still called Sivurana by some"),
    ("not named", "10 Gora"): (
        "Gora",
        "Gora is one village with three hamlets, sometimes called villages, "
        "all close together - write down which hamlet each one is in"),
    ("not named", "18 Gorobuna"): (
        "Gorobuna",
        "outside the conservation area, but Will kept it in scope - do it"),
}

# A word at a stop where the place is not one place. These are field facts
# that change what someone should do when they get there, not commentary.
STOP_NOTES = {
    "Kokoro": (
        "Kokoro is at least four hamlets - Namieta, Maragane, Jakiro and "
        "Buangfu (Buamfu), spread over about a kilometre and a half. Write "
        "down which hamlet the aid post is actually in."),
    "Anatua": (
        "Anatua is a long village with Anatua 1 and Anatua 2 defined. Map "
        "both ends, not one point."),
}

# Places on the track list with no position at all. He cannot be routed to
# them; he can ask about them wherever he is.
UNLOCATED_NOTE = (
    "No position for this at all. If anyone knows where it is, a village name "
    "and a rough direction and distance is enough.")

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32755", always_xy=True)


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def in_scope(name):
    return name.strip().lower() not in OUT_OF_SCOPE


class Resolver:
    def __init__(self):
        self.places, self.aliases = load_places(), load_aliases()
        self._cache = {}

    def __call__(self, name):
        key = name.strip().lower()
        if key not in self._cache:
            hits = best_tier(candidates(name, self.places, self.aliases))
            self._cache[key] = hits[0] if hits else None
        return self._cache[key]


def facility_stops(resolve):
    """village -> the facility points to collect there, and anything to ask about."""
    if not FACILITIES.exists():
        return {}, []
    with FACILITIES.open() as fh:
        rows = list(csv.DictReader(l for l in fh if not l.startswith("#")))

    # Anything Russell already collected comes off the list. He recorded 191
    # points between 17 and 26 Oct 2026 and it is worse than useless to send
    # him back for a school he has photographed; the ones struck off are named
    # in outputs/access/facilities_reconciled.csv so nobody has to take this
    # on trust. Only a verdict of COLLECTED removes a row. PARTIAL stays -
    # half a row found is not a row done - and so does LIKELY, which means the
    # kind of facility was recorded somewhere but nothing ties it to this
    # village.
    done = {}
    if RECONCILED.exists():
        with RECONCILED.open() as fh:
            for d in csv.DictReader(fh):
                done[(d["ward"].strip(), d["village"].strip(),
                      d["facility"].strip())] = d
    collected = [r for r in rows
                 if done.get((r["ward"].strip(), r["village"].strip(),
                              r["facility"].strip()), {}).get("verdict")
                 == "COLLECTED"]
    rows = [r for r in rows if r not in collected]
    for r in rows:
        d = done.get((r["ward"].strip(), r["village"].strip(),
                      r["facility"].strip()), {})
        if d.get("verdict") == "PARTIAL" and d.get("kinds_missing"):
            r["still_wants"] = d["kinds_missing"]

    stops = defaultdict(list)
    for r in rows:
        village, ward = r["village"].strip(), r["ward"].strip()
        ask = ASK_AT.get((village, ward))
        if ask:
            where, why = ask
            stops[where].append({**r, "ask": why})
            continue
        hit = resolve(village)
        if hit and in_scope(hit["name"]):
            stops[hit["name"]].append({**r, "ask": None})
        elif hit:
            continue                      # out of scope, handled separately
        else:
            # Should not happen once the 16 Oct confirmations are in; if a new
            # facility arrives with an unknown village, say so rather than drop it.
            stops.setdefault("(village not located)", []).append(
                {**r, "ask": "we hold no position for this village"})
    return stops, rows, collected


def walk_jobs(resolve):
    """Legs still to record, as (a, b, description) with both ends locatable."""
    with CHECKLIST.open() as fh:
        rows = list(csv.DictReader(fh))
    jobs = []
    deferred = []
    for r in rows:
        unjoined = ("the long way round" in r["detail"]
                    or "nothing recorded joins" in r["detail"])
        if r["status"] == "missing" or unjoined:
            a_raw, b_raw = r["from_place"].strip(), r["to_place"].strip()
            if not in_scope(a_raw) or not in_scope(b_raw):
                deferred.append(r)
                continue
            if r["multi_day"] == "yes":
                deferred.append(r)
                continue
            ha, hb = resolve(a_raw), resolve(b_raw)
            if not ha or not hb or ha["name"] == hb["name"]:
                continue
            jobs.append({
                "a": ha["name"], "b": hb["name"], "row": r,
                "straight": fnum(r["straight_km"]),
                "route": fnum(r["route_km"]),
            })
    return jobs, deferred, rows


def unlocated_places(rows):
    out = OrderedDict()
    import re
    for r in rows:
        if r["status"] != "unlocated":
            continue
        m = re.search(r"no position for (.+?)\s*$", r["detail"])
        if not m:
            continue
        name = m.group(1)
        if not in_scope(name):
            continue
        out.setdefault(name, set()).add(r["route_id"])
    return out


def build_route(stops, jobs, resolve):
    """Nearest-neighbour from Afore, then 2-opt, on job-discounted distance."""
    names = sorted(stops)
    names = [n for n in names if resolve(n)]
    if START in names:
        names.remove(START)
    names = [START] + names

    pts = {}
    for n in names:
        hit = resolve(n)
        pts[n] = TO_UTM.transform(hit["lon"], hit["lat"])

    idx = {n: i for i, n in enumerate(names)}
    m = np.array([pts[n] for n in names], dtype=float)
    d = np.hypot(m[:, None, 0] - m[None, :, 0], m[:, None, 1] - m[None, :, 1])

    cost = d.copy()
    job_edges = set()
    for j in jobs:
        if j["a"] in idx and j["b"] in idx:
            i, k = idx[j["a"]], idx[j["b"]]
            job_edges.add(frozenset((i, k)))
            cost[i, k] = cost[k, i] = d[i, k] * JOB_DISCOUNT

    # nearest neighbour
    order = [0]
    unseen = set(range(1, len(names)))
    while unseen:
        last = order[-1]
        nxt = min(unseen, key=lambda j: cost[last, j])
        order.append(nxt)
        unseen.discard(nxt)

    def total(seq):
        return sum(cost[seq[i], seq[i + 1]] for i in range(len(seq) - 1))

    # 2-opt, start pinned, open path so the last stop is free to move
    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 1):
            for k in range(i + 1, len(order)):
                cand = order[:i] + order[i:k + 1][::-1] + order[k + 1:]
                if total(cand) < total(order) - 1.0:
                    order, improved = cand, True
    return [names[i] for i in order], d, idx, job_edges


def compute():
    """The whole plan as data. The map and the document both read this, so
    they cannot drift apart."""
    resolve = Resolver()
    stops, fac_rows, collected = facility_stops(resolve)
    jobs, deferred, check_rows = walk_jobs(resolve)
    unloc = unlocated_places(check_rows)

    # every place that is one end of a job is a place he must reach
    for j in jobs:
        stops.setdefault(j["a"], [])
        stops.setdefault(j["b"], [])
    unplaced = stops.pop("(village not located)", [])
    stops.setdefault(START, [])

    route, d, idx, job_edges = build_route(stops, jobs, resolve)

    jobs_by_pair = defaultdict(list)
    for j in jobs:
        jobs_by_pair[frozenset((j["a"], j["b"]))].append(j)

    return dict(resolve=resolve, stops=stops, fac_rows=fac_rows,
                collected=collected, jobs=jobs,
                deferred=deferred, unloc=unloc, unplaced=unplaced, route=route,
                d=d, idx=idx, job_edges=job_edges, jobs_by_pair=jobs_by_pair)


def main():
    plan = compute()
    resolve, stops, fac_rows = plan["resolve"], plan["stops"], plan["fac_rows"]
    collected = plan.get("collected", [])
    jobs, deferred, unloc = plan["jobs"], plan["deferred"], plan["unloc"]
    unplaced, route = plan["unplaced"], plan["route"]
    d, idx, jobs_by_pair = plan["d"], plan["idx"], plan["jobs_by_pair"]
    done_pairs = set()

    L = []
    w = L.append
    w("# Where to go and what to do - Managalas")
    w("")
    w("Start at **Afore**. Work down the list in order. At each stop, do what it")
    w("says, then walk on to the next one. Finish wherever you get to - there is")
    w("no need to come back round.")
    w("")
    w("**The two jobs.**")
    w("")
    w("- **COLLECT** - stand at the thing and save a point. A school, an aid post")
    w("  and an airstrip in one village are three separate points, not one.")
    w("  Write down what you find, even if it is closed or fallen down - some of")
    w("  these were last reported forty years ago and nobody has checked since.")
    w("- **RECORD THE WALK** - turn the tracker on when you leave a stop and off")
    w("  when you reach the next one. **Every leg, every time.** Do not decide")
    w("  which ones are worth it. A track we already have costs nothing to")
    w("  record twice; a track we do not have is lost if you walk it with the")
    w("  tracker off.")
    w("")
    w("**Get what you can and move on.**")
    w("")
    w("Speed matters more than completeness. Take the points that are there to")
    w("be taken, record the walk, and go. If something is awkward - a building")
    w("you cannot find in ten minutes, a track nobody will show you, a crossing")
    w("that is up - leave it and carry on to the next stop. Do not spend a day")
    w("on one difficult point. A half-finished round that comes back quickly is")
    w("worth more than a complete one that does not.")
    w("")
    w("**If you cannot get into a village, skip it.**")
    w("")
    w("It does not matter what the reason is - permission refused, a dispute, a")
    w("funeral, a flooded crossing, sickness, or something nobody explains. Do")
    w("not argue it, do not wait it out, and do not go round the back. Leave,")
    w("and pick the list up at the next number you can reach, by whatever route")
    w("is open to you.")
    w("")
    w("Two things to do when that happens:")
    w("")
    w("- **Keep the tracker running on the way out and on to the next place.**")
    w("  The way round is a track in its own right and probably one nobody has")
    w("  recorded. A detour forced on you is still worth having.")
    w("- **Write down which village you skipped and why.** A skipped village with")
    w("  a reason is information. A skipped village with no note just looks like")
    w("  the list was never finished, and somebody will send you back.")
    w("")
    w("Nothing on this list is worth a confrontation. The stops that get missed")
    w("go into the next round.")
    w("")
    w("If a place is not where this says, or is called something else, write that")
    w("down too. That is as useful as the point.")
    w("")
    w("This is the first round. It does not cover every track on the plateau -")
    w("what is missing after this gets collated into a second round.")
    w("")
    w("---")
    w("")

    walk_km = sum(d[idx[route[i]], idx[route[i + 1]]]
                  for i in range(len(route) - 1)) / 1000.0
    total_pts = sum(len(v) for v in stops.values())
    assert total_pts + len(unplaced) == len(fac_rows), (
        f"{len(fac_rows)} facilities in, {total_pts + len(unplaced)} out - "
        "a point was lost between the ward table and the route")
    n_hops = len(route) - 1
    n_gap = sum(1 for i in range(n_hops)
                if frozenset((route[i], route[i + 1])) in jobs_by_pair)
    w(f"**{len(route)} stops**, {len([s for s in route if stops[s]])} of them with "
      f"something to collect, {total_pts} points in all.")
    w("")
    w(f"**All {n_hops} legs between stops get recorded.** They all count the "
      "same. Do not try to work out which ones are worth more.")
    w("")
    if collected:
        w(f"{len(collected)} points that were on the earlier version of this "
          f"list have been taken off, because they were recorded between 17 "
          f"and 26 October and are already in. They are not forgotten - every "
          f"one is named in `facilities_reconciled.csv`. Do not go back for "
          f"them.")
        w("")
    w(f"The whole round is about **{walk_km:.0f} km** of travel measured in straight "
      "lines between stops, so the real walking is more. It is not one trip; take "
      "it in whatever pieces suit, in this order.")
    w("")

    for n, name in enumerate(route, 1):
        hit = resolve(name)
        w(f"## {n}. {name}")
        w("")
        if hit:
            w(f"`{hit['lat']:.4f}, {hit['lon']:.4f}`  ({hit.get('src', 'position')})")
            w("")
        items = stops.get(name, [])
        standing = STOP_NOTES.get(name)
        if standing:
            w(f"> **{standing}**")
            w("")
        if items:
            for note in dict.fromkeys(it["ask"] for it in items if it["ask"]):
                w(f"> **{note[0].upper()}{note[1:]}.**")
                w("")
            for it in items:
                w(f"- **COLLECT** {it['facility']}")
                w(f"  - ward {it['ward']}, reported *{it['status']}*")
        else:
            w("- Nothing to collect here - this stop is on the way, or is one end")
            w("  of a walk that needs recording.")
        w("")

        if n < len(route):
            nxt = route[n]
            pair = frozenset((name, nxt))
            straight = d[idx[name], idx[nxt]] / 1000.0
            # Deliberately no note saying which legs matter more. Will,
            # 16 Oct 2026: he would spend the day trying to force a hard one
            # instead of banking the easy ones. Every leg reads the same.
            if pair in jobs_by_pair and pair not in done_pairs:
                j = jobs_by_pair[pair][0]
                done_pairs.add(pair)
                straight = j["straight"] or straight
            w(f"**WALK TO {nxt.upper()} AND RECORD IT.** "
              f"About {straight:.1f} km.")
            w("")
        w("")

    missed = [p for p in jobs_by_pair if p not in done_pairs]
    if missed:
        w("---")
        w("")
        w("## Only if it is easy")
        w("")
        w("The round passes both ends of these but not one after the other, so")
        w("they are not part of the walk above. **Do not go out of your way for")
        w("them.** If you happen to be going that way anyway, record it; if not,")
        w("leave it for the next round.")
        w("")
        pos = {name: i for i, name in enumerate(route, 1)}
        for pair in sorted(missed, key=lambda p: jobs_by_pair[p][0]["straight"] or 0):
            j = jobs_by_pair[pair][0]
            at = sorted(x for x in (pos.get(j["a"]), pos.get(j["b"])) if x)
            where = (f" — you are at stop {at[0]} and stop {at[1]}"
                     if len(at) == 2 else "")
            w(f"- [ ] **{j['a']} → {j['b']}**, about "
              f"{j['straight'] or 0:.1f} km{where}  `{j['row']['route_id']}`")
        w("")

    if unloc:
        w("---")
        w("")
        w("## Ask about these anywhere")
        w("")
        w(UNLOCATED_NOTE)
        w("")
        for name, routes in unloc.items():
            w(f"- [ ] **{name}** — on the track list in "
              f"{', '.join(sorted(routes))}")
        w("")

    if unplaced:
        w("---")
        w("")
        w("## Could not be put on the route")
        w("")
        w("We hold no position for the village these are listed under, so there")
        w("is nowhere to send anyone. They are not on the walk above.")
        w("")
        for it in unplaced:
            w(f"- [ ] {it['facility']} — ward {it['ward']}, village "
              f"\"{it['village']}\", reported *{it['status']}*")
        w("")

    if deferred:
        w("---")
        w("")
        w("## Not now")
        w("")
        w("Outside the conservation area, or multi-day walks. **Do not attempt")
        w("these on this trip.** Listed so it is clear they were not forgotten.")
        w("")
        for r in deferred:
            km = fnum(r["straight_km"])
            dist = f" — about {km:.0f} km in a straight line" if km else ""
            md = "  **multi-day**" if r["multi_day"] == "yes" else ""
            w(f"- {r['from_place']} → {r['to_place']}{dist}{md}  "
              f"`{r['route_id']}`")
        w("")

    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    print(f"  {len(route)} stops, {total_pts} points, {len(jobs)} legs to record")
    print(f"  {len(missed)} legs not on the route, {len(deferred)} deferred")


if __name__ == "__main__":
    main()
