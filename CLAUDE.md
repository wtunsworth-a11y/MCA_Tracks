# Instructions to myself

## Find out what I have access to. Do not ask Will.

Will, 5 Nov 2026: "stop wasting my time telling you what you have access to.
Check for yourself properly without wasting my time again and again and
again...."

He is right, and it cost him four exchanges over two days. I said satellite
imagery was unreachable, twice, and both times I was wrong. The rules below
come from exactly how I got it wrong, so follow them before telling him
anything is unavailable.

**Never report a capability as unavailable until I have tried to use it and
failed.** Not "I tested three hosts". Tried it, properly, and failed.

**A search API and the data behind it are different hosts.** I tested
`earth-search.aws.element84.com`, got refused, and concluded the whole
Sentinel-2 archive was unreachable. The bucket behind it answers anonymous
requests fine. I tested the doorway and never tried the door.

**An authentication error is not a network block.** Google Maps replying "You
must use an API key" and Earth Engine returning 401 UNAUTHENTICATED mean the
service answered. Reading the response body would have told me that; I read
only the status code and called it blocked.

**Do not generalise from a handful of refusals.** Four blocked hosts say
nothing about the fifth. Enumerate properly: the data bucket, the API, the
CLI, the MCP connector, and the files already in this repository.

**Check formulas against reality.** I computed an MGRS square, searched an
empty one, and concluded there was no coverage. The plateau is in latitude
band L, not M - band M is the equator to 8 S and Managalas is at 9.1 S.
Reading one real raster's bounds settled in seconds what the formula got
wrong twice.

### Known reachable, as of 5 Nov 2026

| Source | Host | Notes |
| --- | --- | --- |
| Sentinel-2 L2A COGs | `sentinel-cogs.s3.us-west-2.amazonaws.com` | anonymous; windowed reads over HTTP; tile **T55LFK** covers the MCA |
| Sentinel-2 2015-16 L1C | `gs://gcp-public-data-sentinel-2` | sparse; no scene over the plateau |
| Sentinel-1 radar | `sentinel-s1-l1c.s3.amazonaws.com` | anonymous |
| Scene search | `api.daac.asf.alaska.edu` | ASF |
| Google Cloud Storage | `storage.googleapis.com`, `gsutil` | public buckets, no credentials |
| Google APIs | `*.googleapis.com` | reachable; Maps and Earth Engine need a key or OAuth token |
| Nominatim | `nominatim.openstreetmap.org` | place and feature search, with geometry |

Blocked at the proxy: Esri, Bing, Google and OSM tile servers, Mapbox,
Sentinel Hub, Copernicus, USGS, Planetary Computer, Overpass, GeoNames,
`earth-search.aws.element84.com`.

Imagery over this plateau is usually clouded - of ten recent Sentinel-2
scenes, four were 100% cloud and only two were clear. Check the scene
classification layer before reporting that something cannot be seen.

## When Russell uploads, these get rebuilt. Not optional.

Will, 7 Nov 2026: "when Russell uploads new data, you WILL update those 2
files". The two are:

    outputs/gis/mca_schools.kml
    outputs/gis/mca_health.kml

They had been going stale, because the weekly routine's pipeline stopped at
the itinerary and never reached the services map. That is fixed in two ways,
and BOTH matter: the routine now runs the whole chain, and the chain is a
script rather than a list of steps in prose that drifts out of date.

    bash scripts/refresh_all.sh

Run it after ANY new field data, tracks or waypoints. It rebuilds the
network, the access model, the checklist, the facilities reconciliation, the
services maps and layers, the itinerary, the questions and the Word
documents, in the one order that works.

A new WAYPOINT drop needs one step first, because the provenance header has
to be written by someone who knows where the file came from:

    python3 scripts/extract_waypoint_kml.py <doc.kml> \
            data/reference/waypoints_<area>.csv

Nothing else needs editing after that. The drops are DISCOVERED by
scripts/waypoint_drops.py, not listed in each script - they used to be listed
in three, and zone 4 was reported as entirely uncollected until two of them
were changed by hand.

Then check the two files above actually changed before saying the update is
done.

## The container is thrown away. The repository is not. Check before panicking.

Will, 15 Nov 2026: "The repo is still there. Please check" - and it was. I had
just told him CLAUDE.md was gone.

An idle cloud container gets reclaimed. The next one starts with a FRESH clone,
and on 15 Nov that clone came up EMPTY: a `.git` with the origin remote set,
no commits, on a branch called `master`. Every file looked deleted. Nothing was
deleted. The session had simply not fetched anything yet.

So when a file, a script or this note appears to be missing at the start of a
session, the FIRST move is not to report it:

    cd /home/user/MCA_Tracks \
      && git fetch origin claude/managalas-track-maps-3xd3bq \
      && git checkout -B claude/managalas-track-maps-3xd3bq FETCH_HEAD

Then look. This is the same rule as the one at the top of this file - do not
report anything as unavailable until I have tried to get it and failed - and
I broke it in the one place where it was most alarming to be wrong.

### The branch layout, so this is never guessed at again

- `claude/managalas-track-maps-3xd3bq` is the working branch AND the GitHub
  default. All work goes here. Checked 15 Nov 2026.
- `main` exists as a snapshot, pushed 15 Nov 2026 at Will's instruction. It is
  there so that anything hard-coded to clone `refs/heads/main` finds something
  instead of coming up empty, which is exactly what broke the restart. It does
  NOT move on its own and it is not where work goes.
- `main` will drift behind the working branch. That is expected. Do not
  "fix" it, do not merge into it and do not open a pull request, unless Will
  asks.
- Nothing that only exists inside the container exists at all. On 12 Nov
  `outputs/*` in .gitignore was swallowing `outputs/gis`, so
  `mca_schools.kml` and `mca_health.kml` had never been committed - the two
  files Will said must be rebuilt on every drop. The 15 Nov rebuild would have
  taken them. Commit the deliverables.

## Working rules he has set

- Cross check names AND positions before announcing anything. A facility named
  for a place is not evidence it stands there: Afore High School is at
  Sakarina, 8.5 km away, and Suwari Primary School is "physically elsewhere".
- Photos never enter this repository. They exceed GitHub's blob limit and show
  identifiable people and precise settlement locations.
- Only the Drive folder `1UR9_fpkrn_I2lCs8O2yZsC7u9xCv1bsy`, and only the
  branch `claude/managalas-track-maps-3xd3bq`.
- `ya29.` tokens are read from the environment, never written to disk.
- The Drive files are shared with four named people, NOT "anyone with the
  link" (checked 5 Nov 2026). So an API key alone will not open them: a key
  works only on public files. Do not suggest link-sharing them either - they
  hold precise settlement locations and identifiable people. What works
  without a paste every time is an OAuth REFRESH token plus client id and
  secret in the environment, which mints access tokens on demand and never
  expires.
- Do not filter a Drive listing by `modifiedTime`: it has returned nothing
  while the files were sitting in the folder. List it all and diff the manifest.
- No unsolicited analysis. Answer what was asked.
