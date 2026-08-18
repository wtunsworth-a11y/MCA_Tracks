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
        drive = {row["name"]: row for row in csv.DictReader(fh, delimiter="\t")}

    local = {p.name: p.stat().st_size for p in RAW.iterdir() if p.is_file() and p.name != ".gitkeep"}

    # Notes and READMEs live in the folder too; they are not track data and
    # cannot be fetched with alt=media, so they are listed separately.
    track_exts = (".gpx", ".kmz", ".kml", ".gpkg")
    non_track = sorted(n for n in drive if not n.lower().endswith(track_exts))

    missing, changed = [], []
    for name, row in sorted(drive.items()):
        if not name.lower().endswith(track_exts):
            continue
        size = int(row["size"])
        if name not in local:
            missing.append((name, size))
        elif local[name] != size:
            changed.append((name, local[name], size))

    # A .kml extracted from an oversized .kmz by slim_kmz.py is derived, not
    # stray, so it should not be reported as unexpected.
    derived = {
        name
        for name in local
        if name.endswith(".kml") and f"{Path(name).stem}.kmz" in drive
    }
    extra = sorted(
        set(local) - set(drive) - derived - {"drive-download-20260817T080903Z-1-001.zip"}
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
    for name, row in drive.items():
        by_size.setdefault(int(row["size"]), []).append(name)
    dupes = {s: n for s, n in by_size.items() if len(n) > 1}
    if dupes:
        print("POSSIBLE DUPLICATES — identical byte size in Drive:")
        for size, names in sorted(dupes.items()):
            print(f"  {human(size)}:")
            for n in sorted(names):
                print(f"      {n}")
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
