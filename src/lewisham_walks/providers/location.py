from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Callable
from typing import Any

from ..models import Coordinate

LocationCallback = Callable[[Coordinate | None, str | None], None]


class LocationPortalProvider:
    """Request the current location through xdg-desktop-portal."""

    BUS_NAME = "org.freedesktop.portal.Desktop"
    OBJECT_PATH = "/org/freedesktop/portal/desktop"
    LOCATION_INTERFACE = "org.freedesktop.portal.Location"
    REQUEST_INTERFACE = "org.freedesktop.portal.Request"
    SESSION_INTERFACE = "org.freedesktop.portal.Session"

    def __init__(self, timeout_seconds: int = 30) -> None:
        self._timeout_seconds = timeout_seconds
        self._active = False
        self._callback: LocationCallback | None = None
        self._connection = None
        self._proxy = None
        self._session_handle: str | None = None
        self._location_signal_id: int | None = None
        self._response_signal_id: int | None = None
        self._session_closed_signal_id: int | None = None
        self._timeout_id: int | None = None

    def request_location(self, parent_window: str, callback: LocationCallback) -> None:
        if self._active:
            callback(None, "A location request is already in progress.")
            return

        self._active = True
        self._callback = callback
        try:
            from gi.repository import Gio, GLib

            self._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._debug(f"connected to session bus as {self._connection.get_unique_name()}")
            self._proxy = Gio.DBusProxy.new_sync(
                self._connection,
                Gio.DBusProxyFlags.NONE,
                None,
                self.BUS_NAME,
                self.OBJECT_PATH,
                self.LOCATION_INTERFACE,
                None,
            )
            options = {
                "session_handle_token": GLib.Variant("s", self._new_token("lewisham_location_session")),
                "accuracy": GLib.Variant("u", 4),
                "distance-threshold": GLib.Variant("u", 0),
                "time-threshold": GLib.Variant("u", 0),
            }
            self._debug(f"CreateSession options={_format_variant_dict(options)}")
            self._proxy.call(
                "CreateSession",
                GLib.Variant("(a{sv})", (options,)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                self._on_create_session_finished,
                parent_window,
            )
        except Exception as error:
            self._finish(None, f"Could not request current location: {error}")

    def cancel(self) -> None:
        if self._active:
            self._finish(None, "Location sharing was cancelled.")

    def _on_create_session_finished(self, proxy, result, parent_window: str) -> None:
        try:
            from gi.repository import Gio, GLib

            self._session_handle = proxy.call_finish(result).unpack()[0]
            self._debug(f"CreateSession returned session_handle={self._session_handle}")
            self._location_signal_id = self._connection.signal_subscribe(
                self.BUS_NAME,
                self.LOCATION_INTERFACE,
                "LocationUpdated",
                self.OBJECT_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_location_updated,
            )
            self._session_closed_signal_id = self._connection.signal_subscribe(
                self.BUS_NAME,
                self.SESSION_INTERFACE,
                "Closed",
                self._session_handle,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_session_closed,
            )
            request_token = self._new_token("lewisham_location_start")
            request_path = self._request_path(request_token)
            self._debug(f"subscribing to Start Response at request_path={request_path}")
            self._response_signal_id = self._connection.signal_subscribe(
                self.BUS_NAME,
                self.REQUEST_INTERFACE,
                "Response",
                request_path,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_start_response,
            )
            self._timeout_id = GLib.timeout_add_seconds(
                self._timeout_seconds,
                self._on_location_timeout,
            )
            options = {"handle_token": GLib.Variant("s", request_token)}
            self._debug(f"Start session_handle={self._session_handle} parent_window={parent_window!r}")
            proxy.call(
                "Start",
                GLib.Variant("(osa{sv})", (self._session_handle, parent_window, options)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                self._on_start_finished,
                request_path,
            )
        except Exception as error:
            self._finish(None, f"Could not start location sharing: {error}")

    def _on_start_finished(self, proxy, result, expected_request_path: str) -> None:
        try:
            request_path = proxy.call_finish(result).unpack()[0]
            self._debug(f"Start returned request_path={request_path}")
            if request_path != expected_request_path and self._response_signal_id is not None:
                from gi.repository import Gio

                self._debug(f"Start request path differed from expected {expected_request_path}; resubscribing")
                self._connection.signal_unsubscribe(self._response_signal_id)
                self._response_signal_id = self._connection.signal_subscribe(
                    self.BUS_NAME,
                    self.REQUEST_INTERFACE,
                    "Response",
                    request_path,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    self._on_start_response,
                )
        except Exception as error:
            self._finish(None, f"Could not start location sharing: {error}")

    def _on_start_response(self, _connection, sender, path, _interface, _signal, parameters) -> None:
        response, results = parameters.unpack()
        self._debug(f"Start Response sender={sender} path={path} response={response} results={_format_variant_dict(results)}")
        if response == 0:
            return
        if response == 1:
            self._finish(None, "Location sharing was cancelled.")
        else:
            self._finish(None, "Location sharing could not be started.")

    def _on_location_updated(self, _connection, sender, path, _interface, _signal, parameters) -> None:
        session_handle, location = parameters.unpack()
        if session_handle != self._session_handle:
            self._debug(
                "ignoring LocationUpdated for different session "
                f"sender={sender} path={path} session_handle={session_handle}"
            )
            return
        self._debug(
            "LocationUpdated "
            f"sender={sender} path={path} session_handle={session_handle} location={_format_variant_dict(location)}"
        )
        latitude = _variant_value(location.get("Latitude"))
        longitude = _variant_value(location.get("Longitude"))
        if latitude is None or longitude is None:
            self._finish(None, "The location portal did not return coordinates.")
            return
        self._finish(Coordinate(float(latitude), float(longitude)), None)

    def _on_session_closed(self, _connection, sender, path, _interface, _signal, parameters) -> None:
        details = parameters.unpack()[0]
        self._debug(f"Session Closed sender={sender} path={path} details={_format_variant_dict(details)}")
        self._finish(None, "The location session was closed before coordinates were available.")

    def _on_location_timeout(self) -> bool:
        self._timeout_id = None
        self._debug("timed out waiting for LocationUpdated")
        self._finish(None, "Timed out waiting for the current location.")
        return False

    def _finish(self, coordinate: Coordinate | None, error_message: str | None) -> None:
        callback = self._callback
        self._cleanup()
        if callback is not None:
            callback(coordinate, error_message)

    def _cleanup(self) -> None:
        try:
            from gi.repository import GLib

            if self._timeout_id is not None:
                GLib.source_remove(self._timeout_id)
        except Exception:
            pass
        self._timeout_id = None

        if self._connection is not None:
            for signal_id in (self._location_signal_id, self._response_signal_id, self._session_closed_signal_id):
                if signal_id is not None:
                    self._connection.signal_unsubscribe(signal_id)
            if self._session_handle is not None:
                try:
                    self._debug(f"closing session {self._session_handle}")
                    self._connection.call(
                        self.BUS_NAME,
                        self._session_handle,
                        self.SESSION_INTERFACE,
                        "Close",
                        None,
                        None,
                        0,
                        -1,
                        None,
                        None,
                        None,
                    )
                except Exception:
                    pass

        self._active = False
        self._callback = None
        self._connection = None
        self._proxy = None
        self._session_handle = None
        self._location_signal_id = None
        self._response_signal_id = None
        self._session_closed_signal_id = None

    def _request_path(self, token: str) -> str:
        unique_name = self._connection.get_unique_name()
        sender = unique_name[1:].replace(".", "_")
        return f"{self.OBJECT_PATH}/request/{sender}/{token}"

    def _new_token(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _debug(self, message: str) -> None:
        if os.environ.get("LEWISHAM_LOCATION_DEBUG"):
            print(f"[lewisham-location] {message}", file=sys.stderr, flush=True)


def _variant_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "unpack"):
        return value.unpack()
    return value


def _format_variant_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: _variant_value(value) for key, value in values.items()}
