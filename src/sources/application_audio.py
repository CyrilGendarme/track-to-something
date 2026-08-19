"""Capture audio rendered by an application/system playback device."""

from __future__ import annotations

import platform

from .live_audio import SoundDeviceSource


class ApplicationAudioSource(SoundDeviceSource):
    """Capture a laptop application's output through a loopback device."""

    def __init__(self, *, application_name: str, device: int | str | None = None, **kwargs):
        self.application_name = application_name
        self._validate_application()
        super().__init__(device=device, loopback=True, **kwargs)

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
