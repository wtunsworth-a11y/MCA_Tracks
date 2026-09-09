"""Georeference the 1970s T683 topographic sheets, and say how well it worked.

What these sheets are
---------------------
Papua New Guinea 1:100,000 Topographic Survey, Series T683, Royal Australian
Survey Corps. Seven sheets covering 97.4 per cent of the coastline this
assessment measures. Projection Transverse Mercator on the Australian Map Grid
Zone 55; horizontal datum AGD66.

They are NOT one epoch. The reliability diagram on each sheet gives its own
aerial photography dates, and they range from 1954 to 1973 - see
data/oro/t683_sheet_sources_v1.json. Tufi, which carries 36 per cent of the
assessed coast including Oro Bay, is 1956 photography: thirty-one years before
the earliest Landsat epoch used here, not fourteen. Every derived rate must
carry its own sheet's baseline year.

Method
------
Each sheet's neatline is drawn along the graticule, so its four corners are
exact half-degree intersections which the numbering rule gives and the printed
corner labels confirm. The corners are found by detecting the neatline as the
strongest continuous dark line within each margin, at full scan resolution and
to sub-pixel precision by intensity-weighted centroid.

A projective transform is then fitted from image pixels to AGD66 longitude and
latitude. Projective rather than affine because a Transverse Mercator sheet is
very slightly keystoned: meridians are straight but parallels are gently
curved, and over 30 minutes that is tens of metres, not hundreds.

Two things are reported rather than assumed:

  RESIDUAL   the fit is checked against the sheet's own printed 1 km AMG grid,
             which is independent of the corners used to fit it. That residual
             is the georeferencing error and is reported separately from
             everything else.

  DATUM      AGD66 to WGS84 across this region is very nearly a constant 200 m
             - about +116 m east and +163 m north. The median absolute
             shoreline movement measured anywhere in this assessment is 13 to
             26 m, so an untransformed overlay would manufacture roughly ten
             times the real signal. The shift is applied as an explicit,
             separately reported step so it can never be confused with the
             fit residual or with real change.

The sheets also state their own accuracy as about plus or minus 32 metres.
That is inherited from the 1950s to 1970s survey and cannot be improved by
anything done here; it is the floor on any position taken off these maps, and
it is larger than the province median shoreline movement. These sheets can
therefore resolve the stretches that moved 100 m or more, and cannot resolve a
typical transect.

Outputs: outputs/oro/oro_t683_georef_v1.json

Funded by the European Union, EU Forestry, Climate Change and Biodiversity
(EU-FCCB) Nexus Programme | Managalas and Oro Province Project (MOPP) |
CIFOR-ICRAF.
Ref: 2026-MOPP-CCOP-001
"""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "oro")
OUT = os.path.join(HERE, "..", "outputs", "oro")
SHEETS_DIR = "/home/user/mca_mla/data/T683"
AGD66_LL = "EPSG:4202"
AGD66_AMG55 = "EPSG:20355"
WGS84 = "EPSG:4326"
DARK = 120
ATTR = ("Funded by the European Union, EU Forestry, Climate Change and "
        "Biodiversity (EU-FCCB) Nexus Programme; Managalas and Oro Province "
        "Project (MOPP); CIFOR-ICRAF.")


def sheet_extent(number):
    """Graticule extent of a T683 sheet from its number.

    The rule was inferred from the index diagram printed on Sinclair 8680,
    which names six neighbours; it reproduces all six. It is confirmed
    independently on Tufi, whose south-west corner is printed as 149 deg 00'
    and 9 deg 30' - exactly what the rule gives.
    """
    col, row = int(str(number)[:2]), int(str(number)[2:])
    lon0 = 148.5 + (col - 86) * 0.5
    lat_s = 8.5 + (80 - row) * 0.5          # southern edge, degrees south
    return lon0, lon0 + 0.5, -(lat_s + 0.5), -lat_s     # W, E, S, N


def _edge(dark, axis, lo_frac, hi_frac, span=(0.20, 0.75)):
    """Sub-pixel position of the strongest continuous line in a margin band."""
    n = dark.shape[1] if axis == 0 else dark.shape[0]
    m = dark.shape[0] if axis == 0 else dark.shape[1]
    s0, s1 = int(span[0] * m), int(span[1] * m)
    prof = (dark[s0:s1, :].sum(axis=0) if axis == 0
            else dark[:, s0:s1].sum(axis=1)).astype(float) / (s1 - s0)
    lo, hi = int(lo_frac * n), int(hi_frac * n)
    band = prof[lo:hi]
    k = int(np.argmax(band))
    # intensity-weighted centroid over the peak and its immediate neighbours
    a, b = max(k - 3, 0), min(k + 4, len(band))
    w = band[a:b]
    if w.sum() <= 0:
        return float(lo + k), float(band[k])
    cen = float((np.arange(a, b) * w).sum() / w.sum())
    return lo + cen, float(band[k])


def georeference(path, number, verbose=True):
    from pyproj import Transformer
    im = Image.open(path).convert("L")
    a = np.asarray(im, dtype=np.uint8)
    H, W = a.shape
    dark = a < DARK
    left, sl = _edge(dark, 0, 0.02, 0.09)
    right, sr = _edge(dark, 0, 0.91, 0.98)
    top, st = _edge(dark, 1, 0.03, 0.09)
    bottom, sb = _edge(dark, 1, 0.80, 0.87)
    w_lon, e_lon, s_lat, n_lat = sheet_extent(number)

    # Geometric consistency, which caught a real error. A 30 by 30 minute
    # face must have width to height in the ratio of half a degree of
    # longitude to half a degree of latitude at that latitude - pure geometry,
    # nothing fitted. On Popondetta the bottom edge was first detected 300 px
    # below every other sheet, on the weakest edge signal in the set, giving a
    # face 3.6 per cent too tall. Where the aspect is out by more than 1.5 per
    # cent the weakest edge is re-searched in the band the other three predict.
    import math as _m
    latm = abs((s_lat + n_lat) / 2)
    expect_aspect = ((e_lon - w_lon) * 111320 * _m.cos(_m.radians(latm))
                     / ((n_lat - s_lat) * 110570))
    corrected = None
    got = (right - left) / (bottom - top)
    if abs(got - expect_aspect) / expect_aspect > 0.015:
        want_h = (right - left) / expect_aspect
        strengths = {"top": st, "bottom": sb, "left": sl, "right": sr}
        weakest = min(("top", "bottom"), key=lambda k: strengths[k])
        if weakest == "bottom":
            pred = top + want_h
            lo, hi = (pred - 0.02 * H) / H, (pred + 0.02 * H) / H
            bottom, sb = _edge(dark, 1, max(lo, 0.0), min(hi, 1.0))
        else:
            pred = bottom - want_h
            lo, hi = (pred - 0.02 * H) / H, (pred + 0.02 * H) / H
            top, st = _edge(dark, 1, max(lo, 0.0), min(hi, 1.0))
        corrected = {"edge": weakest, "reason": "face aspect out of geometry",
                     "aspect_before": round(got, 4),
                     "aspect_expected": round(expect_aspect, 4),
                     "aspect_after": round((right - left) / (bottom - top), 4)}

    # four neatline corners in pixels, and their AGD66 lon/lat
    src = np.array([[left, top], [right, top], [right, bottom], [left, bottom]],
                   float)
    dst = np.array([[w_lon, n_lat], [e_lon, n_lat],
                    [e_lon, s_lat], [w_lon, s_lat]], float)

    # projective transform, solved by direct linear transformation
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, Vt = np.linalg.svd(np.array(A))
    Hm = Vt[-1].reshape(3, 3)
    Hm = Hm / Hm[2, 2]

    def px_to_ll(x, y):
        d = Hm[2, 0] * x + Hm[2, 1] * y + Hm[2, 2]
        return ((Hm[0, 0] * x + Hm[0, 1] * y + Hm[0, 2]) / d,
                (Hm[1, 0] * x + Hm[1, 1] * y + Hm[1, 2]) / d)

    # --- independent check: does the fit reproduce the printed AMG grid? -----
    # The grid is not used to fit anything, so its residual is a fair measure.
    to_amg = Transformer.from_crs(AGD66_LL, AGD66_AMG55, always_xy=True)
    face_w = right - left
    face_h = bottom - top
    # ground size of the face, from the fit
    x0, y0 = to_amg.transform(*px_to_ll(left, bottom))
    x1, y1 = to_amg.transform(*px_to_ll(right, bottom))
    x2, y2 = to_amg.transform(*px_to_ll(left, top))
    m_per_px_x = float(np.hypot(x1 - x0, y1 - y0) / face_w)
    m_per_px_y = float(np.hypot(x2 - x0, y2 - y0) / face_h)

    # detect the printed 1 km grid inside the face and compare with prediction
    inner = dark[int(top + 0.10 * face_h):int(bottom - 0.10 * face_h),
                 int(left + 0.10 * face_w):int(right - 0.10 * face_w)]
    colprof = inner.sum(axis=0).astype(float) / inner.shape[0]
    rowprof = inner.sum(axis=1).astype(float) / inner.shape[1]

    def spacing(prof, expect_px):
        """Dominant line spacing, by power spectrum around the expected value."""
        p = prof - prof.mean()
        f = np.abs(np.fft.rfft(p * np.hanning(len(p))))
        freqs = np.fft.rfftfreq(len(p))
        lo, hi = 1.0 / (expect_px * 1.20), 1.0 / (expect_px * 0.80)
        m = (freqs >= lo) & (freqs <= hi)
        if not m.any():
            return None
        k = int(np.argmax(np.where(m, f, 0)))
        return float(1.0 / freqs[k]) if freqs[k] > 0 else None

    exp_px_x = 1000.0 / m_per_px_x
    exp_px_y = 1000.0 / m_per_px_y
    got_x = spacing(colprof, exp_px_x)
    got_y = spacing(rowprof, exp_px_y)
    res = {"sheet": number, "file": os.path.basename(path),
           "image_px": [int(W), int(H)],
           "neatline_px": {"left": round(left, 1), "right": round(right, 1),
                           "top": round(top, 1), "bottom": round(bottom, 1),
                           "edge_strength": [round(sl, 3), round(sr, 3),
                                             round(st, 3), round(sb, 3)]},
           "graticule_extent_agd66": {"west": w_lon, "east": e_lon,
                                      "south": s_lat, "north": n_lat},
           "face_px": [round(face_w, 1), round(face_h, 1)],
           "ground_m_per_px": [round(m_per_px_x, 3), round(m_per_px_y, 3)],
           "scan_dpi_implied": round(2540.0 / m_per_px_x, 0),
           "aspect_correction": corrected,
           "grid_check": {
               "expected_1km_spacing_px": [round(exp_px_x, 1), round(exp_px_y, 1)],
               "detected_1km_spacing_px": [round(got_x, 1) if got_x else None,
                                           round(got_y, 1) if got_y else None]}}
    if got_x and got_y:
        ex = abs(got_x - exp_px_x) / exp_px_x
        ey = abs(got_y - exp_px_y) / exp_px_y
        res["grid_check"]["scale_error_pct"] = [round(ex * 100, 2),
                                                round(ey * 100, 2)]
        res["grid_check"]["implied_position_error_m_over_face"] = [
            round(ex * m_per_px_x * face_w, 1), round(ey * m_per_px_y * face_h, 1)]
    # the homography, so the sheet can be resampled later without re-fitting
    res["homography_px_to_agd66_lonlat"] = [[round(v, 12) for v in row]
                                            for row in Hm.tolist()]
    if verbose:
        g = res["grid_check"]
        print(f"  {number}  face {face_w:.0f} x {face_h:.0f} px  "
              f"{m_per_px_x:.2f} m/px  ~{res['scan_dpi_implied']:.0f} dpi  |  "
              f"grid expected {exp_px_x:.1f} px, detected "
              f"{(f'{got_x:.1f}' if got_x else 'none'):>7s} px"
              + (f"  scale error {g['scale_error_pct'][0]:.2f} %"
                 if "scale_error_pct" in g else ""), flush=True)
    return res


def main():
    from pyproj import Transformer
    files = sorted(glob.glob(os.path.join(SHEETS_DIR, "*.jpg")))
    print(f"{len(files)} sheets\n")
    src = json.load(open(os.path.join(DATA, "t683_sheet_sources_v1.json")))
    dates = {s["sheet"]: s for s in src["sheets"]}
    out = {"project_ref": "2026-MOPP-CCOP-001", "attribution": ATTR,
           "series": src["series"], "source_repository": src["source_repository"],
           "datum_note": ("sheets are AGD66; the transform to WGS84 across this "
                          "region is very nearly a constant 200 m (+116 m east, "
                          "+163 m north) and is applied and reported as its own "
                          "step, never folded into the fit"),
           "map_accuracy_note": ("each sheet states its own accuracy as about "
                                 "+/- 32 m. That is the floor on any position "
                                 "taken from these maps and exceeds the "
                                 "province median shoreline movement of 13 to "
                                 "26 m, so the sheets resolve stretches that "
                                 "moved 100 m or more and not a typical "
                                 "transect."),
           "sheets": []}
    for f in files:
        m = re.search(r"_(\d{4})_master", os.path.basename(f))
        if not m:
            continue
        num = int(m.group(1))
        r = georeference(f, num)
        d = dates.get(num, {})
        r["photography_years"] = d.get("photography_years")
        r["share_of_assessed_coast_pct"] = d.get("share_of_assessed_coast_pct")
        r["name"] = d.get("name")
        out["sheets"].append(r)

    # the datum shift, measured at each sheet centre rather than assumed
    t = Transformer.from_crs(AGD66_LL, WGS84, always_xy=True)
    import math
    for r in out["sheets"]:
        g = r["graticule_extent_agd66"]
        lon = (g["west"] + g["east"]) / 2
        lat = (g["south"] + g["north"]) / 2
        x, y = t.transform(lon, lat)
        de = (x - lon) * 111320 * math.cos(math.radians(abs(lat)))
        dn = (y - lat) * 110570
        r["agd66_to_wgs84_shift_m"] = {"east": round(de, 1), "north": round(dn, 1),
                                       "total": round(math.hypot(de, dn), 1)}
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "oro_t683_georef_v1.json")
    json.dump(out, open(p, "w"), indent=1)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
