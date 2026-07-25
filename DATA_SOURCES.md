# Data sources and attribution

The GPL-3.0-or-later licence in `COPYING` covers the application source code. It does not relicense third-party facts, source documents, map data, or generated discovery datasets.

## Open Plaques

Plaque records for Lewisham, Greenwich and Southwark are generated from the Open Plaques GeoJSON dump. Open Plaques states that its generated data is free to use under a Public Domain declaration:

- https://openplaques.org/about
- Individual records link back to their Open Plaques pages.

The source dump is not committed. Download a current thin GeoJSON dump and run `scripts/import_openplaques.py` or `scripts/build_seed_fixture.py`.

## Lewisham maroon plaques

Titles, inscriptions and addresses originate in a Lewisham Council document released in response to this Freedom of Information request:

- https://www.whatdotheyknow.com/request/maroon_plaque_locations

Coordinates are matched to Open Plaques where possible; two remaining points are explicitly marked approximate. The raw DOCX is not committed. The FOI response does not state an explicit open-data licence, so this project records its provenance without asserting that the raw document is covered by the application licence.

## Freddy's Blossom Walk

The bundled blossom points are derived from a publicly shared community route created by Freddy's family and supported by the community and Street Trees for Living:

- https://www.telegraphhillfestival.org.uk/events/a-guided-stroll-along-freddys-blossom-walk/
- https://www.streettreesforliving.org/

The source KMZ does not state an open licence and is not committed. The generated points are shipped with prominent attribution at the project owner's direction. Downstream distributors should assess reuse rights independently or seek permission from the route creators before redistributing this dataset outside Lewisham Walks.

## Borough boundaries

The regeneration scripts use Lewisham, Greenwich and Southwark boundary GeoJSON obtained from Democracy Club's Elections API. Democracy Club documents that current local-authority boundaries are sourced from OS Boundary-Line.

Contains OS data © Crown copyright and database right 2026. OS OpenData is licensed under the Open Government Licence v3.0. Democracy Club source metadata is retained in each GeoJSON file.

## OpenStreetMap and live services

Maps, amenities, geocoding fallbacks and routing use OpenStreetMap data and community services. Map attribution is displayed by libshumate and links to https://www.openstreetmap.org/copyright. Follow the usage policies and attribution requirements of OpenStreetMap, Nominatim, Overpass, FOSSGIS routing, Postcodes.io, and the GNOME tile service when modifying providers.
