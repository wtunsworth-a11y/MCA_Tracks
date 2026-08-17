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

# Anything smaller is fine as-is; the pipeline reads KMZ directly.
THRESHOLD_BYTES = 40 * 1024 * 1024
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
        slim(path)


if __name__ == "__main__":
    sys.exit(main())
