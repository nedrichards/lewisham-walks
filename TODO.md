# TODO

Lewisham Walks remains a small, GNOME-first app for discovering Lewisham and its immediate borders.

## Next

- [x] Show the walking directions already returned by the routing service, grouped sensibly between story stops.
- [ ] Field-test 30, 60 and 90-minute walks from several parts of Lewisham, comparing predicted and actual duration, route quality and story selection.
- [x] Add the standard GNOME application actions: About, Preferences, Keyboard Shortcuts and Quit.
- [ ] Complete a keyboard and accessibility pass: accessible names, focus order, large text, high contrast and screen-reader behaviour.
- [ ] Make CI run the GTK tests with real Libshumate rather than skipping that integration when no display is available.
- [ ] Add cancellation for route generation and clearer progress stages for postcode, amenity and routing requests.

## Before the first release

- [ ] Resolve redistribution permission for Freddy's Blossom Walk and the Lewisham FOI plaque data, or choose a release-safe fallback.
- [ ] Curate weak imported records: approximate coordinates, duplicate locations, unwieldy titles and excessively long descriptions.
- [ ] Run a small real-world beta and fix anything that prevents completing a walk.
- [ ] Review privacy, network-service attribution and failure messages from the packaged Flatpak.
- [ ] Refresh screenshots and AppStream release notes.
- [ ] Tag `v0.1.0`, repin the production manifest and publish a GitHub release.
- [ ] Prepare and submit the production Flatpak to Flathub.

## Later

- [x] Remember the last successfully used start postcode without retaining map-picked coordinates or a location history.
- [ ] Consider carefully licensed public art, notable tree, nature or heritage sources.
- [ ] Add translation infrastructure if there is genuine demand.
