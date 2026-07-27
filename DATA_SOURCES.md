# Data sources and attribution

The GPL-3.0-or-later licence in `COPYING` covers the application source code. It does not relicense third-party facts, source documents, map data, or generated discovery datasets.

## Open Plaques

Plaque records for Lewisham, Greenwich and Southwark are generated from the Open Plaques GeoJSON dump. Open Plaques states that its generated data is free to use under a Public Domain declaration:

- https://openplaques.org/about
- Individual records link back to their Open Plaques pages.

The source dump is not committed. Download a current thin GeoJSON dump and run `scripts/import_openplaques.py` or `scripts/build_seed_fixture.py`.

## Historic England listed buildings

Grade I and Grade II* listed-building points for Lewisham, Greenwich and Southwark are generated from Historic England's National Heritage List for England (NHLE). The NHLE is the official current register, and Historic England releases its GIS data under the Open Government Licence:

- https://historicengland.org.uk/listing/the-list/data-downloads/
- https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/ArcGIS/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/0

The source GeoJSON is not committed. The bundled fixture was generated on 27 July 2026 from the official point layer, whose data was last edited on 24 July 2026. To regenerate it, query the ArcGIS layer in WGS 84 for the two included grades and a small London envelope, then apply the repository's exact borough boundaries:

```sh
curl -fsSL --get \
  'https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/ArcGIS/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/0/query' \
  --data-urlencode "where=Grade IN ('I','II*')" \
  --data-urlencode 'geometry=-0.16,51.35,0.18,51.58' \
  --data-urlencode 'geometryType=esriGeometryEnvelope' \
  --data-urlencode 'inSR=4326' \
  --data-urlencode 'spatialRel=esriSpatialRelIntersects' \
  --data-urlencode 'outFields=ListEntry,Name,Grade,ListDate,AmendDate,hyperlink,NGR' \
  --data-urlencode 'returnGeometry=true' \
  --data-urlencode 'outSR=4326' \
  --data-urlencode 'f=geojson' \
  -o /tmp/nhle-listed-buildings.geojson
python3 scripts/import_historic_england.py /tmp/nhle-listed-buildings.geojson
```

© Crown Copyright 2026. Contains Ordnance Survey data © Crown copyright and database right 2026. Released under the Open Government Licence v3.0. Each generated record links to its NHLE list entry. The points locate list entries but do not describe their full footprint or decide whether a particular part of a structure is protected; consult the linked official entry for authoritative details.

## GLA Cultural Infrastructure Map

Cultural destinations for Lewisham, Greenwich and Southwark are generated from the Greater London Authority's Cultural Infrastructure Map 2023. The source CSV files are published under the Open Government Licence v3.0:

- https://data.london.gov.uk/dataset/cultural-infrastructure-map-2023-23697
- https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

The bundled fixture was generated on 27 July 2026. Most source audits were undertaken in spring and summer 2022 and published in 2023; the music-venues CSV was updated in March 2024. This is therefore a useful cultural-infrastructure snapshot, not a live venue directory. Records tell users to check opening hours and public access before visiting.

The importer applies the repository's exact borough boundaries and the review decisions in `data/corrections/gla-cultural-infrastructure.json`. It deliberately favours recognisable public destinations and distinctive creative infrastructure. Museums, public and commercial galleries, arts centres, cinemas and dedicated theatres are retained by default; archives, artists' workspaces, makerspaces, libraries, dance spaces and music venues use tighter allowlists. Generic offices, ordinary branch libraries, schools, obvious duplicates, weak pub listings and known closures are excluded. Targeted July 2026 checks also removed the closed Lewisham Migration Museum point and corrected Lewisham Heritage to its current Catford base.

Download the following CSV files from the dataset page into a temporary directory, then regenerate the bundled file:

```sh
python3 scripts/import_gla_culture.py \
  archives=/tmp/gla-culture/archives.csv \
  artists-workspaces=/tmp/gla-culture/artists-workspaces.csv \
  arts-centres=/tmp/gla-culture/arts-centres.csv \
  cinemas=/tmp/gla-culture/cinemas.csv \
  commercial-galleries=/tmp/gla-culture/commercial-galleries.csv \
  dance-performance=/tmp/gla-culture/dance-performance.csv \
  libraries=/tmp/gla-culture/libraries.csv \
  makerspaces=/tmp/gla-culture/makerspaces.csv \
  museums=/tmp/gla-culture/museums.csv \
  music-venues=/tmp/gla-culture/music-venues.csv \
  theatres=/tmp/gla-culture/theatres.csv
```

The source CSV files are not committed. Venue websites are retained where supplied, and generated records otherwise link back to the GLA dataset page. Re-running against a newer download requires reviewing additions, removals and the curation lists rather than treating the output as an automatic current-status feed.

## Lewisham maroon plaques

Titles, inscriptions and addresses originate in a Lewisham Council document released in response to this Freedom of Information request:

- https://www.whatdotheyknow.com/request/maroon_plaque_locations

The DOCX is committed in the repository as the public source artefact disclosed by Lewisham Council through that request. Coordinates are matched to Open Plaques where possible; two remaining points are explicitly marked approximate. The FOI response does not state an explicit open-data licence, so its inclusion records the document's provenance without asserting that it is covered by the application's GPL licence.

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
