from __future__ import annotations

from xml.etree import ElementTree

from .models import RouteMode, RoutePlan

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

ElementTree.register_namespace("", GPX_NAMESPACE)
ElementTree.register_namespace("xsi", XSI_NAMESPACE)


def plan_title(plan: RoutePlan) -> str:
    if plan.request.route_mode is RouteMode.BLOSSOM_WALK:
        return "Freddy's Blossom Walk"
    return "Lewisham discovery walk"


def suggested_gpx_filename(plan: RoutePlan) -> str:
    if plan.request.route_mode is RouteMode.BLOSSOM_WALK:
        return "freddys-blossom-walk.gpx"
    return f"lewisham-{plan.request.route_theme.value}-walk.gpx"


def plan_to_gpx(plan: RoutePlan) -> str:
    def tag(name: str) -> str:
        return f"{{{GPX_NAMESPACE}}}{name}"

    gpx = ElementTree.Element(
        tag("gpx"),
        version="1.1",
        creator="Lewisham Walks",
        attrib={
            f"{{{XSI_NAMESPACE}}}schemaLocation": (
                f"{GPX_NAMESPACE} http://www.topografix.com/GPX/1/1/gpx.xsd"
            )
        },
    )
    metadata = ElementTree.SubElement(gpx, tag("metadata"))
    ElementTree.SubElement(metadata, tag("name")).text = plan_title(plan)
    route_description = " ".join([
        f"{plan.distance_m / 1000:.1f} km route with {len(plan.discoveries)} local discoveries.",
        *plan.warnings,
    ])
    ElementTree.SubElement(metadata, tag("desc")).text = route_description

    route_points = [("Start", "start", plan.request.start, "Start of walk")]
    route_points.extend(
        (visit.title, visit.kind, visit.coordinate, visit.description or visit.address)
        for visit in plan.visits
    )
    for name, point_type, coordinate, description in route_points:
        waypoint = ElementTree.SubElement(
            gpx,
            tag("wpt"),
            lat=f"{coordinate.lat:.7f}",
            lon=f"{coordinate.lon:.7f}",
        )
        ElementTree.SubElement(waypoint, tag("name")).text = name
        if description:
            ElementTree.SubElement(waypoint, tag("desc")).text = description
        ElementTree.SubElement(waypoint, tag("type")).text = point_type.replace("-", " ").title()

    track = ElementTree.SubElement(gpx, tag("trk"))
    ElementTree.SubElement(track, tag("name")).text = plan_title(plan)
    ElementTree.SubElement(track, tag("desc")).text = route_description
    segment = ElementTree.SubElement(track, tag("trkseg"))
    for coordinate in plan.geometry:
        ElementTree.SubElement(
            segment,
            tag("trkpt"),
            lat=f"{coordinate.lat:.7f}",
            lon=f"{coordinate.lon:.7f}",
        )

    ElementTree.indent(gpx)
    return ElementTree.tostring(gpx, encoding="unicode", xml_declaration=True)
