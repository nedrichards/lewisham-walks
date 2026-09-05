# Flathub readiness

The application is not yet submitted. This checklist records the local audit of
5 September 2026 and the work needed to turn it into a reviewed stable release.
The production source commit remains unchanged until that release is reviewed.

## Verified locally

- Ruff, Python compilation, strict GSettings validation and pedantic AppStream validation pass.
- All 120 tests pass in GNOME 50, including the GTK responsive tests.
- The development Flatpak builds and its Meson tests pass.
- The production manifest passes `flatpak-builder-lint manifest`.
- Desktop and 390 × 780 captures were inspected, including a rendered street map
  and the narrow-layout approximation warning. Cold network tiles required more
  than the capture tool's default three-second delay.
- App code and data attribution are installed under `share/licenses`; development
  headers, static libraries and build metadata are removed from the package.

The build-directory linter reports `appstream-external-screenshot-url` because the
local build does not mirror GitHub screenshots to Flathub's media service. Run the
normal Flathub build and repository linter for the reviewed release before claiming
that the distributable passes all package checks.

## Fixes in this audit

- Connection failures and malformed walking routes reach the honest local fallback.
- Routing fallback preserves the itinerary and does not repeat cafe/pub searches.
- Local straight-line plans and GPX exports retain approximation warnings.
- London amenity searches use worldwide Overpass servers, not the Switzerland-only
  server. Requests identify the application; Nominatim searches stop after a useful
  result and are spaced at least one second apart within the process.
- Zero longitude is retained when parsing amenity points.
- The planner computes topics once per candidate and rejects wholly unreachable
  discovery sets in one pass. Nonpositive highlight limits return no stories.
- Closed maps disconnect from the global style manager and cancel pending refresh
  work and theme animations.
- UI captures include the window background and header.

On the same host and 620-record corpus, mean local planning time fell from 32.4 ms
to 11.5 ms; a distant start fell from 1,186 ms to 1.3 ms (20 runs each). These are
planner measurements, not end-to-end startup or network latency guarantees.
Reproduce with `PYTHONPATH=src python3 scripts/benchmark_planner.py`.
For cold-map captures, set `LEWISHAM_WALKS_CAPTURE_DELAY_MS=15000` in the app sandbox.

## Before release and submission

1. Review and publish the source changes, choose a stable release version, update
   the release metadata with its actual date and notes, and tag the reviewed commit.
   The existing 0.1.0 metadata describes a development checkpoint; it is not proof
   of a published stable release.
2. Update the production manifest to that exact public commit. Build the production
   identity, validate the resulting repository and test its installed desktop entry,
   location permission flow, GPX save portal and offline behavior. Exercise x86_64
   and aarch64; the local validation here covers x86_64 only.
3. Keep both local datasets. The maintainer confirms that the maroon-plaque and
   blossom data are public and were released under FOI. Record the corresponding
   disclosure references and reuse basis in `DATA_SOURCES.md` for distributor review;
   the current file links the plaque FOI but not the blossom disclosure. Public
   disclosure alone should not be described as a newly granted open licence.
4. Review the community-service deployment limits. Nominatim's one-request-per-second
   limit applies across an application's users, not merely each installation. The
   process limiter is not a global traffic budget. Its endpoint can be switched via
   `LEWISHAM_WALKS_NOMINATIM_ENDPOINT` without a code update; agree an appropriate
   endpoint/traffic arrangement before wider distribution.
5. Build with Flathub's `flathub-build` wrapper to mirror screenshots, then run the
   repository linter. Refresh the public screenshots from the reviewed release if
   its appearance has changed; do not publish temporary audit captures as-is.
6. Confirm the application identity's relationship to `nedrichards.com` and prepare
   domain verification. Keep the existing narrow network/display/GPU permissions.
7. Read the current submission requirements. A human must author and open the
   submission against `flathub/flathub`'s `new-pr` branch and handle review. Disclose
   the affected parts and approximate extent of AI-generated material, including
   this audit's changes; this file is internal release guidance, not PR text.

## References

- [Flathub requirements](https://docs.flathub.org/docs/for-app-authors/requirements)
- [Submission and recommended build/lint commands](https://docs.flathub.org/docs/for-app-authors/submission)
- [Metadata quality guidelines](https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines/quality-guidelines)
- [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)
- [Swiss Overpass coverage](https://www.osm.ch/entwickler.html)
- [ICO guidance on FOI and other laws](https://ico.org.uk/for-organisations/foi/guide-to-managing-an-foi-request/foi-and-other-laws/)
