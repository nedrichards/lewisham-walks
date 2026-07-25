#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_REF="${SDK_REF:-org.gnome.Sdk/x86_64/50}"
PYTHONPATH_VALUE="${ROOT}/src"
FILESYSTEM_ARGS=("--filesystem=${ROOT}")

HOST_SITE_PACKAGES="$(
  python - <<'PY'
from pathlib import Path

try:
    import requests
except Exception:
    raise SystemExit(0)

print(Path(requests.__file__).resolve().parents[1])
PY
)"

if [[ -n "${HOST_SITE_PACKAGES}" ]]; then
  PYTHONPATH_VALUE="${PYTHONPATH_VALUE}:${HOST_SITE_PACKAGES}"
  FILESYSTEM_ARGS+=("--filesystem=${HOST_SITE_PACKAGES}:ro")
fi

if [[ "$#" -gt 0 ]]; then
  TEST_ARGS=("$@")
else
  TEST_ARGS=(discover -s "${ROOT}/tests")
fi

flatpak run \
  --user \
  --socket=wayland \
  --socket=fallback-x11 \
  "${FILESYSTEM_ARGS[@]}" \
  --env=PYTHONPATH="${PYTHONPATH_VALUE}" \
  --env=GSETTINGS_BACKEND=memory \
  --command=python3 \
  "${SDK_REF}" \
  -m unittest "${TEST_ARGS[@]}"
