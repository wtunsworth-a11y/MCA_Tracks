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
