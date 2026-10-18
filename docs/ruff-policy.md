# Ruff policy

Use the exact Ruff version in `requirements-dev.txt`. `required-version` in
`pyproject.toml` rejects older or newer executables so local checks agree with CI.
The supported Python target is 3.14, matching the GNOME 51 SDK.

Both commands are required locally and in source CI:

```sh
ruff check .
ruff check --preview --extend-select PLW1514,RUF056 .
```

`explicit-preview-rules = true` prevents the broad stable rule families from
silently enabling their experimental rules. The second command deliberately
opts into explicit file encodings and redundant falsy dictionary fallbacks.
Review new preview rules on Ruff upgrades before adding them to this command.

## Additional stable checks

- `PGH003` and `PGH004` require specific type and lint suppressions.
- `PGH005` catches mock assertions accessed without being called.
- `ISC004` catches implicit string concatenation inside collections, which can
  hide missing commas in styles, options and fixtures.
- `T100` catches debugger calls.
- `TRY201` and `TRY203` catch redundant exception handling and re-raising.
- `TRY400` and `TRY401` preserve useful traceback information when logging errors.

The existing security, timezone, logging, performance and modernization families
remain selected. Existing PyGObject import-order exceptions remain narrow.

## Preview review on Ruff 0.17.0

The unrestricted preview review produced 64 findings. This table records their
disposition; counts are a review snapshot, not a permanent expected baseline.

| Rules | Findings | Decision |
| --- | ---: | --- |
| `PLW1514` | 12 | Specify UTF-8 for JSON manifests and test fixtures; also fix equivalent unreported file operations. Enforce this rule. |
| `RUF056` | 1 | Remove the redundant `False` fallback before `bool()`. Enforce this rule. |
| `FURB140` | 2 | Retain the planner's generator expressions. Interleaved Python 3.14.7 host benchmarks found `starmap` 1–2% slower for 5, 12 and 48 points; full-planner changes were within noise. |
| `PLC1901` | 1 | Keep the explicit empty-string comparison in `iso_date_from_epoch_ms`: numeric epoch zero is valid, and is not missing data. Existing importer tests cover it. |
| `PLW0717` | 8 | Extract routing response parsing; retain the recovery boundaries reviewed below. |
| `S404` | 4 | Review subprocess calls rather than prohibit the import. Current calls use argument lists without a shell, with specific existing security annotations. |
| `S405` | 4 | Keep the XML imports. GPX export constructs XML; the two archive importers parse selected local source documents. Imported documents still require source review; these findings do not establish safe handling of arbitrary hostile XML. |
| `RUF105`, `RUF201` | 30 | Retain existing rule codes and specific `noqa` comments; avoid a separate preview syntax migration. |
| `RUF067` | 2 | Retain the small application-ID helper and constants in the package initializer. |

## Reviewed try blocks

- `OpenStreetMapRoutingProvider.route`: keep transport failures separate from
  response validation. `_parse_osrm_route` contains decoding and validation;
  the caller converts expected malformed-response exceptions into `RoutingError`.
  Invalid service results still trigger the honest local fallback.
- `LocationPortalProvider.request_location`, `_on_create_session_finished` and
  `_on_start_finished`: retain the D-Bus setup and subscription boundaries.
  Different binding exceptions must finish the request and release partial state.
- `MainWindow._generate_walk_worker`: retain the whole worker boundary so both
  expected and unexpected failures reach the GTK completion callback and clear
  the busy state. Keep unexpected failures visible to the user.
- `capture_ui.capture`: retain the callback boundary so snapshot and renderer
  failures are returned to the calling process rather than escaping an idle
  callback and leaving the capture waiting.
- `dependency-health.main`: retain the metadata/extension boundary that converts
  invalid SDK extension metadata into a failed health report.
- `test_ui_responsive._load_gtk`: retain optional host GTK/display detection.
  The authoritative SDK validation must be checked for actual GTK execution;
  host skips alone do not prove compatibility.

Do not enable `ALL`. Broad pytest conversion, private-member restrictions,
docstring requirements and complexity thresholds are poorly matched to the
unittest suite and GTK callback conventions. Revisit individual rules when they
identify a concrete correctness or maintenance improvement.
