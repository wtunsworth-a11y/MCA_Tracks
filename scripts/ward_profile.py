"""The Afore LLG Ward Profile population, matched to the places we map.

Two separate jobs, kept apart on purpose:

  load_profile()   - the 79 villages as supplied, nothing reconciled
  match_to_mapped()- which of them correspond to a position we hold

The matching is not a simple name lookup. The Ward Profile writes "Afore
Village" where we hold Afore, "Anatua 1" and "Anatua 2" where we hold one
Anatua, "Numba/Siurana" for Numba, and a dozen spellings we carry under
another name. Every rule here was confirmed in the field rather than guessed,
and the ones still unconfirmed are deliberately NOT matched - a wrong join
would attach several hundred people to the wrong dot.

HOUSEHOLD COUNTS DO NOT AGREE between this and MCA_Village_Locations.csv:
3,617 here against 3,837 there, and over 79 villages against 46. They are
different instruments - this enumerates by ward, ours scales est_hh from
1,163 recorded points - so they are never summed together.
"""
from pathlib import Path
import csv
import re

ROOT = Path(__file__).resolve().parent.parent
POP = ROOT / "data" / "reference" / "afore_llg_population.csv"


def load_profile():
    """The Ward Profile rows, as supplied. Total rows are dropped."""
    if not POP.exists():
        return []
    with POP.open() as fh:
        rows = [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))
                if r["village"] and not r["village"].startswith("Total")]
    for r in rows:
        r["households"] = int(r["households"] or 0)
        r["population"] = int(r["population"] or 0)
    return rows


def variants(name):
    """The ways the Ward Profile writes a name that we may file differently."""
    yield name
    bare = re.sub(r"\s*\b(village|station|govt station|government station)\b\s*$",
                  "", name, flags=re.I).strip()
    if bare and bare != name:
        yield bare
    m = re.match(r"(.+?)\s*[12]$", name)        # Anatua 1, Sila 2, Kawowoki 1
    if m:
        yield m.group(1).strip()
    for part in re.split(r"[/()]", name):       # Numba/Siurana, Buanfuo (Jakiro)
        part = part.strip()
        if part and part != name:
            yield part


def match_to_mapped(mapped, places, aliases, candidates, best_tier):
    """-> (joined, unmatched).

    joined maps a mapped place name to the Ward Profile rows that belong to
    it, which is one-to-many: Kawowoki 1 and Kawowoki 2 are both Kawowoki,
    and their households have to be added together or the dot understates the
    place by half.
    """
    def canon(n):
        al = aliases.get(str(n).strip().lower())
        return al["to"] if al and al["to"] else n

    def find(name):
        for v in variants(name):
            if v.lower() in mapped:
                return mapped[v.lower()]["name"]
            hit = best_tier(candidates(v, places, aliases))
            if hit:
                c = canon(hit[0]["name"])
                if c.lower() in mapped:
                    return c
        return None

    joined, unmatched = {}, []
    for r in load_profile():
        name = find(r["village"])
        if name:
            joined.setdefault(name, []).append(r)
        else:
            unmatched.append(r)
    return joined, unmatched


def totals(joined):
    """Households and people that reconcile to a mapped position."""
    hh = sum(r["households"] for rows in joined.values() for r in rows)
    pop = sum(r["population"] for rows in joined.values() for r in rows)
    return hh, pop
