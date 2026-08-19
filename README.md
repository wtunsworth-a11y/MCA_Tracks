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
python3 scripts/merge_tracks.py      # normalise + classify to data/processed/tracks.gpkg
python3 scripts/infer_villages.py    # derive village points from track endpoints
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

28 source files → **28 tracks, 602 km**, plus 25 photo waypoints. Everything
arrived in WGS84 (EPSG:4326); lengths are computed in EPSG:32755 (UTM zone 55S).
See `data/processed/tracks_summary.csv` for the full table.

Longest ten:

| Track | Type | Source | Travelled | Recorded |
| ----- | ---- | ------ | --------- | -------- |
| Popondetta to Anatua Road | Road | KMZ | 151.0 km | — |
| Road Track - Popondetta to Sakarina Junction | Road | GPX | 148.6 km | 2025-07-04 |
| Itokama to Afore Road | Road | GPX | 46.9 km | 2025-07-04 |
| Jorua to Girua Track | Village-to-village track | KMZ | 40.9 km | — |
| Gadzot Road | Road | GPX | 29.5 km | 2025-11-16 |
| road track save | Road | GPX | 27.9 km | 2025-07-04 |
| David's track record from Jorura to Afore | Village-to-village track | KMZ | 23.1 km | — |
| David Jajiba's : Track recording from Gora to Jorura | Village-to-village track | KMZ | 16.2 km | — |
| Cropping Calendar Survey Track to Kuhara | Garden / survey track | GPX | 16.2 km | 2025-12-12 |
| Kiara to Grid 63 and back | Garden / survey track | GPX | 15.9 km | 2026-04-18 |

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
  backtrack: `Kiara to Grid 63 and back` begins and ends 520 m apart, and
  `Popondetta to Anatua Road` and `Gadzot Road` both have end-to-end separation
  of only 0.26 × their length. Point-to-point distances will be tabulated
  separately (see Decisions), so `length_km` is a property of the recording,
  not a trail distance — do not quote it as one.
- **The GeoPackage is a different kind of record**, though it is in scope. Its
  six segments sit ~6 km east of the rest with no overlap, span 4.3 km across
  173 vertices, and share one device code (`HBMS - 1108025Z6`) as a name, where
  other sources reach 3,147 vertices for a single track. Different capture
  method, same network.
- **Two tracks carry no timestamps** (both KMZ). The GPX files are Locus Map
  exports with per-point elevation, time and HDOP.
- **Dates are PNG local time (UTC+10).** GPX timestamps are UTC, which pushes
  afternoon walks onto the previous day if converted naively.
- **Some names were app defaults.** `Popondetta_to_Anatua_Road.kmz` was
  internally "Track Infinity"; one GPX was named only by its timestamp. Names
  were resolved from `desc` or the filename, and the original is kept in the
  `source_name` column.

## Track types

Every track is classified as **Road**, **Village-to-village track** or
**Garden / survey track** — the distinction that matters for reading
disturbance, since a vehicle road and a seasonal garden path are not
comparable pressures.

Classification is derived from track names, which is a heuristic, not ground
truth. Anything ambiguous is flagged (`type_certain = False` in the summary)
and listed when `merge_tracks.py` runs. **To correct one, add a row to
`data/track_types.csv` with `name,type`** — overrides win and are reported.

Known ambiguities: a name like "Track from Awaru to Sigara Road" describes a
track that *ends at* a road, not a road itself, so it is classed as a track;
"Afore Guest house", "Water Source" and "Kiara to Grid 63" have endpoints that
are not villages, so they are classed as garden/survey. Check these six.

## Inferred village locations

Villages were never surveyed directly, but the tracks encode them:
`scripts/infer_villages.py` takes each track's first and last point, clusters
endpoints within 300 m, proposes a name from the track's own name, and takes
the majority within each cluster. Output: `data/processed/villages.gpkg`
(layer `villages`) and `villages.csv`, each row carrying its evidence.

**Treat this as a hypothesis to ground-truth, not a result.** The known
weaknesses:

- **Direction is unrecoverable.** "A to B" is assumed to run A→B. When a track
  was walked B→A both names invert. Where several tracks disagree the majority
  wins — Anatua, backed by four tracks, beat a single contradicting one — but a
  name with no competitor stays wrong. **Popondetta was wrong for this reason
  and is corrected in `data/village_names.csv`**, placed at the northern road
  terminus, which matches the real town to ~250 m. That correction comes from
  outside knowledge, not from these files.
- **Confidence varies enormously.** `Kaura` is backed by 7 tracks; most places
  rest on one. The `tracks`, `agreeing` and `confidence` columns say which is
  which, and the map draws single-track places as hollow markers.
- **`Sakarina` sits at 0.20 confidence** — that cluster is a genuine hub where
  Sakarina, Kaura and Kuhara endpoints all converge, and the name is contested.
- **Not every endpoint is a village.** Some are gardens, water sources or a
  guest house. Nine clusters are unnamed or disputed and go unlabelled.

**To correct a name**, add a row to `data/village_names.csv`:

```csv
lon,lat,village,drop
148.2141,-8.7674,Popondetta,
148.3000,-9.1000,,yes
```

The nearest inferred cluster to each coordinate takes that name; `drop = yes`
removes a bogus cluster. Overrides are reported when the script runs.

### Map design note

Colour encodes **track type**, and line weight follows it too — roads heaviest,
garden paths lightest — so the disturbance hierarchy reads without the legend.
Three types sit inside the validated all-pairs palette ceiling of four slots.

The overview labels **villages**, not tracks: two dozen track names is a wall of
text, and place names are what make the network legible. Filled markers are
places two or more tracks agree on; hollow markers rest on a single track.
Individual tracks are identified in the facet grid and by tooltips in the HTML.

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

## Decisions

- **Distances will be tabulated point-to-point later**, not as along-track
  lengths. So backtracking does not need collapsing and `length_km` stays as
  distance travelled — treat it as a recording property, not a trail distance.
- **Scope: everything inside the MCA boundary is in, plus tracks that connect
  outward** (the roads down toward Popondetta, for instance). The
  Sakarina–Numba–Kaura GeoPackage stays in on that basis, despite sitting ~6 km
  east of the rest with no overlap.
- **Village names will firm up as more recordings arrive.** Weak inferences are
  flagged with their evidence rather than resolved by guesswork; more tracks
  touching the same place will settle them by majority.
- **Disturbance weights come later.** The `type` column on every track is ready
  to carry them when they are decided.

## Open questions

- Six track types are flagged `type_certain = False` — the three
  "Track from X to Y main road" cases (classed as tracks that *end at* a road,
  not roads) plus `Afore Guest house`, `Water Source` and `Kiara to Grid 63`
  (endpoints that are not villages). Override in `data/track_types.csv`.
- **Popondetta** is placed at the northern road terminus from the real town's
  coordinates, not from the track data. The one assertion on the map that did
  not come from these files.
- Are any tracks sensitive enough to generalise or withhold? The repo now holds
  28 precise tracks and 28 inferred settlement locations.

## Would help

- **An MCA boundary polygon.** With it the pipeline could tag every track as
  inside the conservation area or an outward connector, which is the
  distinction named above and is likely to matter for the disturbance surface.
