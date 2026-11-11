# GIS layers

Spatial layers meant to be opened, not just looked at. Everything here is
WGS84 (EPSG:4326) and carries the same attributes.

| File | What it is |
| --- | --- |
| `mca_government_services.gpkg` | GeoPackage, three layers: `all_services`, `schools`, `health` |
| `mca_government_services.geojson` | the same 47 facilities, one layer |
| `mca_government_services_shp/` | the same, as a shapefile |
| `mca_government_services.kml` | for Google Earth, foldered by kind then by status |
| `mca_schools.kml` | schools only — 30 |
| `mca_health.kml` | aid posts and health centres only — 10 |
| `mca_government_services.csv` | the same table with lon/lat columns, for a spreadsheet |
| `mca_government_facilities.csv` | the plain list: name, type, village, coordinates |

## The attribute that matters is `status`

`working`, `closed` or `unknown`, and **nothing is assumed to be working.**

It comes from what the recorder wrote standing in front of the building -
"Building in use", "Closed down", "Airstrip is not in operation" - and only
falls back to the Afore LLG ward tables where the field said nothing. The
sentence itself travels with the point in `evidence`, because a status of
"closed" is worth nothing without the reason beside it.

`seen_only_as` flags a facility that was recorded only through its ancillary
buildings - a teacher's house, a dormitory. Seeing one of those standing is
not seeing the school, so such a facility is never marked `working`.

Churches are deliberately absent: there are 27 of them and they are not a
government service.

## The `village` column is decided by position, not by the name

`mca_government_facilities.csv` names the village each facility stands at, and
it gets there by measuring, because the name on the building is not evidence of
where the building is. Afore High School is named for the LLG and stands at
Sakarina. Suwari Primary School is physically elsewhere again. So each facility
is matched to the nearest settlement that has a mapped position, and
`km_from_village` reports that distance so a loose match can be seen as one.

Four facilities are named for a place the gazetteer has no position for -
Tahama, Awaru, Anatua and Kuweno - so they are filed at the nearest mapped
village, 1.5 to 2.5 km off, rather than at the place in their own name. That is
a gap in the village list, not a disagreement about the facility.

Facilities are excluded from the settlement list they are matched against.
Without that, "Aguido Primary School" was itself being used as a village and
three facilities were filed "at" it. Will, 27 Oct 2026: "Aguido is the name of
a person. Not a place."

Built by `scripts/make_services_map.py`, which also draws the three figures
in `outputs/access/`, and `scripts/make_facilities_csv.py`.
