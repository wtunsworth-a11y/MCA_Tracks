#!/usr/bin/env bash
# Everything that has to be rebuilt after new field data arrives, in the one
# order that works.
#
# Will, 7 Nov 2026: "when Russell uploads new data, you WILL update those 2
# files" - outputs/gis/mca_schools.kml and outputs/gis/mca_health.kml. They
# were not being updated, because the weekly routine's pipeline stopped at the
# itinerary and never reached the services map. A prose list of steps drifts;
# this does not.
#
# Order is not arbitrary:
#   classify_mode must run between merge_tracks and anything that reads
#   'mode', or the network comes back without it.
#   reconcile_facilities must run before make_itinerary, which drops the
#   facilities it reports as collected, and before make_questions.
#
# A new WAYPOINT drop needs one manual step first, because its provenance
# header has to be written by someone who knows where the file came from:
#
#   python3 scripts/extract_waypoint_kml.py <doc.kml> \
#           data/reference/waypoints_<area>.csv
#
# After that nothing here needs editing: the drops are discovered by
# scripts/waypoint_drops.py, not listed.
set -euo pipefail
cd "$(dirname "$0")/.."

run () { echo "--- $*"; "$@"; }

run python3 scripts/inspect_sources.py
run python3 scripts/merge_tracks.py
run python3 scripts/classify_mode.py
run python3 scripts/build_access.py
run python3 scripts/infer_villages.py
run python3 scripts/cross_reference_tracks.py

run python3 scripts/reconcile_facilities.py
run python3 scripts/pick_facility_photos.py
run python3 scripts/make_services_map.py          # the two KML layers
run python3 scripts/make_facilities_csv.py        # name/type/village/coords
run python3 scripts/make_site_maps.py            # village footprints on S2

# Audits. They raise suggestions rather than change anything, and they exist
# because both faults cost real time: a fourth spelling of Koeno put a school
# at the wrong village, and two files named backwards made one village look
# like two. Neither should ever again be found by tripping over it.
run python3 scripts/audit_place_spellings.py
run python3 scripts/audit_track_direction.py

run python3 scripts/make_todo.py
run python3 scripts/make_itinerary.py
run python3 scripts/make_itinerary_map.py
run python3 scripts/make_questions.py
run python3 scripts/make_villages_kml.py
run python3 scripts/make_villages_map.py
run python3 scripts/make_zone_voronoi.py

run node scripts/md_to_docx.js outputs/access/ITINERARY.md \
    outputs/access/MCA_itinerary.docx \
    "Managalas Conservation Area — field collection itinerary" \
    toc outputs/access/fig_itinerary.png
run node scripts/md_to_docx.js outputs/access/TRACK_CHECKLIST.md \
    outputs/access/MCA_track_checklist.docx \
    "Managalas Conservation Area — track recording status" toc
run node scripts/md_to_docx.js outputs/access/TODO.md \
    outputs/access/MCA_todo.docx \
    "Managalas Conservation Area — outstanding points" toc
run node scripts/md_to_docx.js outputs/access/QUESTIONS.md \
    outputs/access/MCA_questions_for_Russell.docx \
    "Managalas Conservation Area — questions for Russell"

echo
echo "=== layers that must now be current ==="
ls -la outputs/gis/mca_schools.kml outputs/gis/mca_health.kml \
       outputs/gis/mca_government_facilities.csv
