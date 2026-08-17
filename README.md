# MCA_Tracks

Mapping of tracks (walking trails, patrol routes, roads) across the Managalas
Conservation Area, Oro Province, Papua New Guinea.

Source data: https://drive.google.com/drive/folders/1UR9_fpkrn_I2lCs8O2yZsC7u9xCv1bsy

## Outputs

| File | What it is |
| ---- | ---------- |
| `outputs/managalas_tracks.png` | Overview map, all tracks, projected to UTM 55S |
| `outputs/managalas_tracks_facets.png` | One panel per track on a shared extent |
| `outputs/managalas_tracks.html` | Interactive map — toggle tracks, OSM or satellite basemap |
| `data/processed/tracks.gpkg` | All tracks merged into one layer (`tracks`) |
| `data/processed/tracks_summary.csv` | Table of names, sources, dates, lengths |

Open the HTML in a browser; the basemap tiles load client-side.

## Pipeline

```
python3 scripts/inspect_sources.py   # report structure of everything in data/raw
python3 scripts/merge_tracks.py      # normalise to data/processed/tracks.gpkg
python3 scripts/make_maps.py         # render the three outputs
```

Requires `geopandas`, `matplotlib`, `folium`, `adjustText`.

## The data

Seven source files, 12 features, 7 real-world tracks, 252 km total. Everything
arrived in WGS84 (EPSG:4326); lengths are computed in EPSG:32755 (UTM zone 55S).

| Track | Source | Travelled | Recorded |
| ----- | ------ | --------- | -------- |
| Popondetta to Anatua Road | KMZ | 151.0 km | — |
| Jorua to Girua Track | KMZ | 40.9 km | — |
| Gadzot Road | GPX | 29.5 km | 2025-11-16 |
| Kiara to Grid 63 and back | GPX | 15.9 km | 2026-04-18 |
| Koruwo to Anatua 1 | GPX | 9.1 km | 2026-02-01 |
| Sakarina–Numba–Kaura (6 segments) | GPKG | 4.3 km | — |
| Anatua to Serefuna | GPX | 1.8 km | 2026-02-04 |

### Things to know before using this

- **Lengths are distance travelled, not route length.** Several tracks
  backtrack. `Kiara to Grid 63 and back` begins and ends 520 m apart, so its
  real trail is roughly half the 15.9 km logged. `Popondetta to Anatua Road`
  and `Gadzot Road` both have end-to-end separation of only 0.26 × their
  length. Don't quote these figures as trail distances without deciding how to
  handle the doubling.
- **The GeoPackage is a different kind of record.** Its six segments sit ~6 km
  east of everything else with no overlap, span only 4.3 km across 173
  vertices, and share a single name (`HBMS - 1108025Z6`, a device code). The
  other sources reach 3,147 vertices for one track. Treat it as a separate
  survey, not part of the same network.
- **Two tracks carry no timestamps** (both KMZ). The GPX files are Locus Map
  exports with per-point elevation, time and HDOP.
- **Dates are PNG local time (UTC+10).** GPX timestamps are UTC, which pushes
  afternoon walks onto the previous day if converted naively.
- **Some names were app defaults.** `Popondetta_to_Anatua_Road.kmz` was
  internally "Track Infinity"; one GPX was named only by its timestamp. Names
  were resolved from `desc` or the filename, and the original is kept in the
  `source_name` column.

### Map design note

Colour encodes *provenance* (GPX / KMZ / GPKG), not individual track. Seven
tracks exceed what a categorical palette can keep separable — the validated
all-pairs ceiling is four slots — so individual identity is carried by direct
labels on the overview, by the facet panels, and by tooltips in the HTML. A
consequence: the two KMZ tracks share a colour on the overview, which is what
the facet view is for.

## Layout

| Path | Purpose |
| ---- | ------- |
| `data/raw/` | Source files as received. Not edited. |
| `data/processed/` | Merged, normalised output. |
| `outputs/` | Rendered maps. |
| `scripts/` | Inspect, merge and render. |

Track files are committed here so the sandbox can read them — it has no network
route to Google Drive. **These carry precise location data; review before making
this repository public.**

## Open questions

- Should backtracking be collapsed, so lengths read as trail distance?
- Is the Sakarina–Numba–Kaura GeoPackage meant to be part of this network?
- Are any of these tracks sensitive enough to generalise or withhold?
- Is a printed figure needed, or is the interactive map the deliverable?
