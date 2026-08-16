# MCA_Tracks

Mapping of tracks (walking trails, patrol routes, hunting tracks) across the
Managalas Conservation Area, Oro Province, Papua New Guinea.

## Status

Awaiting source data. The Drive folder is created but empty as of 2026-08-16:
https://drive.google.com/drive/folders/1UR9_fpkrn_I2lCs8O2yZsC7u9xCv1bsy

## Layout

| Path              | Purpose                                                   |
| ----------------- | --------------------------------------------------------- |
| `data/raw/`       | Source files exactly as received (GPX / KML / CSV / shp). Not edited. |
| `data/processed/` | Cleaned, merged, reprojected track data.                  |
| `outputs/`        | Rendered maps and exports.                                |
| `scripts/`        | Ingest, cleaning and mapping code.                        |

Raw and processed data are gitignored by default — track files can be large and
may carry sensitive location information (e.g. hunting sites, settlement
locations). Decide deliberately before committing any of it.

## Open questions

- Source format of the track data (GPS unit exports, KoboToolbox/ODK, QGIS project, hand-digitised?)
- Coordinate reference system of the source, and target CRS for output
- Attributes carried per track (date, recorder, village, purpose, party size)
- Intended map outputs — static figures for a report, or an interactive web map
- Whether any tracks are sensitive and should be generalised or withheld
