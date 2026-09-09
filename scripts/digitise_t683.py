"""Digitise vehicle tracks, roads and foot tracks off a georeferenced T683 sheet.

The sheet's own legend is what makes this tractable, because the classes are
separated by colour and by whether the line is broken:

    Road, all weather hard or loose surface ....... red, solid, thick
    Road, fair or dry weather loose surface ....... red, solid, thin
    Vehicle track ................................. red, DASHED
    Foot track .................................... black, solid
    Foot track approximate ........................ black, DASHED

So colour gives road/vehicle against foot, and the dash pattern gives vehicle
against road and approximate against definite. Nothing here is inferred from
context; it is all read off the sheet the way the legend says to read it.

What has to be removed first
----------------------------
Black ink is not only foot tracks. The 1 km AMG grid is black, and so is every
label, spot height and village square. The grid is dealt with exactly, by
projecting its known lines through the georeferencing fit rather than trying to
detect them again. Text and point symbols are dealt with by shape: they are
compact blobs, whereas a track is long and thin.

Dashes are then relinked. A dashed line skeletonises into dozens of unconnected
fragments, so fragments are joined end to end where they are close and nearly
collinear. Whether a finished line had gaps in it is what classifies it, and
that is recorded per feature rather than assumed for the layer.

Every output carries the sheet it came from and that sheet's own survey year,
because the series is not one epoch and a date that is not carried on the
feature will eventually be attached to the wrong one.

Usage:  python3 scripts/digitise_t683.py <sheet-number> [more sheet numbers]
Writes: data/processed/historic_tracks.gpkg (layer "tracks_1973")
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geopandas as gpd
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy import ndimage
from shapely.geometry import LineString
from skimage.measure import regionprops, label as sklabel
from skimage.morphology import skeletonize, remove_small_objects

from georef_t683 import face_bbox

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

WGS84 = "EPSG:4326"
AGD66_AMG55 = "EPSG:20355"

# Colour cuts, measured off the scans rather than guessed. Contours are brown
# and sit between red and background, so the red cut is deliberately strict.
RED = dict(rg=55, rb=40, r=120)
BLACK = dict(val=110, sat=55)

GRID_MASK_PX = 5        # half-width of the strip blanked around each grid line
MIN_OBJECT_PX = 40      # specks below this are scanner noise
MAX_BLOB_THICK = 9      # a run of ink thicker than this is a symbol, not a line
# Lettering is the hard case: "RANGE" and "Garden" are drawn in strokes as thick
# as a foot track, so thickness alone does not separate them. What does separate
# them is shape. A track, or one dash of a dashed track, is long relative to its
# width; a letter is not. A component that is both short and not elongated is
# lettering and goes.
TEXT_MAJOR_PX = 110     # a component longer than this is too big to be a letter
# Measured, not guessed: over a lettering-heavy window the small components have
# median elongation 1.6, over a dashed-track window 3.3 — but the tails overlap
# badly (lettering p90 is 10.6, because I, l and the strokes of N and E are
# themselves elongated). No single threshold separates them. 2.5 sits between the
# medians and is a deliberate compromise: some lettering survives and some real
# dashes are lost. This is why "approximate" foot tracks are flagged in the
# output as the least reliable class, and why the solid classes are the ones to
# trust.
TEXT_ELONGATION = 2.5
DASH_GAP_PX = 22        # ~140 m: longer than a dash gap, shorter than a real gap
DASH_ANGLE_DEG = 35     # fragments must be roughly collinear to be joined
MIN_LINE_PX = 60        # ~380 m: shorter than this is not a route
FACE_INSET_PX = 26      # keeps the neatline and its graticule ticks out


def load_fit(sheet):
    g = json.loads((PROCESSED / f"t683_{sheet}_georef.json").read_text())
    ce = np.array(g["fit"]["easting_coeffs_x_y_1"])
    cn = np.array(g["fit"]["northing_coeffs_x_y_1"])
    return g, ce, cn


def ink_masks(rgb):
    R = rgb[:, :, 0].astype(np.int16)
    G = rgb[:, :, 1].astype(np.int16)
    B = rgb[:, :, 2].astype(np.int16)
    mx = rgb.max(2).astype(np.int16)
    mn = rgb.min(2).astype(np.int16)
    red = (R - G > RED["rg"]) & (R - B > RED["rb"]) & (R > RED["r"])
    black = (mx < BLACK["val"]) & (mx - mn < BLACK["sat"])
    return red, black


def blank_grid(mask, ce, cn, shape):
    """Blank the printed AMG grid, whose lines the fit already tells us about.

    Distance to the nearest kilometre line is just the easting (or northing)
    folded modulo 1000, so the whole grid goes in one pass over the image
    instead of one pass per line.
    """
    H, W = shape
    x = np.arange(W, dtype=np.float32)
    y = np.arange(H, dtype=np.float32)[:, None]

    out = mask
    for c in (ce, cn):
        grad = float(np.hypot(c[0], c[1]))       # metres of coordinate per pixel
        if grad == 0:
            continue
        coord = (c[0] * x + c[1] * y + c[2]).astype(np.float32)
        off = np.mod(coord, 1000.0)
        np.minimum(off, 1000.0 - off, out=off)   # metres to the nearest line
        out = out & ~(off < GRID_MASK_PX * grad)
        del coord, off
    return out


def drop_blobs(mask):
    """Remove text, village squares and other compact symbols.

    A track is thin everywhere along its length; a letter or a filled symbol is
    not. The distance transform gives the local half-thickness directly, so a
    component whose thickest point is fat is a symbol whatever its outline.
    """
    mask = remove_small_objects(mask, min_size=MIN_OBJECT_PX)
    dist = ndimage.distance_transform_edt(mask)
    fat = dist > MAX_BLOB_THICK / 2
    if not fat.any():
        return mask
    lab, n = ndimage.label(mask)
    bad = np.unique(lab[fat])
    bad = bad[bad > 0]
    mask = mask & ~np.isin(lab, bad)
    return drop_lettering(mask)


def drop_lettering(mask):
    """Remove map lettering, which thickness alone cannot separate from tracks."""
    lab = sklabel(mask, connectivity=2)
    drop = []
    for r in regionprops(lab):
        major = r.axis_major_length
        minor = max(r.axis_minor_length, 1e-6)
        if major < TEXT_MAJOR_PX and (major / minor) < TEXT_ELONGATION:
            drop.append(r.label)
    if not drop:
        return mask
    return mask & ~np.isin(lab, np.array(drop))


def trace_skeleton(skel):
    """Split a skeleton into polylines, cutting at junctions."""
    nbr = ndimage.convolve(skel.astype(np.uint8), np.ones((3, 3), np.uint8),
                           mode="constant") - skel.astype(np.uint8)
    junction = skel & (nbr > 2)
    pieces = skel & ~junction
    lab, n = ndimage.label(pieces, structure=np.ones((3, 3)))
    lines = []
    objs = ndimage.find_objects(lab)
    for i, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        sub = lab[sl] == i
        if sub.sum() < 4:
            continue
        ys, xs = np.nonzero(sub)
        ys = ys + sl[0].start
        xs = xs + sl[1].start
        lines.append(order_path(np.column_stack([xs, ys])))
    return [l for l in lines if l is not None and len(l) >= 2]


def order_path(pts):
    """Order the pixels of a thin component into a path, end to end."""
    if len(pts) < 2:
        return None
    # start from the point furthest from the centroid, then greedily walk
    c = pts.mean(0)
    start = int(np.argmax(((pts - c) ** 2).sum(1)))
    remaining = list(range(len(pts)))
    remaining.remove(start)
    path = [start]
    cur = start
    while remaining:
        d = ((pts[remaining] - pts[cur]) ** 2).sum(1)
        j = int(np.argmin(d))
        if d[j] > 8:            # a real break, not the next pixel along
            break
        cur = remaining.pop(j)
        path.append(cur)
    return pts[path]


def simplify(path, tol=1.5):
    return np.array(LineString(path).simplify(tol).coords)


def gap_is_inked(raw, a, b, need=0.6):
    """Was there ink between these two fragment ends before we cleaned up?

    This is the difference between a line that is really dashed and one this
    script broke itself. Blanking the AMG grid cuts every solid track that
    crosses a grid line, and blob removal cuts tracks that run through a
    village square or a label. Both leave gaps that look exactly like dashes.
    The uncleaned ink still knows the difference, so it is asked.
    """
    n = max(int(np.hypot(*(b - a))), 2)
    xs = np.linspace(a[0], b[0], n).astype(int)
    ys = np.linspace(a[1], b[1], n).astype(int)
    ok = (xs >= 0) & (ys >= 0) & (xs < raw.shape[1]) & (ys < raw.shape[0])
    if ok.sum() == 0:
        return False
    return float(raw[ys[ok], xs[ok]].mean()) >= need


def link_dashes(lines, raw):
    """Join fragments that are close and nearly collinear, and say if we did.

    A dashed line arrives here as many separate fragments. Joining them is what
    turns them back into one route. Joins are counted only where the gap was
    genuinely blank on the original scan, so that a line this script cut apart
    is not then reported as a dashed one.
    """
    from scipy.spatial import cKDTree
    lines = [np.asarray(l, float) for l in lines]
    used = [False] * len(lines)
    out = []
    # Index both ends of every fragment so a join candidate is a neighbour
    # lookup rather than a scan over every other fragment.
    ends = np.array([l[0] for l in lines] + [l[-1] for l in lines])
    owner = np.array(list(range(len(lines))) * 2)
    flipped = np.array([False] * len(lines) + [True] * len(lines))
    tree = cKDTree(ends) if len(ends) else None

    def direction(line, at_end):
        seg = line[-min(8, len(line)):] if at_end else line[:min(8, len(line))][::-1]
        v = seg[-1] - seg[0]
        n = np.hypot(*v)
        return v / n if n > 0 else np.array([0.0, 0.0])

    for i in range(len(lines)):
        if used[i]:
            continue
        used[i] = True
        chain = lines[i].copy()
        joins = 0
        extended = True
        while extended:
            extended = False
            for at_end in (True, False):
                tip = chain[-1] if at_end else chain[0]
                dirv = direction(chain, at_end)
                best, best_d, best_flip = None, DASH_GAP_PX, False
                for k in tree.query_ball_point(tip, DASH_GAP_PX):
                    j = int(owner[k])
                    if used[j]:
                        continue
                    flip = bool(flipped[k])
                    cand = lines[j][::-1] if flip else lines[j]
                    step = cand[0] - tip
                    d = float(np.hypot(*step))
                    if d >= best_d or d == 0:
                        continue
                    if float(np.dot(dirv, step / d)) < np.cos(np.radians(DASH_ANGLE_DEG)):
                        continue
                    best, best_d, best_flip = j, d, flip
                if best is not None:
                    cand = lines[best][::-1] if best_flip else lines[best]
                    if not gap_is_inked(raw, tip, cand[0]):
                        joins += 1          # a real gap, so the line was dashed
                    chain = np.vstack([chain, cand]) if at_end else np.vstack([cand[::-1], chain])
                    used[best] = True
                    extended = True
        out.append((chain, joins))
    return out


def digitise(sheet):
    g, ce, cn = load_fit(sheet)
    path = RAW / g["file"]
    print(f"\n=== sheet {sheet} ({g.get('sheet_name')})  {path.name}")
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    H, W = rgb.shape[:2]

    red, black = ink_masks(rgb)

    # Everything outside the printed face is marginalia — the sheet title, the
    # legend, the reliability diagram, the grid-value labels — and all of it is
    # ink of exactly the colours being looked for. Without this the legend boxes
    # and the word SIBIUM end up in the output as tracks.
    fx0, fx1, fy0, fy1 = face_bbox(rgb.astype(np.int16))
    face = np.zeros(red.shape, bool)
    face[int(fy0) + FACE_INSET_PX:int(fy1) - FACE_INSET_PX,
         int(fx0) + FACE_INSET_PX:int(fx1) - FACE_INSET_PX] = True
    red &= face
    black &= face
    print(f"  face x {fx0:.0f}..{fx1:.0f} y {fy0:.0f}..{fy1:.0f} "
          f"(inset {FACE_INSET_PX} px)")
    print(f"  ink: red {red.mean()*100:.2f}%  black {black.mean()*100:.2f}%")
    raw = {"red": red.copy(), "black": black.copy()}   # before any cleaning

    black = blank_grid(black, ce, cn, (H, W))
    red = drop_blobs(red)
    black = drop_blobs(black)
    print(f"  after grid and symbol removal: red {red.mean()*100:.2f}%  "
          f"black {black.mean()*100:.2f}%")

    to_wgs = Transformer.from_crs(AGD66_AMG55, WGS84, always_xy=True)
    rows = []
    for colour, mask in (("red", red), ("black", black)):
        skel = skeletonize(mask)
        frags = trace_skeleton(skel)
        frags = [simplify(f) for f in frags if len(f) >= 3]
        chains = link_dashes(frags, raw[colour])
        kept = 0
        for chain, joins in chains:
            if len(chain) < 2:
                continue
            length_px = float(np.hypot(*np.diff(chain, axis=0).T).sum())
            if length_px < MIN_LINE_PX:
                continue
            dashed = joins >= 2
            if colour == "red":
                kind = "Vehicle track" if dashed else "Road"
                certainty = "definite"
            else:
                kind = "Foot track"
                certainty = "approximate" if dashed else "definite"
            E = ce[0] * chain[:, 0] + ce[1] * chain[:, 1] + ce[2]
            N = cn[0] * chain[:, 0] + cn[1] * chain[:, 1] + cn[2]
            lon, lat = to_wgs.transform(E, N)
            rows.append({
                "type": kind,
                "certainty": certainty,
                "dash_joins": joins,
                "sheet": sheet,
                "sheet_name": g.get("sheet_name"),
                "survey_year": g.get("tracks_villages_current_to"),
                "photography_year": g.get("photography_year"),
                "source": f"T683 sheet {sheet} {g.get('sheet_name')}",
                "georef_rms_m": g["fit"]["residual_m"]["combined_rms"],
                # Dashed black cannot be told from map lettering reliably; solid
                # black and anything red can. Say so on the feature.
                "reliability": ("lower - dashed black is not cleanly separable "
                                "from map lettering"
                                if (colour == "black" and dashed) else "good"),
                "geometry": LineString(np.column_stack([lon, lat])),
            })
            kept += 1
        print(f"  {colour:5s}: {len(frags)} fragments -> {len(chains)} chains -> {kept} kept")
    return rows


def main(sheets):
    rows = []
    for s in sheets:
        rows += digitise(int(s))
    if not rows:
        print("nothing digitised")
        return 1
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)
    utm = gdf.to_crs("EPSG:32755")
    gdf["length_km"] = (utm.length / 1000).round(3)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "historic_tracks.gpkg"
    gdf.to_file(out, layer="tracks_1973", driver="GPKG")
    print(f"\n{len(gdf)} features, {gdf['length_km'].sum():,.0f} km total")
    print(gdf.groupby(["type", "certainty"])["length_km"]
          .agg(["count", "sum"]).round(1).to_string())
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["8579", "8580", "8679"]
    sys.exit(main(args))
