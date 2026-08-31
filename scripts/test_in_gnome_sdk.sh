#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${ROOT}/com.nedrichards.lewishamwalks.Devel.json"
BUILD_DIR="${ROOT}/build-sdk-tests"

if [[ "$#" -gt 0 ]]; then
  TEST_ARGS=("$@")
else
  TEST_ARGS=(discover -s "${ROOT}/tests")
fi

flatpak-builder \
  --user \
  --force-clean \
  --disable-rofiles-fuse \
  --stop-at=lewisham-walks \
  "${BUILD_DIR}" \
  "${MANIFEST}"

flatpak build \
  --socket=wayland \
  --socket=fallback-x11 \
  --device=dri \
  --filesystem="${ROOT}:ro" \
  --env=PYTHONPATH="${ROOT}/src" \
  --env=GSETTINGS_BACKEND=memory \
  "${BUILD_DIR}" \
  python3 \
  -m unittest "${TEST_ARGS[@]}"
