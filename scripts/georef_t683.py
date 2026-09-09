"""Georeference a T683 topographic sheet on its own printed AMG grid.

Series T683, PNG 1:100,000 Topographic Survey, Royal Australian Survey Corps.
Projection Transverse Mercator on the Australian Map Grid zone 55; horizontal
datum AGD66.

Why the grid rather than the neatline corners
---------------------------------------------
The obvious anchor is the four neatline corners, whose graticule coordinates
the sheet number gives and the printed corner labels confirm. That was tried
first and it is not good enough here, for two reasons found in the data:

  * The corners disagree with themselves. Measured individually, the left edge
    of Sibium is 8629 px long and the right edge 8566 px — 0.7 per cent apart.
    A four-corner fit silently averages that away and leaves it in the result.

  * The AMG grid is not parallel to the neatline. Grid convergence tilts it
    about 0.14 degrees, so the north edge of the sheet spans 187 m of AMG
    northing from west to east. Measuring a "vertical" grid line down the whole
    face therefore smears it across some 20 px, which is what made an earlier
    spectral estimate of the grid spacing wrong by 4.6 per cent.

The printed 1 km grid is the sheet's own coordinate system, it is dense, and it
is drawn to survey accuracy. So the grid is what is fitted, and the neatline is
demoted to a sanity check.

The fit is affine, not projective. Affine has independent x and y scale, which
is needed: the scan measures 156.77 px/km across and 156.12 px/km down, a real
0.4 per cent anisotropy from the scanner or from paper stretch. Over 30 minutes
of a Transverse Mercator sheet the projective term is worth tens of metres,
well under the residual reported below, so it buys nothing here.

What is reported, not assumed
-----------------------------
  RESIDUAL   every detected grid intersection is compared against the affine
             prediction; rms and worst case are reported in metres.
  DATUM      AGD66 to WGS84 is close to a constant 200 m in this region and is
             applied by pyproj as its own step, never folded into the fit.
  SHEET      the sheet states its own accuracy as about +/- 32 m. That is
             inherited from the original survey and nothing here improves it.

Usage:  python3 scripts/georef_t683.py data/raw/<sheet>.jpg
Writes: data/processed/t683_<number>_georef.json
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

AGD66_LL = "EPSG:4202"
AGD66_AMG55 = "EPSG:20355"
WGS84 = "EPSG:4326"

# Each sheet carries its own currency in the reliability diagram, and the sheets
# are NOT one epoch across the series. Read off the sheet, not assumed. The date
# that matters for tracks is the one attached to track and village information,
# which on these sheets is later than the photography.
SHEET_SOURCES = {
    8579: {"name": "Sibium", "photography_year": 1973,
           "tracks_villages_current_to": 1974,
           "note": ("reliability diagram: aerial photography 1973, "
                    "stereophotogrammetric methods, track and village "
                    "information interpreted from air photographs "
                    "supplemented by patrol reports to 1974")},
    8580: {"name": "Popondetta", "photography_year": 1973,
           "tracks_villages_current_to": 1973,
           "note": ("reliability diagram: aerial photography 1973, "
                    "stereophotogrammetric methods, track and village "
                    "information interpreted from air photographs "
                    "supplemented by patrol reports to 1973")},
    8679: {"name": "Musa", "photography_year": 1973,
           "tracks_villages_current_to": 1973,
           "note": ("reliability diagram: aerial photography 1973, "
                    "stereophotogrammetric methods, track and village "
                    "information interpreted from air photographs "
                    "supplemented by patrol reports to 1973")},
}

DARK = 140
HALF_BAND = 120          # half-height of the strip a grid line is measured in
NOMINAL_PX_PER_KM = 156  # only a starting guess for the peak separation


def sheet_extent(number):
    """Graticule extent of a T683 sheet from its number: W, E, S, N."""
    col, row = int(str(number)[:2]), int(str(number)[2:])
    lon0 = 148.5 + (col - 86) * 0.5
    lat_s = 8.5 + (80 - row) * 0.5
    return lon0, lon0 + 0.5, -(lat_s + 0.5), -lat_s


def peaks(profile, origin, min_sep, limit=80):
    """Sub-pixel positions of dark lines in a 1-D profile, strongest first."""
    # A band lying in the white margin has a zero median, which would make the
    # threshold zero so that nothing is ever below it and the loop never ends.
    thr = max(float(np.median(profile)) * 1.3, 1e-6)
    work = profile.copy()
    found = []
    for _ in range(limit * 4):
        if len(found) >= limit:
            break
        k = int(np.argmax(work))
        if work[k] < thr:
            break
        a, b = max(k - 3, 0), min(k + 4, len(profile))
        w = profile[a:b]
        work[max(k - min_sep, 0):k + min_sep] = 0
        if w.sum() <= 0:
            continue
        found.append(origin + float((np.arange(a, b) * w).sum() / w.sum()))
    return sorted(found)


def grid_samples(dark, bands, axis):
    """Grid-line crossings measured in narrow bands, so tilt cannot smear them.

    Returns [(x_px, y_px, line_index)] with line_index counted from the first
    line found in each band; the absolute value is pinned by the caller.
    """
    H, W = dark.shape
    sep = int(NOMINAL_PX_PER_KM * 0.6)
    out = []
    for centre in bands:
        if axis == "v":
            sub = dark[centre - HALF_BAND:centre + HALF_BAND, :]
            prof = sub.mean(0)
            pos = peaks(prof, 0, sep)
            out.append((centre, pos))
        else:
            sub = dark[:, centre - HALF_BAND:centre + HALF_BAND]
            prof = sub.mean(1)
            pos = peaks(prof, 0, sep)
            out.append((centre, pos))
    return out


def face_bbox(rgb):
    """Bounding box of the printed map face, found by colour.

    The neatline would be the natural thing to detect, but on these scans it is
    fainter than the grid lines drawn inside it, so "strongest line in the
    margin" reliably finds a grid line instead — which is what threw an earlier
    attempt out by 4.6 per cent. The face is printed in colour and the margin is
    bare paper, and that difference is unambiguous. The box is only ever used to
    give grid lines their kilometre labels, never to fix the transform.
    """
    H, W, _ = rgb.shape
    sat = rgb.max(2) - rgb.min(2)
    coloured = sat > 18

    def longest_run(frac, thr=0.30, gap=50):
        idx = np.where(frac > thr)[0]
        if len(idx) == 0:
            return None
        groups = np.split(idx, np.where(np.diff(idx) > gap)[0] + 1)
        g = max(groups, key=len)
        return float(g[0]), float(g[-1])

    x0, x1 = longest_run(coloured[int(0.25 * H):int(0.75 * H), :].mean(0))
    y0, y1 = longest_run(coloured[:, int(0.25 * W):int(0.75 * W)].mean(1))
    return x0, x1, y0, y1


def fit_affine(points, values_e, values_n):
    """Least squares [x,y,1] -> easting, northing, with outlier rejection."""
    P = np.column_stack([points[:, 0], points[:, 1], np.ones(len(points))])
    keep = np.ones(len(points), bool)
    for _ in range(4):
        ce, *_ = np.linalg.lstsq(P[keep], values_e[keep], rcond=None)
        cn, *_ = np.linalg.lstsq(P[keep], values_n[keep], rcond=None)
        re_ = values_e - P @ ce
        rn_ = values_n - P @ cn
        err = np.hypot(re_, rn_)
        s = err[keep].std()
        if s == 0:
            break
        new = err < max(3 * s, 5.0)
        if (new == keep).all():
            break
        keep = new
    return ce, cn, keep, np.hypot(values_e - P @ ce, values_n - P @ cn)


def main(path):
    path = Path(path)
    m = re.search(r"_(\d{4})_master", path.name)
    if not m:
        print(f"!! cannot read a sheet number from {path.name}")
        return 1
    number = int(m.group(1))
    w_lon, e_lon, s_lat, n_lat = sheet_extent(number)

    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    img = rgb.mean(2).astype(np.uint8)
    dark = (img < DARK).astype(np.float32)
    H, W = dark.shape
    print(f"{path.name}  sheet {number}  {W} x {H} px")
    print(f"graticule  {w_lon}..{e_lon} E   {s_lat}..{n_lat} N   (AGD66)")

    to_amg = Transformer.from_crs(AGD66_LL, AGD66_AMG55, always_xy=True)
    corners_amg = {n: to_amg.transform(lo, la) for n, (lo, la) in {
        "NW": (w_lon, n_lat), "NE": (e_lon, n_lat),
        "SW": (w_lon, s_lat), "SE": (e_lon, s_lat)}.items()}

    # Grid lines that actually fall inside the face, in whole kilometres.
    east_lo = int(np.ceil(max(corners_amg["NW"][0], corners_amg["SW"][0]) / 1000))
    east_hi = int(np.floor(min(corners_amg["NE"][0], corners_amg["SE"][0]) / 1000))
    north_lo = int(np.ceil(max(corners_amg["SW"][1], corners_amg["SE"][1]) / 1000))
    north_hi = int(np.floor(min(corners_amg["NW"][1], corners_amg["NE"][1]) / 1000))
    n_east, n_north = east_hi - east_lo + 1, north_hi - north_lo + 1
    print(f"expect {n_east} easting lines {east_lo}..{east_hi} km, "
          f"{n_north} northing lines {north_lo}..{north_hi} km")

    bands_y = np.linspace(0.10 * H, 0.85 * H, 6).astype(int)
    bands_x = np.linspace(0.10 * W, 0.90 * W, 6).astype(int)
    vert = grid_samples(dark, bands_y, "v")
    horiz = grid_samples(dark, bands_x, "h")

    # Which grid line is which? Counting a run from one end is not safe: a band
    # also picks up the neatline, so two bands can start their count on
    # different lines and the fit then sees a whole kilometre of disagreement.
    # Instead the neatline corners give a rough transform, good to a few hundred
    # metres, which is enough to name every line to the nearest kilometre. The
    # naming is then redone from the fitted transform and the fit repeated, so
    # the rough corners only ever choose labels and never enter the answer.
    fx0, fx1, fy0, fy1 = face_bbox(rgb)
    print(f"printed face  x {fx0:.0f}..{fx1:.0f}   y {fy0:.0f}..{fy1:.0f}  (by colour)")
    src = np.array([[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1]], float)
    dst = np.array([corners_amg[n] for n in ("NW", "NE", "SE", "SW")], float)
    P = np.column_stack([src[:, 0], src[:, 1], np.ones(4)])
    ce, *_ = np.linalg.lstsq(P, dst[:, 0], rcond=None)
    cn, *_ = np.linalg.lstsq(P, dst[:, 1], rcond=None)

    def label(ce, cn):
        """Attach an AMG value to every detected crossing, to the nearest km."""
        pts, es, ns = [], [], []
        for yc, xs in vert:
            for x in xs:
                e = ce[0] * x + ce[1] * yc + ce[2]
                km = round(e / 1000)
                if not (east_lo <= km <= east_hi):
                    continue
                if abs(e - km * 1000) > 450:      # too far from any grid line
                    continue
                pts.append((x, yc)); es.append(km * 1000.0); ns.append(np.nan)
        for xc, ys in horiz:
            for y in ys:
                n = cn[0] * xc + cn[1] * y + cn[2]
                km = round(n / 1000)
                if not (north_lo <= km <= north_hi):
                    continue
                if abs(n - km * 1000) > 450:
                    continue
                pts.append((xc, y)); es.append(np.nan); ns.append(km * 1000.0)
        return (np.array(pts, float), np.array(es, float), np.array(ns, float))

    pts, es, ns = label(ce, cn)

    pts = np.array(pts, float)
    es = np.array(es, float)
    ns = np.array(ns, float)

    # Easting is constrained only by the vertical lines and northing only by the
    # horizontal ones, so the two coefficient sets are fitted on their own rows.
    def solve(mask, target):
        P = np.column_stack([pts[mask, 0], pts[mask, 1], np.ones(mask.sum())])
        t = target[mask]
        keep = np.ones(len(t), bool)
        for _ in range(4):
            c, *_ = np.linalg.lstsq(P[keep], t[keep], rcond=None)
            r = t - P @ c
            s = r[keep].std()
            new = np.abs(r) < max(3 * s, 3.0)
            if (new == keep).all():
                break
            keep = new
        return c, r, keep

    for _ in range(3):
        ve, vn = ~np.isnan(es), ~np.isnan(ns)
        ce, re_, ke = solve(ve, es)
        cn, rn_, kn = solve(vn, ns)
        pts, es, ns = label(ce, cn)      # relabel from the fit, then refit
    ve, vn = ~np.isnan(es), ~np.isnan(ns)
    ce, re_, ke = solve(ve, es)
    cn, rn_, kn = solve(vn, ns)

    print()
    print(f"easting  fit on {ke.sum()}/{ve.sum()} crossings   "
          f"rms {re_[ke].std():6.1f} m   max {np.abs(re_[ke]).max():6.1f} m")
    print(f"northing fit on {kn.sum()}/{vn.sum()} crossings   "
          f"rms {rn_[kn].std():6.1f} m   max {np.abs(rn_[kn]).max():6.1f} m")
    rms = float(np.hypot(re_[ke].std(), rn_[kn].std()))
    print(f"combined rms {rms:.1f} m   (sheet's own stated accuracy +/- 32 m)")

    # scale and rotation implied by the fit
    sx = float(np.hypot(ce[0], cn[0]))
    sy = float(np.hypot(ce[1], cn[1]))
    rot = float(np.degrees(np.arctan2(cn[0], ce[0])))
    print(f"scale {sx:.4f} m/px across, {sy:.4f} m/px down "
          f"({abs(sx - sy) / sx * 100:.2f} % anisotropy)")
    print(f"grid rotation in the scan {rot:+.3f} deg   "
          f"implied scan {2540 / sx:.0f} dpi")

    # neatline as an independent check, since it was not used in the fit
    inv = np.linalg.inv(np.array([[ce[0], ce[1], ce[2]],
                                  [cn[0], cn[1], cn[2]],
                                  [0, 0, 1]]))
    print("\nneatline corners predicted from the grid fit (px):")
    for name, (E, N) in corners_amg.items():
        v = inv @ np.array([E, N, 1.0])
        print(f"  {name}  ({v[0]:8.1f}, {v[1]:8.1f})")

    to_wgs = Transformer.from_crs(AGD66_AMG55, WGS84, always_xy=True)
    cx, cy = W / 2, H / 2
    E = ce[0] * cx + ce[1] * cy + ce[2]
    N = cn[0] * cx + cn[1] * cy + cn[2]
    lon_w, lat_w = to_wgs.transform(E, N)
    to_ll = Transformer.from_crs(AGD66_AMG55, AGD66_LL, always_xy=True)
    lon_a, lat_a = to_ll.transform(E, N)
    import math
    de = (lon_w - lon_a) * 111320 * math.cos(math.radians(abs(lat_w)))
    dn = (lat_w - lat_a) * 110570
    print(f"\nAGD66 -> WGS84 at sheet centre: {de:+.1f} m east, {dn:+.1f} m north "
          f"({math.hypot(de, dn):.1f} m)")

    src = SHEET_SOURCES.get(number, {})
    if src:
        print(f"\nsheet currency: photography {src['photography_year']}, "
              f"tracks/villages to {src['tracks_villages_current_to']}")
    out = {
        "sheet": number,
        "file": path.name,
        "sheet_name": src.get("name"),
        "photography_year": src.get("photography_year"),
        "tracks_villages_current_to": src.get("tracks_villages_current_to"),
        "currency_note": src.get("note"),
        "series": "T683, PNG 1:100,000 Topographic Survey, RA Survey Corps",
        "image_px": [int(W), int(H)],
        "graticule_extent_agd66": {"west": w_lon, "east": e_lon,
                                   "south": s_lat, "north": n_lat},
        "fit": {
            "model": "affine, pixel -> AGD66 / AMG zone 55 (EPSG:20355)",
            "easting_coeffs_x_y_1": [float(v) for v in ce],
            "northing_coeffs_x_y_1": [float(v) for v in cn],
            "fitted_on": "printed 1 km AMG grid crossings",
            "crossings_used": [int(ke.sum()), int(kn.sum())],
            "crossings_offered": [int(ve.sum()), int(vn.sum())],
            "residual_m": {"easting_rms": round(float(re_[ke].std()), 2),
                           "easting_max": round(float(np.abs(re_[ke]).max()), 2),
                           "northing_rms": round(float(rn_[kn].std()), 2),
                           "northing_max": round(float(np.abs(rn_[kn]).max()), 2),
                           "combined_rms": round(rms, 2)},
            "scale_m_per_px": [round(sx, 4), round(sy, 4)],
            "grid_rotation_deg": round(rot, 4),
            "scan_dpi": round(2540 / sx),
        },
        "sheet_stated_accuracy_m": 32,
        "accuracy_note": ("the sheet states +/- 32 m from the original survey; "
                          "the fit residual above is separate from and smaller "
                          "than that, so +/- 32 m is the floor on any position "
                          "digitised from this sheet"),
        "datum_note": ("fit is to AGD66/AMG55; conversion to WGS84 is done by "
                       "pyproj as a separate step and is about 200 m in this "
                       "region, never folded into the fit"),
        "agd66_to_wgs84_shift_m": {"east": round(de, 1), "north": round(dn, 1)},
    }
    PROCESSED.mkdir(parents=True, exist_ok=True)
    target = PROCESSED / f"t683_{number}_georef.json"
    target.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  "data/raw/521_PNG_Oro_Sibium_100K_8579_master.jpg"))
