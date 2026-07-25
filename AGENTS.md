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

Run the gate documented in `CONTRIBUTING.md`. GTK behaviour is authoritative in the pinned GNOME 50 SDK. For UI changes, additionally capture and inspect desktop and 390×780 layouts using `scripts/capture_ui.py`.

The development manifest uses local source and runs tests. The production manifest must use the public GitHub repository and an exact commit SHA. Do not repin it for ordinary unreviewed work.
