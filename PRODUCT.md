# Product direction

Lewisham Walks should help someone step outside and notice something nearby that they did not know before. Route generation is the mechanism; local discovery is the product.

## Experience principles

- Start with stories, not configuration. The main view offers readable nearby discoveries before asking the user to make a route.
- Keep the map legible and exploratory. Begin with a useful Lewisham-first selection, then repick a spatially distributed set from the full corpus as the viewport moves. Distinguish Lewisham's own collection, and number only the stops in an active walk.
- Make a good choice on the user's behalf. A walk should favour accurate, curated, varied records, avoid duplicate locations and fit the available time.
- Preserve surprise. Stories explicitly marked as discovered are avoided when alternatives exist, and “Try Another” varies otherwise equivalent local choices.
- Be honest about uncertainty. Provenance and coordinate quality are available in the story view. If live pedestrian routing fails, the result is labelled as approximate rather than silently drawing a fake road route.
- Require no account or secret. Bundled data and local planning always work. Keyless open services add current postcode lookup, walking directions and optional amenities.
- Feel like GNOME. Use Libadwaita's hierarchy, typography, controls, adaptive layouts, restrained colour and platform settings rather than custom application chrome.

## Data model

The first useful corpus combines the Lewisham maroon plaque list, Open Plaques records from Lewisham, Greenwich and Southwark, and Freddy's Blossom Walk. Lewisham remains the centre of gravity, while a small amount of the nearest accurate border context keeps walks useful when they cross an administrative line. OpenStreetMap supplies maps, walking routes, cafes and pubs.

Bundled narrative points use the source-neutral `Discovery` model. Every record has an explicit kind, collection and provenance; source-specific details live in attributes rather than becoming fields on the shared model. `AmenityStop` remains separate because cafes and pubs are optional, live, functional route stops rather than bundled stories. Both become `RouteVisit` entries in a generated itinerary.

## Network behaviour

One route request is made after the local planner has chosen all stops. The FOSSGIS pedestrian routing service is used with an identifying user agent and its one-request-per-second fair-use limit. Failure falls back to local straight-line estimates. Plaque and blossom discovery does not depend on the network.

## Next valuable sources

New sources should earn their place by adding a distinct reason to walk, reliable coordinates and useful source attribution. Strong candidates are public art, notable trees, local nature or conservation records, and Lewisham heritage assets. Source count alone is not a success metric.
