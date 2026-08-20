"""Render maps of the Managalas tracks.

Produces:
  outputs/managalas_tracks.png   static overview, projected to UTM 55S
  outputs/managalas_tracks.html  interactive map (tiles load in the browser)

Colour encodes track type — road, village-to-village, garden/survey — which is
the distinction that matters for reading disturbance across the landscape.
Village points are inferred from track endpoints by scripts/infer_villages.py.
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
# Ordered by the disturbance each type implies, heaviest first.
CATEGORY_COLOR = {
    "Road": "#eb6834",
    "Village-to-village track": "#2a78d6",
    "Garden / survey track": "#1baf7a",
}

# Roads read as the heaviest feature on the map, garden paths the lightest.
CATEGORY_WIDTH = {
    "Road": 2.8,
    "Village-to-village track": 2.0,
    "Garden / survey track": 1.5,
}

VILLAGE_COLOR = "#0b0b0b"

# Conservation-area boundary: recessive, never a data series.
BOUNDARY_FILL = "#f2f1ec"
BOUNDARY_EDGE = "#898781"

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"

# How many of the longest tracks get a name on the overview map.
LABEL_COUNT = 8

def load_tracks():
    gdf = gpd.read_file(PROCESSED / "tracks.gpkg", layer="tracks")
    gdf["category"] = gdf["type"]
    return gdf


def load_boundary():
    """MCA boundary polygon, if scripts/build_boundary.py has been run."""
    path = PROCESSED / "mca_boundary.gpkg"
    return gpd.read_file(path, layer="boundary") if path.exists() else None


def load_villages(min_tracks=1):
    """Inferred village points, if infer_villages.py has been run."""
    path = PROCESSED / "villages.gpkg"
    if not path.exists():
        return None
    villages = gpd.read_file(path, layer="villages")
    return villages[villages["named"] & (villages["tracks"] >= min_tracks)]


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


def static_map(gdf, villages=None, boundary=None):
    proj = gdf.to_crs(UTM55S)
    proj = label_groups(proj)

    fig, ax = plt.subplots(figsize=(9.5, 11), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    # Conservation area behind everything: a recessive wash plus a dashed edge,
    # so it frames the network without competing with the track colours.
    if boundary is not None and not boundary.empty:
        bproj = boundary.to_crs(UTM55S)
        bproj.plot(ax=ax, facecolor=BOUNDARY_FILL, edgecolor="none", zorder=0)
        bproj.boundary.plot(ax=ax, color=BOUNDARY_EDGE, linewidth=1.4, linestyle=(0, (6, 3)), zorder=1)

    for category, color in CATEGORY_COLOR.items():
        subset = proj[proj["category"] == category]
        if subset.empty:
            continue
        width = CATEGORY_WIDTH[category]
        # White casing under each line so it stays legible where tracks cross.
        subset.plot(ax=ax, color="#ffffff", linewidth=width + 2.0, zorder=2)
        subset.plot(ax=ax, color=color, linewidth=width, zorder=3)

    # Villages carry the labels rather than tracks: with two dozen tracks the
    # track names are a wall of text, and place names are what make the network
    # readable. Marker size reflects how many tracks vouch for the location.
    texts = []
    if villages is not None and not villages.empty:
        vproj = villages.to_crs(UTM55S)
        for _, row in vproj.iterrows():
            strong = row["tracks"] >= 2
            # Every place gets a marker; only corroborated ones get a name.
            # Labelling all 50 buries the middle of the plateau in text.
            if not strong:
                ax.scatter(
                    row.geometry.x, row.geometry.y, s=22,
                    facecolor="#ffffff", edgecolor=VILLAGE_COLOR, linewidth=1.2, zorder=6,
                )
                continue
            ax.scatter(
                row.geometry.x,
                row.geometry.y,
                s=46 if strong else 22,
                facecolor=VILLAGE_COLOR if strong else "#ffffff",
                edgecolor=VILLAGE_COLOR,
                linewidth=1.2,
                zorder=6,
            )
            texts.append(
                ax.text(
                    row.geometry.x,
                    row.geometry.y,
                    row["village"],
                    fontsize=9 if strong else 8,
                    color=INK_PRIMARY if strong else INK_SECONDARY,
                    fontweight="bold" if strong else "normal",
                    zorder=7,
                    path_effects=[pe.withStroke(linewidth=3.2, foreground="#ffffff")],
                )
            )

        adjust_text(
            texts,
            ax=ax,
            expand=(1.15, 1.3),
            max_move=40,
            arrowprops=dict(arrowstyle="-", color=INK_MUTED, lw=0.7, shrinkA=2, shrinkB=2),
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
        Line2D([0], [0], color=color, lw=CATEGORY_WIDTH[category] + 0.6, label=f"{category}")
        for category, color in CATEGORY_COLOR.items()
        if (proj["category"] == category).any()
    ]
    if boundary is not None and not boundary.empty:
        handles.append(
            Line2D([0], [0], color=BOUNDARY_EDGE, lw=1.4, linestyle=(0, (6, 3)),
                   label="MCA boundary (survey)")
        )
    legend = ax.legend(
        handles=handles,
        loc="lower right",
        frameon=True,
        fontsize=8.5,
        facecolor=SURFACE,
        edgecolor=GRIDLINE,
        title="Track type",
        title_fontsize=8.5,
    )
    legend.get_title().set_color(INK_SECONDARY)
    for text in legend.get_texts():
        text.set_color(INK_SECONDARY)

    n_groups = label_groups(gdf)["group"].nunique()
    n_villages = 0 if villages is None else len(villages)
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
        f"{n_groups} tracks · {n_villages} inferred villages · Oro Province, Papua New Guinea",
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


def interactive_map(gdf, villages=None, boundary=None):
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

    # One toggle per track type rather than per track: with two dozen tracks a
    # per-track layer list is unusable, and type is what the map is now about.
    if boundary is not None and not boundary.empty:
        folium.GeoJson(
            boundary,
            name="MCA boundary",
            style_function=lambda _: {
                "fillColor": "#898781", "color": "#4a4a48",
                "weight": 2, "dashArray": "8,5", "fillOpacity": 0.08,
            },
            tooltip="Managalas Conservation Area (survey boundary)",
        ).add_to(fmap)

    for category, color in CATEGORY_COLOR.items():
        subset = gdf[gdf["category"] == category]
        if subset.empty:
            continue
        layer = folium.FeatureGroup(name=f"{category} ({len(subset)})")
        weight = CATEGORY_WIDTH[category] + 1.0

        for _, row in subset.iterrows():
            date = row["date"] if row["date"] else "not recorded"
            certain = "" if row.get("type_certain", True) else " <i>(type uncertain)</i>"
            popup = folium.Popup(
                f"<b>{row['name']}</b><br>"
                f"{category}{certain}<br>"
                f"{row['length_km']:,.2f} km · {row['vertices']:,} points<br>"
                f"Date: {date}<br>"
                f"Source: {row['source_file']}",
                max_width=320,
            )
            geom = row.geometry
            parts = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
            for part in parts:
                # GPX geometries carry Z (elevation), so take only x, y.
                line = [(c[1], c[0]) for c in part.coords]
                folium.PolyLine(line, color="#ffffff", weight=weight + 3, opacity=0.9).add_to(layer)
                folium.PolyLine(
                    line,
                    color=color,
                    weight=weight,
                    opacity=1.0,
                    tooltip=f"{row['name']} — {category}",
                    popup=popup,
                ).add_to(layer)

        layer.add_to(fmap)

    if villages is not None and not villages.empty:
        layer = folium.FeatureGroup(name=f"Inferred villages ({len(villages)})")
        for _, row in villages.iterrows():
            strong = row["tracks"] >= 2
            folium.CircleMarker(
                location=(row.geometry.y, row.geometry.x),
                radius=6 if strong else 4,
                color=VILLAGE_COLOR,
                weight=1.5,
                fill=True,
                fill_color=VILLAGE_COLOR if strong else "#ffffff",
                fill_opacity=1.0,
                tooltip=row["village"],
                popup=folium.Popup(
                    f"<b>{row['village']}</b><br>"
                    f"Inferred from {row['tracks']} track(s), "
                    f"{row['agreeing']} agreeing (confidence {row['confidence']:.2f})<br>"
                    f"{'Other names proposed: ' + row['alternatives'] + '<br>' if row['alternatives'] else ''}"
                    f"<small>{row['evidence']}</small>",
                    max_width=340,
                ),
            ).add_to(layer)
        layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    out = OUTPUTS / "managalas_tracks.html"
    fmap.save(out)
    print(f"wrote {out}")


def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    gdf = load_tracks()
    villages = load_villages()
    boundary = load_boundary()
    static_map(gdf, villages, boundary)
    small_multiples(gdf)
    interactive_map(gdf, villages, boundary)


if __name__ == "__main__":
    main()
