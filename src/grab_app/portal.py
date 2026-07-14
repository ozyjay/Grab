"""Asynchronous XDG Screenshot portal client."""

from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_INTERFACE = "org.freedesktop.portal.Screenshot"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"


@dataclass(frozen=True)
class CaptureResult:
    status: str
    uri: str | None = None
    message: str | None = None


CaptureCallback = Callable[[CaptureResult], None]


class ScreenshotPortal:
    def __init__(self, connection: Gio.DBusConnection | None = None) -> None:
        self.connection = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.proxy = Gio.DBusProxy.new_sync(
            self.connection,
            Gio.DBusProxyFlags.NONE,
            None,
            PORTAL_BUS,
            PORTAL_PATH,
            SCREENSHOT_INTERFACE,
            None,
        )

    def capture(self, callback: CaptureCallback) -> None:
        token = "grab_" + uuid.uuid4().hex
        unique_name = (self.connection.get_unique_name() or "").lstrip(":").replace(".", "_")
        request_path = f"{PORTAL_PATH}/request/{unique_name}/{token}"
        subscription = 0
        finished = False

        def finish(result: CaptureResult) -> None:
            nonlocal finished, subscription
            if finished:
                return
            finished = True
            if subscription:
                self.connection.signal_unsubscribe(subscription)
                subscription = 0
            callback(result)

        def on_response(
            _connection: Gio.DBusConnection,
            _sender: str,
            _path: str,
            _interface: str,
            _signal: str,
            parameters: GLib.Variant,
            _data: object,
        ) -> None:
            response, values = parameters.unpack()
            if response == 0:
                uri_value = values.get("uri") if isinstance(values, dict) else None
                uri = uri_value.unpack() if isinstance(uri_value, GLib.Variant) else uri_value
                if isinstance(uri, str) and uri:
                    finish(CaptureResult("success", uri=uri))
                else:
                    finish(CaptureResult("error", message="The screenshot portal returned no image."))
            elif response == 1:
                finish(CaptureResult("cancelled"))
            else:
                finish(CaptureResult("error", message="The screenshot request was denied."))

        subscription = self.connection.signal_subscribe(
            PORTAL_BUS,
            REQUEST_INTERFACE,
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
            None,
        )

        options: dict[str, GLib.Variant] = {
            "handle_token": GLib.Variant("s", token),
            "interactive": GLib.Variant("b", False),
        }
        version = self.proxy.get_cached_property("version")
        if version is not None and version.unpack() >= 3:
            options["target"] = GLib.Variant("u", 1)

        def on_called(proxy: Gio.DBusProxy, result: Gio.AsyncResult, _data: object) -> None:
            try:
                returned = proxy.call_finish(result).unpack()[0]
                if returned != request_path:
                    finish(
                        CaptureResult(
                            "error", message="The screenshot portal returned an invalid request handle."
                        )
                    )
            except GLib.Error as error:
                finish(CaptureResult("error", message=f"Screenshot service unavailable: {error.message}"))

        self.proxy.call(
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            on_called,
            None,
        )
