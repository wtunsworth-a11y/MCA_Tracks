"""Compare the Google Drive folder listing against what is in data/raw.

The sandbox cannot fetch from Drive, but it can *list* it through the Drive
connector. So Claude refreshes data/drive_manifest.tsv from that listing and
this script says exactly which files still need to come across — no guessing
which ones changed.

Also flags same-size duplicates and files too large for a normal git push.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "drive_manifest.tsv"

GITHUB_BLOB_LIMIT = 100 * 1024 * 1024  # hard push rejection
GITHUB_WARN_LIMIT = 50 * 1024 * 1024  # GitHub warns above this


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024


def main():
    if not MANIFEST.exists():
        sys.exit(f"no manifest at {MANIFEST} — ask Claude to refresh it from Drive")

    with MANIFEST.open() as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    # Keyed by drive_id, not by name. Russell uploaded the same KMZ twice on
    # 27 Oct 2026 under one name - 1.28 GB with its photos and 7.3 MB without
    # - and keying on the name silently dropped the first, so the folder read
    # as 41 files when it held 42 and the big one never reached this report.
    drive = {row["drive_id"]: row for row in rows}
    same_name = {}
    for row in rows:
        same_name.setdefault(row["name"], []).append(row)
    collisions = {n: rs for n, rs in same_name.items() if len(rs) > 1}

    local = {p.name: p.stat().st_size for p in RAW.iterdir() if p.is_file() and p.name != ".gitkeep"}

    # Notes and READMEs live in the folder too; they are not track data and
    # cannot be fetched with alt=media, so they are listed separately.
    track_exts = (".gpx", ".kmz", ".kml", ".gpkg")
    non_track = sorted({r["name"] for r in rows
                        if not r["name"].lower().endswith(track_exts)})

    missing, changed = [], []
    for row in sorted(rows, key=lambda r: r["name"]):
        name = row["name"]
        if not name.lower().endswith(track_exts):
            continue
        size = int(row["size"])
        if name not in local:
            missing.append((name, size))
        elif local[name] != size:
            changed.append((name, local[name], size))

    drive_names = set(same_name)

    # A .kml extracted from an oversized .kmz by slim_kmz.py is derived, not
    # stray, so it should not be reported as unexpected.
    derived = {
        name
        for name in local
        if name.endswith(".kml") and f"{Path(name).stem}.kmz" in drive_names
    }
    extra = sorted(
        set(local) - drive_names - derived - {"drive-download-20260817T080903Z-1-001.zip"}
    )

    print(f"Drive: {len(drive)} files    local data/raw: {len(local)} files\n")

    if missing:
        total = sum(s for _, s in missing)
        print(f"NEEDED — in Drive, not here ({len(missing)} files, {human(total)}):")
        for name, size in sorted(missing, key=lambda r: -r[1]):
            flag = ""
            if size >= GITHUB_BLOB_LIMIT:
                flag = "  <-- EXCEEDS GitHub's 100 MB limit, cannot be pushed normally"
            elif size >= GITHUB_WARN_LIMIT:
                flag = "  <-- over 50 MB, GitHub will warn"
            print(f"  {human(size):>10}  {name}{flag}")
        print()

    if changed:
        print(f"CHANGED — different size here vs Drive ({len(changed)}):")
        for name, here, there in changed:
            print(f"  {name}: local {human(here)} vs Drive {human(there)}")
        print()

    if extra:
        print(f"LOCAL ONLY — not in the Drive listing ({len(extra)}):")
        for name in extra:
            print(f"  {name}")
        print()

    # Same-size pairs are worth a look: Locus can save one track twice.
    by_size = {}
    for row in rows:
        by_size.setdefault(int(row["size"]), []).append(row["name"])
    dupes = {s: n for s, n in by_size.items() if len(n) > 1}
    if dupes:
        print("POSSIBLE DUPLICATES — identical byte size in Drive:")
        for size, names in sorted(dupes.items()):
            print(f"  {human(size)}:")
            for n in sorted(names):
                print(f"      {n}")
        print()

    if collisions:
        print("SAME NAME, DIFFERENT FILES — one of these cannot be saved to "
              "data/raw without overwriting the other:")
        for name, rs in sorted(collisions.items()):
            print(f"  {name}")
            for r in sorted(rs, key=lambda r: -int(r["size"])):
                print(f"      {human(int(r['size'])):>10}  {r['modified']}  "
                      f"{r['drive_id']}")
        print()

    if non_track:
        print(f"NOT TRACK DATA — in the folder, not fetched ({len(non_track)}):")
        for name in non_track:
            print(f"  {name}")
        print()

    if not missing and not changed:
        print("Up to date — every Drive file is present locally at the same size.")


if __name__ == "__main__":
    main()
