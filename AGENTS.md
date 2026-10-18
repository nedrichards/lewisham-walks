# Repository guidance

## Product contract

Lewisham Walks is a GNOME-first, adaptive GTK4/Libadwaita application for local discovery. Lewisham remains the centre of gravity, with neighbouring borough data only to improve border walks. No feature may require a commercial API key. Local planning and bundled discovery must continue to work when remote services fail.

## Repository map

- `src/lewisham_walks/`: application, planner, providers and UI.
- `tests/`: network-independent unit and GTK responsive tests.
- `data/`: desktop integration, schema, metadata, icons and data-generation inputs.
- `scripts/`: importers, test wrapper and UI capture tool.
- `com.nedrichards.lewishamwalks.Devel.json`: local development/test Flatpak.
- `com.nedrichards.lewishamwalks.json`: production manifest pinned to a reviewed Git commit.

## Working conventions

- Prefer GTK/Libadwaita platform behaviour and symbolic icons over custom chrome.
- Desktop is the primary layout; widths down to 360 px must remain usable without hidden or unreachable controls.
- Keep `Discovery` source-neutral. Put source-specific values in `attributes`; keep live functional `AmenityStop` values separate.
- Never disguise straight lines as pedestrian routing. Remote failure must be visible and non-fatal.
- Add a regression test with every behavioural fix. Mock network calls.
- Do not commit raw source documents, local captures, build output, secrets, `.agents`, or `.codex`.

## Validation

Run the gate documented in `CONTRIBUTING.md`. GTK behaviour is authoritative in the pinned GNOME 51 SDK, with GTK 4.24 and libadwaita 1.10. For UI changes, additionally capture and inspect desktop and 390×780 layouts using `scripts/capture_ui.py`.

The development manifest uses local source and runs tests. The production manifest must use the public GitHub repository and an exact commit SHA. Do not repin it for ordinary unreviewed work.

## Local Flatpak build storage

Use `./scripts/local-flatpak.sh` (defaults to development) for local checkout
builds and updates. Use `./scripts/local-flatpak.sh production` only when the
production manifest is intended. See `docs/local-flatpak.md`.
Use the normal manifests and keep their test gates enabled.

- Keep the durable update repository at `flatpak-repo/`. Never place it under
  `.flatpak-builder/` or another disposable build/cache directory.
- Use `.flatpak-builder/` for Builder state and `.flatpak-builder/staging` as
  the single staging location for both profiles. Build sequentially. Do not
  create per-task, per-validation or timestamped build/state/repository trees.
- Use `--delete-build-dirs` and clean module working directories and staging
  after success, failure and ordinary interruption, as the script does. Keep
  the reusable cache and downloads. Do not use `--keep-build-dirs` for routine
  automated builds. Debug retention needs an explicit task-specific reason
  and cleanup when finished.
- Do not run GNOME Builder or raw Builder commands concurrently with the
  script. Interactive GNOME Builder development remains supported via the
  `.Devel` manifest; prefer the script for automated validation and deployment.
- Keep directory-source `skip` lists excluding generated build directories,
  `target`, `.flatpak-builder*` and `flatpak-repo`, so artifacts are not copied
  into subsequent builds.
- Verify the installed app and its update origin after deployment. Never
  re-export an installed `export/` directory.

There is no enforced storage budget. Do not change Rust incremental/debug
settings as part of storage housekeeping without a separate request.


`scripts/test_in_gnome_sdk.sh` delegates to `local-flatpak.sh sdk-test`, using
the same staging, lock and cleanup for focused SDK unittest runs.
