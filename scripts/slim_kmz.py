"""Extract geometry from oversized KMZ files.

A KMZ recorded with photos attached is mostly JPEGs — one here is 141 MB, of
which the doc.kml holding every coordinate is 43 KB. GitHub rejects blobs over
100 MB, and the imagery is not needed to draw a map, so pull the KML out and
let the pipeline read that instead.

The original stays in data/raw (gitignored); the extracted .kml is committed.
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# Anything smaller is fine as-is; the pipeline reads KMZ directly. Well below
# GitHub's 100 MB limit on purpose: a KMZ past a few MB is carrying photos, and
# there is no reason to keep those in git when the geometry is a few tens of KB.
THRESHOLD_BYTES = 5 * 1024 * 1024
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def slim(path):
    with zipfile.ZipFile(path) as z:
        kml_entries = [i for i in z.infolist() if i.filename.lower().endswith(".kml")]
        if not kml_entries:
            print(f"  !! {path.name}: no .kml inside, skipping")
            return None

        # A KMZ's root document is conventionally doc.kml; fall back to the
        # largest KML if it is named something else.
        entry = next(
            (i for i in kml_entries if i.filename.lower() == "doc.kml"),
            max(kml_entries, key=lambda i: i.file_size),
        )
        images = sum(1 for i in z.infolist() if i.filename.lower().endswith(IMAGE_SUFFIXES))
        payload = z.read(entry.filename)

    out = path.with_suffix(".kml")
    out.write_bytes(payload)
    saved = path.stat().st_size - out.stat().st_size
    print(
        f"  {path.name}: {path.stat().st_size:,} bytes ({images} images) "
        f"-> {out.name} {out.stat().st_size:,} bytes (saved {saved:,})"
    )
    return out


def ignore_original(path):
    """Add the fat original to .gitignore so it never enters the repo.

    data/raw/*.kmz is un-ignored generally, so each photo-laden file needs its
    own exclusion. Doing it here keeps the rule beside the reason for it.
    """
    gitignore = ROOT / ".gitignore"
    entry = f"data/raw/{path.name}"
    text = gitignore.read_text() if gitignore.exists() else ""
    if entry in text:
        return
    marker = "# Photo-laden KMZ originals — geometry is committed as the extracted .kml\n"
    if marker not in text:
        text += f"\n{marker}"
    text += f"{entry}\n"
    gitignore.write_text(text)
    print(f"    added to .gitignore: {entry}")


def main():
    targets = [
        p
        for p in sorted(RAW.glob("*.kmz"))
        if p.stat().st_size >= THRESHOLD_BYTES and not p.with_suffix(".kml").exists()
    ]
    if not targets:
        print("No oversized KMZ files needing extraction.")
        return

    print(f"Extracting geometry from {len(targets)} oversized KMZ file(s):")
    for path in targets:
        if slim(path) is not None:
            ignore_original(path)


if __name__ == "__main__":
    sys.exit(main())
