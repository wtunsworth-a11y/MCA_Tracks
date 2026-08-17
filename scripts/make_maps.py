"""Render maps of the Managalas tracks.

Produces:
  outputs/managalas_tracks.png   static overview, projected to UTM 55S
  outputs/managalas_tracks.html  interactive map (tiles load in the browser)

Colour encodes provenance, not individual track: seven tracks exceed what a
categorical palette can separate (the validated all-pairs ceiling is four), so
identity is carried by direct labels and popups instead of hue.
"""

import textwrap
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from adjustText import adjust_text
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"

UTM55S = "EPSG:32755"

# Validated categorical slots 1-3 (all-pairs, light surface). See dataviz
# reference palette; do not substitute without re-running the validator.
CATEGORY_COLOR = {
    "GPS track log (GPX)": "#2a78d6",
    "Route export (KMZ)": "#eb6834",
    "Survey segments (GPKG)": "#1baf7a",
}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"

# How many of the longest tracks get a name on the overview map.
LABEL_COUNT = 8

CATEGORY_BY_FORMAT = {
    "gpx": "GPS track log (GPX)",
    "kmz": "Route export (KMZ)",
    "gpkg": "Survey segments (GPKG)",
}


def load_tracks():
    gdf = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    gdf["category"] = gdf["format"].map(CATEGORY_BY_FORMAT)
    return gdf


def label_groups(gdf):
    """One label per real-world track — the GPKG's six segments share a label."""
    gdf = gdf.copy()
    gdf["group"] = gdf["name"].str.replace(r"\s*\(seg \d+\)$", "", regex=True)
    return gdf


def add_scalebar(ax, length_m=10_000):
    """Scale bar in projected metres, anchored bottom-left."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    pad_x = (x1 - x0) * 0.06
    pad_y = (y1 - y0) * 0.05
    bx, by = x0 + pad_x, y0 + pad_y

    # Opaque backing so the bar never reads as part of a track underneath it.
    ax.add_patch(
        plt.Rectangle(
            (bx - length_m * 0.09, by - (y1 - y0) * 0.016),
            length_m * 1.18,
            (y1 - y0) * 0.055,
            facecolor=SURFACE,
            edgecolor=GRIDLINE,
            lw=0.6,
            zorder=5,
        )
    )
    ax.plot([bx, bx + length_m], [by, by], color=INK_PRIMARY, lw=2.5, solid_capstyle="butt", zorder=6)
    for x in (bx, bx + length_m):
        ax.plot([x, x], [by - (y1 - y0) * 0.006, by + (y1 - y0) * 0.006], color=INK_PRIMARY, lw=2.5, zorder=6)
    ax.text(
        bx + length_m / 2,
        by + (y1 - y0) * 0.012,
        f"{length_m // 1000} km",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color=INK_SECONDARY,
        zorder=6,
    )


def add_north_arrow(ax):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x1 - (x1 - x0) * 0.07
    y = y1 - (y1 - y0) * 0.09
    ax.annotate(
        "N",
        xy=(x, y),
        xytext=(x, y - (y1 - y0) * 0.055),
        ha="center",
        va="center",
        fontsize=10,
        color=INK_SECONDARY,
        arrowprops=dict(arrowstyle="-|>", color=INK_SECONDARY, lw=1.4),
    )


def static_map(gdf):
    proj = gdf.to_crs(UTM55S)
    proj = label_groups(proj)

    fig, ax = plt.subplots(figsize=(9.5, 11), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    for category, color in CATEGORY_COLOR.items():
        subset = proj[proj["category"] == category]
        if subset.empty:
            continue
        # White casing under each line so it stays legible where tracks cross.
        subset.plot(ax=ax, color="#ffffff", linewidth=4.0, zorder=2)
        subset.plot(ax=ax, color=color, linewidth=2.0, zorder=3)

    # Selective direct labels: with two dozen tracks, labelling every one turns
    # the map into a wall of text. Name the longest few here; the facet view
    # and the HTML map identify the rest.
    lengths = proj.groupby("group")["length_km"].sum().sort_values(ascending=False)
    labelled = set(lengths.head(LABEL_COUNT).index)

    texts = []
    for group, rows in proj.groupby("group"):
        if group not in labelled:
            continue
        point = rows.geometry.union_all().representative_point()
        total_km = rows["length_km"].sum()
        texts.append(
            ax.text(
                point.x,
                point.y,
                # Survey names run long; wrap so labels stay inside the axes.
                "\n".join(textwrap.wrap(group, width=26)) + f"\n{total_km:,.1f} km",
                fontsize=8.5,
                color=INK_PRIMARY,
                linespacing=1.35,
                zorder=7,
                path_effects=[pe.withStroke(linewidth=3.2, foreground="#ffffff")],
            )
        )

    adjust_text(
        texts,
        ax=ax,
        expand=(1.25, 1.5),
        arrowprops=dict(arrowstyle="-", color=INK_MUTED, lw=0.8, shrinkA=2, shrinkB=2),
    )

    ax.grid(True, color=GRIDLINE, lw=0.6, zorder=1)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRIDLINE)

    # Ticks in kilometres — raw UTM metres force a dangling "1e6" offset label.
    km = FuncFormatter(lambda v, _: f"{v / 1000:,.0f}")
    ax.xaxis.set_major_formatter(km)
    ax.yaxis.set_major_formatter(km)
    ax.set_xlabel("Easting (km, UTM 55S)", fontsize=8.5, color=INK_MUTED)
    ax.set_ylabel("Northing (km, UTM 55S)", fontsize=8.5, color=INK_MUTED)
    ax.set_aspect("equal")

    handles = [
        Line2D([0], [0], color=color, lw=2.5, label=f"{category}")
        for category, color in CATEGORY_COLOR.items()
        if (proj["category"] == category).any()
    ]
    legend = ax.legend(
        handles=handles,
        loc="lower right",
        frameon=True,
        fontsize=8.5,
        facecolor=SURFACE,
        edgecolor=GRIDLINE,
        title="Source",
        title_fontsize=8.5,
    )
    legend.get_title().set_color(INK_SECONDARY)
    for text in legend.get_texts():
        text.set_color(INK_SECONDARY)

    total = gdf["length_km"].sum()
    n_groups = label_groups(gdf)["group"].nunique()
    ax.set_title(
        "Recorded tracks across the Managalas Plateau",
        fontsize=14,
        color=INK_PRIMARY,
        pad=30,
        loc="left",
    )
    ax.text(
        0.0,
        1.008,
        f"{n_groups} tracks · {total:,.0f} km · Oro Province, Papua New Guinea",
        transform=ax.transAxes,
        fontsize=9,
        color=INK_SECONDARY,
        va="bottom",
    )

    add_scalebar(ax)
    add_north_arrow(ax)

    fig.tight_layout()
    out = OUTPUTS / "managalas_tracks.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def small_multiples(gdf):
    """One panel per track, all on a shared extent.

    The overview cannot separate the two KMZ tracks — they share a colour —
    and seven tracks exceed the four-slot all-pairs ceiling, so faceting is
    how each track gets identified unambiguously.
    """
    proj = label_groups(gdf.to_crs(UTM55S))
    groups = (
        proj.groupby("group")["length_km"].sum().sort_values(ascending=False).index.tolist()
    )

    minx, miny, maxx, maxy = proj.total_bounds
    pad = max(maxx - minx, maxy - miny) * 0.04

    ncols = 5
    nrows = -(-len(groups) // ncols)  # ceiling division
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(3.3 * ncols, 4.5 * nrows), facecolor=SURFACE, squeeze=False
    )
    focus_color = "#2a78d6"  # categorical slot 1

    for ax, group in zip(axes.flat, groups):
        ax.set_facecolor(SURFACE)
        # Every other track, recessive, for spatial context.
        proj.plot(ax=ax, color="#d9d8d2", linewidth=0.9, zorder=2)

        rows = proj[proj["group"] == group]
        rows.plot(ax=ax, color="#ffffff", linewidth=4.2, zorder=3)
        rows.plot(ax=ax, color=focus_color, linewidth=2.4, zorder=4)

        total_km = rows["length_km"].sum()
        date = rows["date"].dropna().iloc[0] if rows["date"].notna().any() else "no date"
        title = group if len(group) <= 34 else group[:33].rstrip() + "…"
        ax.set_title(title, fontsize=9.5, color=INK_PRIMARY, loc="left", pad=20)
        ax.text(
            0.0,
            1.012,
            f"{total_km:,.1f} km · {date}",
            transform=ax.transAxes,
            fontsize=8,
            color=INK_SECONDARY,
            va="bottom",
        )

        ax.set_xlim(minx - pad, maxx + pad)
        ax.set_ylim(miny - pad, maxy + pad)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color(GRIDLINE)

    for ax in axes.flat[len(groups) :]:
        ax.axis("off")

    fig.suptitle(
        "Each track in isolation, shared extent",
        fontsize=13,
        color=INK_PRIMARY,
        x=0.012,
        ha="left",
        y=0.985,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95], h_pad=3.5)
    out = OUTPUTS / "managalas_tracks_facets.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def interactive_map(gdf):
    import folium

    gdf = label_groups(gdf)
    minx, miny, maxx, maxy = gdf.total_bounds
    fmap = folium.Map(tiles=None, control_scale=True)
    fmap.fit_bounds([[miny, minx], [maxy, maxx]])

    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite imagery",
    ).add_to(fmap)

    for group, rows in gdf.groupby("group"):
        category = rows["category"].iloc[0]
        color = CATEGORY_COLOR[category]
        layer = folium.FeatureGroup(name=f"{group} ({rows['length_km'].sum():,.1f} km)")

        for _, row in rows.iterrows():
            date = row["date"] if row["date"] else "not recorded"
            popup = folium.Popup(
                f"<b>{row['name']}</b><br>"
                f"{row['length_km']:,.2f} km · {row['vertices']:,} points<br>"
                f"Date: {date}<br>"
                f"Source: {row['source_file']}<br>"
                f"Original name: {row['source_name'] or '—'}",
                max_width=320,
            )
            coords = []
            geom = row.geometry
            parts = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
            for part in parts:
                # GPX geometries carry Z (elevation), so take only x, y.
                coords.append([(c[1], c[0]) for c in part.coords])

            for line in coords:
                # White casing first, then the coloured line on top.
                folium.PolyLine(line, color="#ffffff", weight=6, opacity=0.9).add_to(layer)
                folium.PolyLine(
                    line,
                    color=color,
                    weight=3,
                    opacity=1.0,
                    tooltip=f"{row['name']} — {row['length_km']:,.2f} km",
                    popup=popup,
                ).add_to(layer)

        layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    out = OUTPUTS / "managalas_tracks.html"
    fmap.save(out)
    print(f"wrote {out}")


def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    gdf = load_tracks()
    static_map(gdf)
    small_multiples(gdf)
    interactive_map(gdf)


if __name__ == "__main__":
    main()
