"""Write a KML that Google Earth shows properly: named, foldered, styled.

GeoPandas' KML driver puts every attribute in a SchemaData block and writes no
<name> at all, so a layer opens as 68 or 236 unnamed placemarks. Anything meant
to be LOOKED AT rather than loaded into GIS needs this instead.
"""
from xml.sax.saxutils import escape


def _coords(geom):
    if geom.geom_type == "LineString":
        return [list(geom.coords)]
    if geom.geom_type == "MultiLineString":
        return [list(g.coords) for g in geom.geoms]
    if geom.geom_type == "Polygon":
        return [list(geom.exterior.coords)]
    if geom.geom_type == "MultiPolygon":
        return [list(g.exterior.coords) for g in geom.geoms]
    raise ValueError(geom.geom_type)


def _ring(pts):
    return " ".join(f"{x:.6f},{y:.6f},0" for x, y, *_ in pts)


def _placemark(name, desc, geom, style):
    parts = _coords(geom)
    poly = geom.geom_type.endswith("Polygon")
    body = []
    for pts in parts:
        if poly:
            body.append("<Polygon><outerBoundaryIs><LinearRing><coordinates>"
                        f"{_ring(pts)}"
                        "</coordinates></LinearRing></outerBoundaryIs></Polygon>")
        else:
            body.append("<LineString><tessellate>1</tessellate><coordinates>"
                        f"{_ring(pts)}</coordinates></LineString>")
    geo = body[0] if len(body) == 1 else "<MultiGeometry>" + "".join(body) + "</MultiGeometry>"
    return (f"<Placemark><name>{escape(str(name))}</name>"
            f"<description><![CDATA[{desc}]]></description>"
            f"<styleUrl>#{style}</styleUrl>{geo}</Placemark>")


def write(path, doc_name, doc_desc, styles, folders):
    """styles: {id: (line_abgr, width, poly_abgr|None)}
       folders: [(folder_name, [(name, description_html, geometry, style_id), ...])]"""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           f"<name>{escape(doc_name)}</name>",
           f"<description><![CDATA[{doc_desc}]]></description>"]
    for sid, (line, width, fill) in styles.items():
        out.append(f'<Style id="{sid}"><LineStyle><color>{line}</color>'
                   f"<width>{width}</width></LineStyle>")
        out.append(f"<PolyStyle><color>{fill}</color><fill>1</fill><outline>1</outline></PolyStyle>"
                   if fill else "<PolyStyle><fill>0</fill><outline>1</outline></PolyStyle>")
        out.append("</Style>")
    for fname, items in folders:
        out.append(f"<Folder><name>{escape(fname)}</name><open>1</open>")
        for name, desc, geom, style in items:
            out.append(_placemark(name, desc, geom, style))
        out.append("</Folder>")
    out.append("</Document></kml>")
    path.write_text("\n".join(out), encoding="utf-8")
    return path
