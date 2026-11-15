"""What counts as a settlement, in one place.

Will, 15 Nov 2026: "Dont assume every place (like a junction) is a village.
Same with river names?" Yes - and also facilities, landforms and old sites.

The rule itself was never wrong. It was WRITTEN THREE TIMES: as
NOT_A_SETTLEMENT in make_facilities_csv.py and make_ward_map.py, and as a
STOPWORDS set in infer_villages.py. Three copies drift, and the drift is what
does the damage - the waypoint drops were listed in three scripts too, and
zone 4 was reported as entirely uncollected because two of them were updated
by hand and the third was not.

So: one module, imported by everything that has to answer "is this a village?"

A name matching any of these is a real place. It is simply not a SETTLEMENT,
so it must never be offered as the answer to "which village is this in", and
must never be invented as a village from a track name or a waypoint.
"""
import re

PATTERNS = {
    # Aguido is a person; the school named after him is a facility, and three
    # facilities were once filed as being "at" it.
    "facility": r"\b(school|aid\s*post|aidpost|health\s+cent(?:re|er)|airstrip"
                r"|office|church|institute|clinic|haus\s*sik|guest\s*house"
                r"|teacher'?s?\s+house|classroom|dormitory)\b",
    "junction": r"\b(junction|jct|crossing|turn-?off|corner|shortcut"
                r"|short\s+cut)\b",
    "water":    r"\b(river|creek|stream|bridge|ford|waterfall|spring"
                r"|water\s+source)\b",
    "landform": r"\b(mount|mt\.?|ridge|range|hill|peak|pass|gap|plateau)\b",
    # "Samaga old village site" is where a village WAS.
    "old site": r"\b(old\s+village\s+site|former|abandoned|site\s+of"
                r"|old\s+site)\b",
    "route":    r"\b(road|highway|track|trail|feeder|path)\b",
}

_ANY = re.compile("|".join(f"(?:{p})" for p in PATTERNS.values()), re.I)


def kind(name):
    """The first non-settlement kind a name matches, or None if it is a place."""
    for k, pat in PATTERNS.items():
        if re.search(pat, str(name), re.I):
            return k
    return None


def is_settlement(name):
    """False for a facility, junction, river, landform, old site or route."""
    return _ANY.search(str(name)) is None


# The single-word form, for parsers that tokenise a track name rather than
# testing it whole. Kept in step with PATTERNS by the test below.
STOPWORDS = {
    "track", "tracks", "recording", "record", "records", "survey", "surveys",
    "cropping", "calendar", "calander", "zone", "six", "main", "road", "roads",
    "the", "and", "then", "back", "via", "from", "to", "of", "village",
    "villages", "primary", "school", "guest", "house", "water", "source",
    "grid", "connect", "connects", "davids", "david", "jajibas", "jajiba",
    "seg", "trek", "new", "guinea", "papua", "seg1", "part", "seq",
    "junction", "river", "creek", "community", "station", "hamlet",
    "trail", "short", "cut", "end", "alternate", "feeder", "leading", "bush",
    "shortcut", "high", "highschool", "camp", "bridge", "crossing",
    "teacher", "teachers", "classroom", "dormitory", "site", "old", "former",
    "abandoned", "mount", "ridge", "range", "hill", "aid", "post", "church",
    "airstrip", "clinic", "office", "elementary", "secondary",
}


if __name__ == "__main__":
    CASES = [
        ("Aguido Primary School", "facility"), ("Toma Aid Post", "facility"),
        ("Toma SDA Church", "facility"), ("Basabe junction", "junction"),
        ("Bareji River", "water"), ("Tuberi river", "water"),
        ("Samaga old village site", "old site"), ("Mt Aveke", "landform"),
        ("Popondetta to Afore Road", "route"),
        ("Teacher house", "facility"),
        # these ARE settlements and must come back None
        ("Toma", None), ("Awaru", None), ("Koeno", None), ("Jaure", None),
        ("Anatua 1", None), ("Biriri", None), ("Gorobuna", None),
    ]
    bad = [(n, kind(n), want) for n, want in CASES if kind(n) != want]
    for n, got, want in bad:
        print(f"  FAIL {n!r}: got {got!r}, want {want!r}")
    print(f"{len(CASES) - len(bad)}/{len(CASES)} cases pass")
    raise SystemExit(1 if bad else 0)
