# Contributing

Issues and small, focused pull requests are welcome. Lewisham Walks is deliberately GNOME-centric, Lewisham-first, adaptive from desktop to narrow screens, and usable without a paid API key.

## Development

Use Python 3.10 or newer, Meson, Ruff, and the GNOME 50 SDK. Keep planning and data transformations testable without GTK or network access. Network providers must retain timeouts, an identifying user agent, and an honest local fallback where practical.

Before opening a pull request, run:

```sh
ruff check .
python3 -m compileall -q src scripts tests
PYTHONPATH=src python3 -m unittest discover -s tests
meson setup --reconfigure build-dir
meson test -C build-dir --print-errorlogs
glib-compile-schemas --strict --dry-run data
appstreamcli validate --pedantic --no-net data/com.nedrichards.lewishamwalks.metainfo.xml.in
./scripts/test_in_gnome_sdk.sh
```

For packaging changes, also build `com.nedrichards.lewishamwalks.Devel.json`. The development manifest always uses the local checkout and runs tests. The production manifest is pinned to an exact public Git commit and is updated only for a reviewed checkpoint or release.

Do not commit raw source documents, generated build output, credentials, UI review captures, or agent state. If adding a discovery source, document its provenance, licence, regeneration command, and accuracy limitations in `DATA_SOURCES.md`.

Commit messages should be short and semantic, describing one coherent behaviour or repository change.
