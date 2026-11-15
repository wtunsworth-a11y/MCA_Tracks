"""Building footprints over the MCA, pulled out of Overture Maps.

    python3 scripts/fetch_buildings.py

Writes data/reference/mca_buildings.geojson.

WHERE THIS COMES FROM, and why it is the only route that works.

Four sources were tried on 12 Nov 2026:

    Google Open Buildings   NO PNG COVERAGE AT ALL. The S2 level-4 tile that
                            holds the plateau is 691, and 691 does not exist
                            in the bucket. Nor does it for Port Moresby, which
                            is the same tile, or Lae. The method was checked
                            against Jakarta, Nairobi and Dhaka, which are all
                            present, so this is coverage and not a bad tile id.
    Microsoft ML footprints blocked at the proxy (minedbuildings on Azure)
    Geofabrik OSM extracts  blocked at the proxy
    Overture Maps on S3     WORKS, anonymously

Overture's buildings theme is 512 files and 277 GB, which sounds impossible to
query and is not. Each file carries per-row-group statistics on a bbox struct,
and the data is sorted spatially, so reading 512 footers - about two minutes -
finds the three row groups that touch the plateau. Nothing else is downloaded.

The polygons are OpenStreetMap-sourced. Coverage is partial and concentrated
in the north-west: 2,375 buildings, of which about 1,431 fall within 500 m of
a village we already have and 946 belong to no village in our list at all.
There is nothing within 5 km of Awaru, so this cannot place every settlement.

duckdb is the usual tool for this and is no use here: its httpfs and spatial
extensions download over plain HTTP from extensions.duckdb.org, which the
proxy refuses. pyarrow reads the parquet directly and needs no extension.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "reference" / "mca_buildings.geojson"

RELEASE = "2026-10-21.0"
BASE = (f"overturemaps-us-west-2/release/{RELEASE}"
        f"/theme=buildings/type=building")
# The MCA with a margin. Deliberately generous: a building just outside the
# boundary still tells you where a settlement is.
WEST, EAST, SOUTH, NORTH = 148.15, 148.50, -9.40, -9.00


def candidate_row_groups(s3, pq):
    """The row groups whose bbox statistics overlap the window."""
    files = sorted(i.path for i in s3.get_file_info(
        __import__("pyarrow.fs", fromlist=["FileSelector"]).FileSelector(BASE))
        if i.path.endswith(".parquet"))
    hits, t0 = [], time.time()
    for n, path in enumerate(files, 1):
        try:
            md = pq.ParquetFile(s3.open_input_file(path)).metadata
        except Exception as e:                       # a transient S3 read
            print(f"    skipped {path.rsplit('/', 1)[-1][:28]}: {e}")
            continue
        for g in range(md.num_row_groups):
            rg, b = md.row_group(g), {}
            for c in range(rg.num_columns):
                p = rg.column(c).path_in_schema
                if p.startswith("bbox."):
                    st = rg.column(c).statistics
                    b[p[5:]] = (st.min, st.max)
            if not b:
                continue
            if (b["xmax"][1] >= WEST and b["xmin"][0] <= EAST
                    and b["ymax"][1] >= SOUTH and b["ymin"][0] <= NORTH):
                hits.append((path, g))
        if n % 128 == 0:
            print(f"    scanned {n}/{len(files)} footers, "
                  f"{len(hits)} candidate row groups, {time.time() - t0:.0f}s")
    return hits


def main():
    try:
        import pyarrow.compute as pc
        import pyarrow.fs as fs
        import pyarrow.parquet as pq
    except ImportError:
        print("!! pyarrow is needed:  pip install -r requirements.txt",
              file=sys.stderr)
        return 1
    from shapely import wkb
    from shapely.geometry import mapping

    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")
    print(f"scanning Overture {RELEASE} buildings footers ...")
    hits = candidate_row_groups(s3, pq)
    if not hits:
        print("!! no row group overlaps the MCA - has the release moved?",
              file=sys.stderr)
        return 1
    print(f"  {len(hits)} row groups to read")

    feats = []
    by_file = {}
    for path, g in hits:
        by_file.setdefault(path, []).append(g)
    for path, groups in by_file.items():
        tb = pq.ParquetFile(s3.open_input_file(path)).read_row_groups(
            groups, columns=["id", "geometry", "bbox", "subtype", "class"])
        bx = tb.column("bbox").combine_chunks()
        mask = pc.and_(
            pc.and_(pc.greater_equal(bx.field("xmax"), WEST),
                    pc.less_equal(bx.field("xmin"), EAST)),
            pc.and_(pc.greater_equal(bx.field("ymax"), SOUTH),
                    pc.less_equal(bx.field("ymin"), NORTH)))
        sub = tb.filter(mask)
        ids = sub.column("id").to_pylist()
        sts = sub.column("subtype").to_pylist()
        cls = sub.column("class").to_pylist()
        for i, blob in enumerate(sub.column("geometry").combine_chunks()):
            feats.append({
                "type": "Feature",
                "properties": {"id": ids[i], "subtype": sts[i], "class": cls[i]},
                "geometry": mapping(wkb.loads(blob.as_py()))})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        json.dump({
            "type": "FeatureCollection",
            "_provenance": (
                f"Overture Maps release {RELEASE}, theme=buildings, read "
                f"anonymously from s3://overturemaps-us-west-2 by "
                f"scripts/fetch_buildings.py. OpenStreetMap-sourced. Coverage "
                f"over the MCA is PARTIAL and concentrated in the north-west - "
                f"there is nothing within 5 km of Awaru. Google Open Buildings "
                f"has no PNG coverage at all; Microsoft's footprints and "
                f"Geofabrik are blocked at the proxy."),
            "features": feats}, fh)
    print(f"wrote {OUT.relative_to(ROOT)} — {len(feats):,} building polygons, "
          f"{OUT.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
