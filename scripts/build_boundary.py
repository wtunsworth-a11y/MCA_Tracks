"""Build the Managalas Conservation Area boundary polygon.

There is no boundary shapefile in the Drive folder — only PDFs. But
"Managalas CA boundary map with survey coordinates.pdf" carries the gazetted
20-point survey table in degrees/minutes/seconds, which is the authoritative
description of the boundary. Those points are transcribed here.

Important: this is the *survey* boundary — 20 points joined by straight lines,
as gazetted. It is not a detailed boundary following ridges or rivers, so
expect it to cut across terrain. Treat inside/outside calls near the edge as
approximate, and replace this with a proper boundary layer if one exists.

Source: Drive file 1Vz53FTL9h92oJ0Wcj_U9aeUC04tXafJs
Writes data/processed/mca_boundary.gpkg (layer "boundary").
"""

import warnings
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

WGS84 = "EPSG:4326"
UTM55S = "EPSG:32755"

# (point, lon d m s, lat d m s) — latitudes are south, so negated below.
SURVEY_POINTS = [
    (1, (148, 2, 20.33736), (9, 22, 55.9956)),
    (2, (148, 3, 54.24624), (9, 27, 39.77334)),
    (3, (148, 6, 56.58732), (9, 28, 27.87906)),
    (4, (148, 10, 55.63056), (9, 24, 18.174276)),
    (5, (148, 16, 14.81232), (9, 22, 25.24602)),
    (6, (148, 20, 23.16552), (9, 19, 36.860628)),
    (7, (148, 23, 50.54712), (9, 16, 58.029888)),
    (8, (148, 27, 58.29876), (9, 15, 42.1668)),
    (9, (148, 34, 58.60308), (9, 11, 0.061764)),
    (10, (148, 31, 5.89044), (9, 3, 36.7596)),
    (11, (148, 25, 57.84564), (8, 59, 44.108844)),
    (12, (148, 25, 19.98732), (8, 52, 31.407924)),
    (13, (148, 16, 8.28408), (8, 51, 57.429648)),
    (14, (148, 10, 22.3806), (8, 58, 38.066556)),
    (15, (148, 6, 31.25412), (9, 3, 38.343852)),
    (16, (148, 7, 59.11464), (9, 6, 24.283692)),
    (17, (148, 10, 11.3016), (9, 7, 50.416176)),
    (18, (148, 8, 13.3638), (9, 10, 5.541528)),
    (19, (148, 7, 11.622), (9, 14, 32.633556)),
    (20, (148, 3, 37.90836), (9, 19, 32.122236)),
]


def dms(degrees, minutes, seconds):
    return degrees + minutes / 60 + seconds / 3600


def main():
    coords = [(dms(*lon), -dms(*lat)) for _, lon, lat in SURVEY_POINTS]
    polygon = Polygon(coords)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    boundary = gpd.GeoDataFrame(
        [{
            "name": "Managalas Conservation Area",
            "source": "survey coordinates, Managalas CA boundary map PDF",
            "vertices": len(coords),
        }],
        geometry=[polygon],
        crs=WGS84,
    )

    area_km2 = boundary.to_crs(UTM55S).area.iloc[0] / 1e6
    boundary["area_km2"] = round(area_km2, 1)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "mca_boundary.gpkg"
    boundary.to_file(out, layer="boundary", driver="GPKG")

    minx, miny, maxx, maxy = boundary.total_bounds
    print(f"{len(coords)} survey points -> polygon, {area_km2:,.0f} km2")
    print(f"bounds  lon {minx:.4f} .. {maxx:.4f}   lat {miny:.4f} .. {maxy:.4f}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
