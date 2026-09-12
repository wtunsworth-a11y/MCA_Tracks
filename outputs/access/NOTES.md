# Managalas market access — method, sources and what to be careful of

Replaces Figure 8, which plotted village GPS points and joined market stops with
straight lines. Every distance here is measured along a route that somebody has
actually travelled and recorded.

---

## Coordinate reference systems

| Purpose | CRS |
|---|---|
| All distance, routing and area computation | EPSG:32755 — WGS 84 / UTM zone 55S, metres |
| All delivered GeoJSON and CSV coordinates | EPSG:4326 — WGS 84 lat/lon |

## Digital elevation model

**Copernicus DEM GLO-30**, 30 m, tiles `S09_00_E148_00` and `S10_00_E148_00`,
downloaded from the public AWS mirror. Used for three things: walking time,
road gradient, and the hillshade behind both figures.

Walking time is **Tobler's hiking function**, not a flat speed:
W = 6·exp(−3.5·|S + 0.05|) km/h, S being the slope. That is 5.0 km/h on the
flat, 2.3 km/h up a 20 % climb and 3.9 km/h down one. A flat 4 km/h would have
understated every climb on this plateau.

---

## Deliverable 1 — the road network

### OpenStreetMap could not be used

Every OSM endpoint is unreachable from the environment this was built in. Tested
and refused: `overpass-api.de`, `overpass.kumi.systems`, `download.geofabrik.de`,
`api.openstreetmap.org`, `tile.openstreetmap.org`. Digitising from satellite
imagery was equally impossible — no basemap could be fetched either.

**This is stated rather than worked around.** The network below has not been
cross-checked against OSM, and should be before publication if anyone has
unrestricted network access.

### What was used instead

The project's own GPS recordings, which the brief lists as an acceptable source
and which are in fact better here: they are the road as actually travelled.

**Track names could not be used to identify roads.** Locally a foot track is
called a road. Seven of the fifteen recordings whose name contains "road" are
walked, including *Bioi village to Omajeap main road* and *Kuheine to Dakanatam
main road*. Classification is therefore by measurement, in this order:

1. **GPS speed**, from per-point timestamps. Walked recordings measure 2.7–4.4
   km/h median and never exceed 12 km/h; driven ones 11.7–15.1 km/h with half
   their moving time above 12 km/h. Nothing falls between 4.4 and 11.7, so the
   cut sits in the middle of an empty band.
2. **Overlap with a proven road** — a second recording of a road is a road. This
   is what identifies *Popondetta to Anatua Road*: 151 km, no timestamps, running
   along a GPX driven at 15 km/h.
3. **Gradient**, one-sidedly. Every speed-confirmed road is ≤ 15.8 % at the 85th
   percentile; foot tracks reach 36.9 %. They overlap between 11 and 16 %, so
   gradient can rule a road *out* but never *in*.
4. **The 1973 T683 topographic sheets**, where the surveyors drew road, vehicle
   track and foot track as separate classes. Weakest, since a road may have been
   built since.

Every feature in `mca_roads.geojson` carries `mode_evidence` naming the rule that
classified it, plus its measured speed and gradient where those exist.

**Result: 472 km of motorable road, 405 km of foot track.**

Two promotion thresholds were tightened after the first pass, because the
distribution of the evidence showed they were too loose. The overlap shares that
promoted a track to a road are sharply bimodal: 23 sit at 98–100 %, which is a
second recording of the same road, and 4 sit at 68–85 %, which is a foot track
running alongside a road for part of its way. One of the loose four is named
*Siribu Bush Track*, and it was what made Siribu look road-served. The overlap
bar is now 0.95. Exactly one feature was promoted by the 1973 rule, at 52 %, and
that too was at Siribu; that bar is now 0.70.

`surface` and `tracktype` are written as `unknown`. They are not recorded in the
source data and were not going to be guessed.

### Field knowledge overrides the measurement

`data/access_overrides.csv` records statements from someone who knows the ground,
and they outrank the automated rules.

**Yoivi and Siribu have track access only at present, upgradeable to road.**

The measurement could not have established this on its own, and it is worth being
clear why. Siribu's nearest road is 1,476 m away once the loose promotions are
removed — consistent with the override. Yoivi still measures 25 m from a road a
vehicle was driven along at road speed, but that is 25 m from a *coordinate the
brief rounded to two decimal places*, about ±1.1 km, so the proximity does not
establish access either. Rather than move a threshold until the numbers agreed,
both stops are marked track-only in the data and drawn hollow on both figures.

They are removed from the road routing entirely — a stop a vehicle cannot reach
cannot serve anyone by road. They remain market stops: people still walk in, and
the walking figures still use them.

### Independent check on the network

The brief states which villages the road must and must not reach. Nothing about
zones was encoded in the method, and the network reproduces the split exactly:

- **Must reach** — Itokama, Umbuara, Koruwo, Tabuane, Kaura, Afore, Manusi: all
  within 1.4 km of the network, most within 80 m. Siribu is the exception and is
  discussed above: the brief lists it as road-connected, the field correction
  says track only, and the tightened classification puts its nearest road 1,476 m
  away — the two agree against the brief.
- **Must not reach** — Suari, Jaure, Aiari, Gewoya, Toma, Biriri, Kero, Kinando,
  Borohojo: all 7.9 to 16.8 km away.

No road is drawn into Zones 4, 9 or 10.

---

## Deliverable 2 — road distance and service areas

`road_km` is distance **along the road**, node to node on a graph built by noding
the road lines at their intersections. The walk from a village to wherever it
meets the road is reported separately as `offroad_to_road_m` rather than folded
in — folding it in made Kaura, itself a market stop 1.4 km off the road, come out
as 1.4 km from itself.

A village further than 2 km from the network is reported as `road_reachable = no`
with `road_km` blank. It is **not** given a straight-line figure, which would read
as a road distance. The 2 km threshold is safe: the furthest road-served village
is 1.4 km out and the nearest unserved one is 7.9 km.

`mca_service_areas.geojson` holds 12 polygons — three bands × the **four** stops a
vehicle can reach. Yoivi and Siribu have none, because they have no road access. **Each is
a corridor 1 km wide centred on the road, not an area claim.** The width is a
drawing decision so the bands can be read on a 55 km-wide map; at the 300 m first
used they were invisible under the road line. Do not read them as "everywhere
within 500 m of the road is served".

---

## Deliverable 3 — the figures

`fig_mca_map.png` and `fig_market_reach.png`, both 9×7 inches at 200 dpi, DejaVu
Sans 9 pt, no title or figure number inside the image. Palette as specified:
#1F4E79 circuit and stops, #C4C4C4 other villages, #B03A2E roadless zones.

**Zone boundaries are not drawn.** No polygon for them exists in the supplied
data and the brief says to leave them out rather than approximate them.

A third figure, `fig_road_speed.png`, was added on request — see below.

---

## What the numbers say about the report's claims

| Claim in the report | What the road network gives |
|---|---|
| 3,059 households, 87.7 %, served by the circuit | **2,650 of 3,837 households, 69.1 %**, are reachable by road at all |
| — | within 2 km by road: **1,357 hh (35.4 %)** |
| — | within 5 km: **2,079 hh (54.2 %)** |
| — | within 10 km: **2,459 hh (64.1 %)** |
| Siribu covers Zones 3 and 5; every village within 4.0 km | **Not supported, twice over.** Siribu has no road access at all (see above). Even ignoring that, the Zone 3 villages are 11.2–12.8 km from the nearest road-served stop, which is Kaura or Umbuara. Kiera is not road-reachable at all. Siribu village itself is 13.4 km by road from Kaura. |

Road distance runs a **median 1.29× the straight line**, so straight-line figures
are optimistic throughout — as the brief anticipated.

### Twelve villages, 1,187 households, are not reachable by road

Borohojo (271), Gewoya (188), Dareki (145), Aiari (109), Kero (89), Biriri (82),
Toma (73), Jaure (59), Kiera (53), Kinando (49), Sigara (36), Suari (33).

Two of these are worth separate attention because the brief asks:

- **Toma** — no road. 3.0 h walk to Afore, 7.6 km straight.
- **Biriri** — no road. 3.7 h walk to Yoivi, 9.1 km straight.

Both walking times are computed on the **straight line**, because no recorded
path connects either village to a stop. They are therefore *optimistic*: a real
route will be longer. `walk_basis` in the CSV says which villages this applies to.

---

## Data problems found, and what was done about them

### Market stop coordinates

Four stops are quoted to four decimal places; **Yoivi and Siribu to two**, which
is about ±1.1 km. It showed: the brief's Siribu sits 2.0 km off the road while the
surveyed Siribu is 13 m from it.

- **Siribu** — the surveyed position is used instead, 2,072 m from the one given.
- **Yoivi** — **not in the survey file at all.** The brief's rounded position is
  used as given. The nearest surveyed village is Verayame, 2.2 km away. Yoivi
  should be surveyed before these figures are published.

### Umuwate is in the wrong place, or the wrong zone

Listed in Zone 1 (the Itokama cluster) but its coordinates, −9.135433 / 148.401440,
put it beside Afore in Zone 7b, roughly 15 km from every other Zone 1 village.
One of the two fields is wrong. It is carried through as supplied and flagged
here rather than silently moved.

### Village name spellings differ from the brief

The brief says Yaure, Kinado, Boroheje; the file says **Jaure, Kinando, Borohojo**.
The file's spellings are used. Aiari, Gewoya, Toma, Biriri, Kero and Suari agree.

### Positions with a wide household spread

Ten villages have household points scattered over more than 10 km. The median is
robust so the centroids are usable, but these are **not surveyed village centres**
and should not be presented as such. `position_spread_km` is carried in the CSV
for every village.

| Village | Zone | Spread |
|---|---|---|
| Suari | 4 | 37.9 km |
| Jaure | 4 | 33.1 km |
| Niniuri | 7b | 22.1 km |
| Dea | 5 | 20.1 km |
| Kwae | 1 | 16.5 km |
| Gewoya | 9 | 15.9 km |
| Natanga | 3 | 14.4 km |
| Biriri | 9 | 14.1 km |
| Kawowoki | 7a | 13.6 km |
| Tabuane | 5 | 11.0 km |

Suari and Jaure are the worst and both are in Zone 4 — which has no road, so
their access figures rest on a position that could be tens of kilometres out.

### Villages in the Ward Profiles with no coordinates

The Ward Profiles of August 2026 record **73 villages and 3,489 households** in the
Conservation Area. The survey file holds **46 villages**, so **27 villages have no
coordinates** and could not be placed.

They could not be located: no gazetteer or OSM lookup was possible (see above),
and inventing positions was not an option. **They are absent from both figures and
from the access table.**

One inconsistency to resolve at source: the survey file's own `est_hh` sums to
**3,837**, which is *348 more* than the Ward Profiles' 3,489 for the whole
Conservation Area — even though the file covers only 46 of 73 villages. The two
household figures are not reconcilable as they stand, so the percentages above
are computed against the 3,837 in the file and should be revised once that is
settled.

---

## Additional figure — where the road is slow

`fig_road_speed.png` and `mca_road_speed.geojson`, added on request.

Driven recordings are cut into point-to-point steps and attached to 500 m chunks
of road. Stopped time (< 3 km/h) is excluded, as are recorder dropouts. A
recording can be part driven and part walked — one is called *track and road to
Afore* and is exactly that — so a stretch counts as driven only if the vehicle
reached road speed within a two-minute window; otherwise a walked leg reads as
3 km/h road.

**Coverage is the dominant limitation: only 33 km of the 472 km network has enough
passes to measure**, from 5 driven recordings in 3 files. Chunks below 8
observations are drawn grey and left unclassified. Most of the network has never
been driven with a GPS running.

Over the measured 32 km: **median 13.2 km/h**, slowest chunk 6.2, fastest 23.7.

**Terrain does not explain where it is slow.** Spearman correlations against
median speed:

| | rho |
|---|---|
| mean gradient | +0.05 |
| steepest gradient | +0.09 |
| sinuosity | −0.18 |
| elevation | −0.33 |

Gradient is effectively unrelated to speed. The only appreciable relationship is
with elevation, and that is **confounded rather than causal**: the fast chunks are
the coastal approach near Popondetta (median 59 m) and the slow ones are up on
the plateau (median 780 m). Those are different roads, not the same road behaving
differently with altitude.

The slowest fifth does sit on steeper ground than the fastest fifth (17.2 % vs
11.9 % steepest gradient) but their mean gradients are close (7.2 % vs 6.2 %).
Taken together this points at **surface condition rather than topography** — which
this data cannot measure. Confirming it needs either a surface survey or
repeated passes over the same chunks in different seasons.

---

## Files

| File | What it is |
|---|---|
| `mca_roads.geojson` | 472 km motorable road, with per-segment classification evidence |
| `mca_market_stops.geojson` | the six stops, with road or track access marked |
| `mca_village_access.csv` | 46 villages: nearest stop, road km, straight km, walking hours, and the caveats per row |
| `mca_service_areas.geojson` | 18 corridor polygons, 2/5/10 km road distance × 6 stops |
| `fig_mca_map.png` | Figure A — the map |
| `fig_market_reach.png` | Figure B — market reach |
| `fig_road_speed.png` | Additional — measured road speed and its relation to terrain |
| `mca_road_speed.geojson` | 500 m chunks with speed, gradient, sinuosity and observation counts |
| `method.json` | CRS, DEM, thresholds |

Scripts that produced them, in order:
`classify_mode.py` → `build_access.py` → `make_access_figures.py` → `road_speed.py`

Field-knowledge overrides live in `data/access_overrides.csv`.
