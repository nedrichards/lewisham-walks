from __future__ import annotations

import re

import requests

from ..models import Coordinate


class GeocodingError(RuntimeError):
    pass


def normalise_postcode(postcode: str) -> str:
    compact = re.sub(r"\s+", "", postcode).upper()
    if not re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}", compact):
        raise ValueError("Enter a valid UK postcode.")
    return f"{compact[:-3]} {compact[-3:]}"


class PostcodesIoGeocoder:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def lookup_postcode(self, postcode: str) -> Coordinate:
        normalised = normalise_postcode(postcode)
        response = self._session.get(f"https://api.postcodes.io/postcodes/{normalised}", timeout=10)
        if response.status_code == 404:
            raise GeocodingError("Postcode not found.")
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result")
        if not result:
            raise GeocodingError("Postcode not found.")
        return Coordinate(lat=float(result["latitude"]), lon=float(result["longitude"]))
