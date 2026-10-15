# To do - Managalas track recording

Built by `scripts/make_todo.py` from `outputs/access/track_checklist.csv`.
`TRACK_CHECKLIST.md` lists the same work route by route; this lists it job
by job, because one missing coordinate blocks a whole route and one short
link closes several.

Of 110 legs on the team's list: **57 recorded**, **36 partly**, **9 not walked**, **8 cannot be checked** until a place is located.

## 1. Places that need a coordinate

**5 places.** Nothing else on this list is
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
- [ ] **Damara** — blocks `F47` (Damara-Bua)
  - on the list between: Bua

## 2. Short links worth walking first

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

## 3. Longer links, same problem

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

## 4. Places no recording has ever reached

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

## 5. Legs with neither end recorded

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

## 6. Questions we need answered, not walked

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

