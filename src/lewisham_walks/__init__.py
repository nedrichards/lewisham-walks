"""Lewisham local discovery walk planner."""

import os

APP_ID = "com.nedrichards.lewishamwalks"


def runtime_app_id(flatpak_id: str | None = None) -> str:
    """Return the D-Bus application ID permitted by the current Flatpak."""
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID")
    if flatpak_id in {APP_ID, f"{APP_ID}.Devel"}:
        return flatpak_id
    return APP_ID
