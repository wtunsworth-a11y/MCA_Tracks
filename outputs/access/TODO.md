# To do - Managalas tracks and facility points

Built by `scripts/make_todo.py` from `outputs/access/track_checklist.csv`
and `data/reference/facilities.csv`. `TRACK_CHECKLIST.md` lists the walking
route by route; this lists everything job by job, because one missing
coordinate blocks a whole route and one short link closes several.

**Two things outstanding.** The walking: of 110 legs on the team's list, **58 recorded**, **36 partly**, **9 not walked**, **7 cannot be checked** until a place is located. The points: **63 facility positions** still to collect, none of which has a coordinate yet.

## 1. Places on the track list that need a coordinate

**4 places.** Nothing else on this list is
cheaper to fix. Until each one has a position we cannot say whether its
route has been walked or not - it is not missing, it is unknown.

A rough position is enough: the village, or the junction, to within a
kilometre. Mark it in the KML (`outputs/access/unlocated_places.kml`),
or just say which known place it is near and how far.

- [ ] **Aputuara** — blocks `F04` (Numba-Aputuara - Banderi)
  - on the list between: Banderi, Numba
- [ ] **Umasi** — blocks `F17` (Numba -Umasi-Embi-Warisota)
  - on the list between: Embi, Numba
- [ ] **Emoriva** — blocks `F29` (Kuai-Tedebedi-Emoriva)
  - on the list between: Tedebedi
  - already said: 'This looks like a contraction of Emo River. Not here and not inside MCA.' Consistent with Tedebedi, placed 2 km from the Emo River airstrip at 148.04 - F29 runs off the plateau to the west. Needs a position if the route is wanted
- [ ] **Vovosik** — blocks `F44` (Jaura-Vovosik-Kwikila)
  - on the list between: Jaura, Kwikila

## 2. Facility points to collect

**63 points** across 36 villages - the second list, the schools, aid
posts, health centres, airstrips and offices.

Each facility is its own point. A school, an aid post and an airstrip
in one village are three positions, not one, so a village coordinate
does not cover them. Grouped by village so a single visit collects
everything there.

Record the status as found as well as the position - several of these
were last reported closed decades ago, and the table below is what was
said, not what is there now.

### Then: 63 points at 36 villages we can find

| village | ward | points | facilities |
|---|---|---:|---|
| Marasi | 01 Yoivi | 1 | Marasi Elementary School, 2 × 2-in-1 (*In use*) |
| Manusi | 01 Yoivi | 1 | Manusi Elementary School, 1 × 2-in-1 (*In use, bush material*) |
| Yoivi | 01 Yoivi | 3 | Yoivi Community Aid Post (*Newly built, no proper facilities, no regular drug supply, 2 volunteer CHWs, not registered*); Aguido Elementary School (*In use*); Aguido Primary School, 1 × 4-in-1 classroom, 4 teacher houses (*In use, bush material*) |
| Afore Govt Station → Afore (the station is slightly different to Afore village - find it from the village and give each building its own point) | 02 Niniuri | 5 | Afore Health Centre, clinic + 3 CHW houses (*Functioning*); Afore Elementary School, 2-in-1 classroom (*Functioning*); Afore Primary School, 2 × 2-in-1 + 6 staff houses (*Functioning, needs upgrading*); DDA Sub-District Office (*Not functioning, yet to open*); Afore Airstrip (*Closed*) |
| Dareki | 03 Kawowoki | 2 | Dareki Elementary School, 2-in-1 (*Functioning*); Dareki Aid Post (*Closed 2010*) |
| Kawowoki | 03 Kawowoki | 2 | Kawowoki Elementary School, 2-in-1 (*Functioning*); Kawowoki Aid Post (*Closed*) |
| Kaura | 04 Kaura | 1 | Kaura Elementary School, 1 × 2-in-1 (*Running*) |
| not named → Numba (Siurani is the old name for Numba - the school is at Numba) | 05 Siurani | 1 | Elementary School, 2-in-1 (*Not functioning, closed*) |
| Koeno | 06 Koeno | 1 | Koeno Elementary School + teacher houses (*In use*) |
| Sakarina | 06 Koeno | 1 | Airstrip (*Closed 2019, lack of maintenance*) |
| Dea | 07 Dea | 2 | Dea Elementary School, 4 classrooms, 1 teacher house (*In use*); Dea Primary School, 8 classrooms, 6 teacher houses (*In use*) |
| Tabuane | 07 Dea | 1 | Tabuane Elementary School (*In use, no data collected*) |
| Ugunomo → Ugunomu | 07 Dea | 1 | Ugunomo Elementary School (*In use*) |
| not named → Dea (nobody knows where this airstrip is - ask in the ward) | 07 Dea | 1 | Airstrip (*Closed 1988*) |
| Siribu | 08 Siribu | 1 | Siribu Elementary School, 2 × 2-in-1 (*In use*) |
| Jorura → Jorua | 09 Natanga | 1 | Jorura Elementary School (*Semi-permanent*) |
| Kiara | 09 Natanga | 1 | Kiara Elementary School (*Semi-permanent*) |
| Natanga | 09 Natanga | 2 | Natanga Elementary School (*Semi-permanent*); Natanga Aid Post (*Non-operational, no CHW*) |
| not named → Gora (Gora is one village with three hamlets, sometimes called villages, all close together - write down which hamlet each one is in) | 10 Gora | 4 | Elementary School, 4-in-1 + 2 single classrooms, 4 teacher houses (*In use*); Primary School (*In use*); Aid Post + CHW house (*CHW house 2024*); Airstrip (*Closed 1988, to re-open*) |
| Tahama → Semahara Tahama | 11 Tahama | 1 | Tahama Elementary School, 2 single classrooms, 2 teacher houses (*In use, bush material*) |
| Koruwo | 11 Tahama | 4 | Koruwo Elementary School, 2-in-1, 2 teacher houses (*In use*); Koruwo Primary School, 1 × 4-in-1, 2 × 2-in-1, 1 × 8-in-1, 5 teacher houses (*In use, 8-in-1 incomplete*); Koruwo High School + male and female dormitories (*Started 2026, dormitories for 3rd term*); Health Centre (*Incomplete, no CHW*) |
| Anatua 2 → Anatua (Anatua is a long village and they have defined Anatua 1 and Anatua 2 - map both ends, not one point) | 12 Umbuwara | 1 | Anatua Elementary School (*In use*) |
| Boidomo → Bodoimo | 12 Umbuwara | 1 | Boidomo Elementary School (*In use*) |
| Umbuwara → Umbuara | 12 Umbuwara | 2 | Umbuwara Elementary School (*In use*); Umbuwara Primary School (*Detail not recorded*) |
| not named → Umbuara (the ward table does not say where this aid post is - ask locally) | 12 Umbuwara | 1 | Aid Post building (*Incomplete since 2012*) |
| Kokoro | 13 Kokoro | 1 | Aid Post, moved from Serefuna 2025 (*Incomplete, to complete 2026, 1 officer*) |
| Serefuna | 13 Kokoro | 1 | Serefuna Elementary School, 1 × 2-in-1 (*Upgrade needed, bush material*) |
| Itokama | 14 Ufia | 4 | Itokama Health Centre + 1 CHW house (*Incomplete but in use*); Itokama Elementary School (*Functioning*); Itokama Primary School, 3 × 2-in-1, 8 teacher houses, library (*In use*); Itokama Airstrip, natural surface (*Ceased 2023, charters only*) |
| Naukanane → Naokanane | 14 Ufia | 1 | Naukanane Elementary School (*Functioning*) |
| Umuate | 14 Ufia | 1 | Umuate Elementary School (*Functioning*) |
| Gewoya | 15 Toma | 3 | Gewoya Elementary School (*Functioning, bush material*); Gewoya Primary School (*Functioning*); Gewoya Aid Post (*Closed 1996*) |
| Toma | 15 Toma | 1 | Toma Aid Post (*Closed 2002*) |
| Aiari | 16 Aiari | 3 | Aiari Elementary School, EP and E1/E2 + teacher house (*Running, bush material*); Aid Post (*Closed 1985*); Airstrip (*Closed 1988*) |
| Suari | 17 Jaure | 2 | Suari Elementary School, 2-in-1 + 1 teacher house (*In use*); Primary School (*In use, bush material*) |
| Yaure → Jaure | 17 Jaure | 2 | Yaure Aid Post (*Incomplete since 1984, no structure*); Yaure Airstrip (*Closed 2002*) |
| not named → Gorobuna (outside the conservation area, but Will kept it in scope - do it) | 18 Gorobuna | 2 | Elementary School (*Rundown and closed, no teacher, closed 2025, bush material*); Airstrip (*Unused since built, 2021*) |

## 3. Short links worth walking first

**6 legs under 3 km.** Both ends are
already recorded, but no recording follows the direct track between them,
so the map has to send people the long way round. Short walks, each of
which closes a hole in the network.

- [ ] **Highway → Kawowoki** — 0.5 km direct, against 24.2 km the long way round  `R12`
- [ ] **Afore → Korokoro** — 0.5 km direct, against 2.2 km the long way round  `R14`
- [ ] **Highway → Bioi** — 1.5 km direct, against 11.4 km the long way round  `F53`
- [ ] **Bioi → Dareki** — 1.5 km direct, against 7.6 km the long way round  `F05`
- [ ] **Kaura → Avaru** — 2.2 km direct, against 6.0 km the long way round  `R06`
- [ ] **Dea → Siribu** — 2.8 km direct, against 11.3 km the long way round  `F22`

## 4. Longer links, same problem

**15 legs.** Both ends recorded, the direct track not.

- [ ] **Kiara → Koruwo** — 3.0 km direct, against 9.7 km the long way round  `F23`
- [ ] **Kawowoki → Avaru** — 3.1 km direct, against 32.9 km the long way round  `F41`
- [ ] **Ugunomo → Siribu** — 3.1 km direct, against 9.0 km the long way round  `R07`
- [ ] **Umbuara → Kiara** — 3.3 km direct, against 16.2 km the long way round  `F34`
- [ ] **Niniri → Kawowoki** — 3.9 km direct, against 15.3 km the long way round  `F32`
- [ ] **Toma → Biriri** — 4.3 km direct, against 31.5 km the long way round  `F25`
- [ ] **Avaru → Dareki** — 5.1 km direct, against 27.1 km the long way round  `F07`
- [ ] **Avaru → Sigara** — 5.8 km direct, against 14.8 km the long way round  `F03`
- [ ] **Dareki → Sigara** — 6.6 km direct, against 33.6 km the long way round  `F05`
- [ ] **Tahama → Toma** — 7.1 km direct, against 14.8 km the long way round  `F02`
- [ ] **Sigara → Banderi** — 8.8 km direct, against 63.0 km the long way round  `F36`
- [ ] **Wayei → Umbara** — 10.2 km direct, against 22.3 km the long way round  `F31`
- [ ] **Tahama → Serepuna** — 11.0 km direct, against 23.6 km the long way round  `F24`
- [ ] **Toma → Itokama** — 14.8 km direct, against 38.0 km the long way round  `F13`
- [ ] **Gora → Popondetta** — 25.9 km direct, against 128.5 km the long way round  `F09`

## 5. Places no recording has ever reached

**15 places**, furthest first. The number is how far the
place sits from the nearest recorded line - that is the walk needed to
tie it in, not the length of any particular track.

| place | km off the network | routes | note |
|---|---:|---|---|
| Safia | 42.4 | F25, F30 | CONFIRMED by Will, 4 Oct 2026: there is only one Safia, so this is it - the airstrip at 9d35.70'S 148d38.34'E (Pacific Wrecks). Aiari-Safia is therefore genuinely a 54 km route |
| Sairope | 22.6 | F42 | OSM village; GeoNames has New Sairope 2 km away. Gora > Asafa > Sairope is then a consistent westward chain, which is the corroboration |
| Tedebedi | 21.0 | F29, F60 | also written Tetebedi; confirmed by Will, 3 Oct 2026: Tetebedi/Tedebedi is OUTSIDE the conservation area, so Anatua-Tetebedi and Kuai-Tedebedi-Emoriva run beyond the boundary |
| Asafa | 15.2 | F42, F59 | OSM village 15 km WNW of Gora. (An Asafa 406 km away in Eastern Highlands was rejected) |
| Babarobo | 14.0 | F25 | OSM village, and it sits almost exactly on the Biriri-Safia line, which is the leg the list puts it in |
| Suari | 13.3 | F37 |  |
| Jaure | 10.2 | F12, F26, F37, F38 | also written Jaura |
| Aiari | 9.8 | F30, F37, F49 | also written Water Crossing |
| Gorobuna | 7.0 | F43, F59 |  |
| Peroroda | 6.1 | H02 | OSM village. 20 km from where the route implied, but that anchor is the weak Bareji cluster, so the distance proves little either way - worth a check |
| Warisota | 1.6 | F17 | OSM village beside Embi. AMBIGUOUS: GeoNames has another Warisota 13 km north and OSM a New Warisota 45 km west - this is the one the route fits |
| Singata | 1.1 | F58, F59, F62 |  |
| Old Cardamom factory | 1.0 | R04 |  |
| Emo | 0.9 | F03 | OSM village east of Sigara; GeoNames agrees within 1 km. NOT the Emo River / Emo Station near Kokoda, 45 km west - the name is used twice in Oro |
| Oro Bay | 0.6 | H01 | also written Orobay |

## 6. Legs with neither end recorded

**9 legs.** Nothing nearby has been recorded at
either end, so these are whole journeys rather than gaps to close.

- **Afore-Toma-Biriri-Babarobo-Safia**  `F25`
  - [ ] Babarobo → Safia — 29.3 km straight  **multi-day walk, not a day trip**
- **Aiari-Safia**  `F30`
  - [ ] Aiari → Safia — 53.7 km straight  **multi-day walk, not a day trip**
- **Ufia-Umuate-Aiari-Suari-Jaure**  `F37`
  - [ ] Aiari → Suari — 5.2 km straight
  - [ ] Suari → Jaure — 10.5 km straight
- **Gora-Asafa-Sairope**  `F42`
  - [ ] Asafa → Sairope — 9.2 km straight
- **Aiari-Water Crossing**  `F49`
  - [ ] Aiari → Water Crossing — Aiari and Aiari are the same point in our data (0 m apart), so there is no leg here - and that place is 9.8 km off anything recorded
- **Singata-Gorobuna-Asafa**  `F59`
  - [ ] Singata → Gorobuna — 10.2 km straight
  - [ ] Gorobuna → Asafa — 13.4 km straight
- **Road 2-Old Cadamon factory**  `R04`
  - [ ] Old Cardamom factory → (the road itself) — no recorded motorable road within 1.0 km of Old Cardamom factory - the road itself is not recorded

## 7. Questions we need answered, not walked

- [ ] **Ogan.** It burned down on or before 4 Oct 2026. The access figures
  still count it as 69 households, road-served, 1.48 km by road to Afore -
  2.6 % of the road-served households. Where have those households gone?
  Until we know, the published figures are flagged but not corrected.
- [ ] **Road 1 and Ogan** came back 52 m apart, so `R05` has no leg to walk.
  Is that right, or did two pins land on one feature?
- [ ] **The off-plateau routes** - Safia, Kwikila, Oro Bay, Popondetta - are
  they in scope at all, or only the portion inside the conservation area?
  Four of the longest jobs on this list are off-plateau, and `F30`
  (Aiari-Safia) is 54 km in a straight line.

