"""Capture audio rendered by an application/system playback device."""

from __future__ import annotations

import platform

from .system_loopback import SystemLoopbackSource


class ApplicationAudioSource(SystemLoopbackSource):
    """Capture what a running application plays, via its output device's loopback.

    Windows mixes every application on an output device, so this records the
    whole mix of that device (the default output unless ``device`` names
    another), not the application alone.
    """

    def __init__(self, *, application_name: str, device: str | None = None, **kwargs):
        self.application_name = application_name
        self._validate_application()
        super().__init__(speaker=device, **kwargs)

    def _validate_application(self) -> None:
        """Ensure the requested Windows application is currently running."""
        if platform.system() != "Windows":
            return
        try:
            import psutil
        except ImportError as exc:
            raise RuntimeError("Install psutil to resolve a Windows application name") from exc

        wanted = self.application_name.casefold().removesuffix(".exe")
        running = {
            (process.info["name"] or "").casefold().removesuffix(".exe")
            for process in psutil.process_iter(["name"])
        }
        if wanted not in running:
            raise RuntimeError(f"Windows application is not running: {self.application_name}")
