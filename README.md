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
export GOOGLE_OAUTH_TOKEN='ya29...'  # see scripts/fetch_from_drive.sh header
./scripts/fetch_from_drive.sh        # pull anything new from Drive into data/raw
python3 scripts/slim_kmz.py          # extract geometry from photo-laden KMZ files
python3 scripts/inspect_sources.py   # report structure of everything in data/raw
python3 scripts/merge_tracks.py      # normalise to data/processed/tracks.gpkg
python3 scripts/make_maps.py         # render the three outputs
```

Requires `geopandas`, `matplotlib`, `folium`, `adjustText`.

### Getting files from Drive

`drive.google.com` is blocked from the sandbox, but **`www.googleapis.com` is
not** — so the Drive API works with an access token and no local step:

1. https://developers.google.com/oauthplayground/, scope
   `https://www.googleapis.com/auth/drive.readonly`
2. Authorise, exchange for tokens, copy the `ya29...` access token
3. `export GOOGLE_OAUTH_TOKEN='ya29...' && ./scripts/fetch_from_drive.sh`

Tokens last about an hour and are read from the environment only — never
written to disk. `scripts/sync_from_drive.sh` does the same job from your own
machine via rclone if you would rather not mint a token.

`scripts/drive_diff.py` reports what is in Drive but not yet in `data/raw`,
against the listing in `data/drive_manifest.tsv`.

## The data

26 source files → **24 tracks, 373 km**, plus 25 photo waypoints. Everything
arrived in WGS84 (EPSG:4326); lengths are computed in EPSG:32755 (UTM zone 55S).
See `data/processed/tracks_summary.csv` for the full table.

Longest ten:

| Track | Source | Travelled | Recorded |
| ----- | ------ | --------- | -------- |
| Popondetta to Anatua Road | KMZ | 151.0 km | — |
| Jorua to Girua Track | KMZ | 40.9 km | — |
| Gadzot Road | GPX | 29.5 km | 2025-11-16 |
| David's track record from Jorura to Afore | KMZ | 23.1 km | — |
| Cropping Calendar Survey Track to Kuhara | GPX | 16.2 km | 2025-12-12 |
| David Jajiba's track recording, Gora to Jorura | KMZ | 16.2 km | — |
| Kiara to Grid 63 and back | GPX | 15.9 km | 2026-04-18 |
| Afore Guest house | GPX | 11.6 km | 2026-02-01 |
| David's track record, Itokama to Umuate | KMZ | 9.5 km | — |
| Koruwo to Anatua 1 | GPX | 9.1 km | 2026-02-01 |

Many tracks come from a **Cropping Calendar Survey** and are named accordingly;
one (`Anatua-Gadzot-Umbuwara`) is recorded as cycling rather than walking.

### Things the pipeline handles automatically

- **Degenerate geometry.** `Itokama_to_Umuate_Davids_track_record.kmz` holds one
  Placemark with two LineStrings: a one-point stub and the real 756-point track.
  GEOS rejects the whole feature over the stub, silently losing the track, so
  the merge falls back to parsing the KML directly and keeps only parts with two
  or more points. Worth 9.5 km that would otherwise have vanished.
- **Duplicate recordings.** `Kaura_to_Koeno_2025-12-09_08-25.gpx` and
  `Kaura_to_Kuhara_2025-12-09_08-25.gpx` have byte-identical geometry and
  timestamps; they differ only in the Locus export time in their metadata. The
  merge drops one and reports it. **Note the filenames disagree with the
  content** — both embed the name "Kaura to Kuhara", so the `Koeno` filename
  looks wrong and is worth correcting at source.
- **Oversized KMZ.** `Russell_Muraba_Trek_Record_2.kmz` is 141 MB, of which 57
  JPEGs; its `doc.kml` is 43 KB. `scripts/slim_kmz.py` extracts the geometry,
  the `.kml` is committed, and the original is gitignored (it exceeds GitHub's
  100 MB blob limit). Re-fetch it if the photos are needed.
- **Points vs lines.** That same file is 25 *points* — photo waypoints, not a
  track. They go to a separate `waypoints` layer and are excluded from track
  counts and lengths.

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

Colour encodes *provenance* (GPX / KMZ / GPKG), not individual track. Two dozen
tracks are far past what a categorical palette can keep separable — the
validated all-pairs ceiling is four slots — so identity is carried by the facet
panels and by tooltips in the HTML. The overview direct-labels only the eight
longest (`LABEL_COUNT` in `make_maps.py`); labelling all 24 makes it unreadable.

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
