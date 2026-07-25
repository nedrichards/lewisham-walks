from __future__ import annotations

from xml.etree import ElementTree

from .models import RoutePlan


def plan_to_gpx(plan: RoutePlan) -> str:
    gpx = ElementTree.Element("gpx", version="1.1", creator="Lewisham Walks")
    metadata = ElementTree.SubElement(gpx, "metadata")
    ElementTree.SubElement(metadata, "name").text = "Lewisham discovery walk"

    for discovery in plan.discoveries:
        waypoint = ElementTree.SubElement(
            gpx,
            "wpt",
            lat=f"{discovery.coordinate.lat:.7f}",
            lon=f"{discovery.coordinate.lon:.7f}",
        )
        ElementTree.SubElement(waypoint, "name").text = discovery.title
        ElementTree.SubElement(waypoint, "desc").text = discovery.description

    track = ElementTree.SubElement(gpx, "trk")
    ElementTree.SubElement(track, "name").text = "Route"
    segment = ElementTree.SubElement(track, "trkseg")
    for coordinate in plan.geometry:
        ElementTree.SubElement(segment, "trkpt", lat=f"{coordinate.lat:.7f}", lon=f"{coordinate.lon:.7f}")

    ElementTree.indent(gpx)
    return ElementTree.tostring(gpx, encoding="unicode", xml_declaration=True)
