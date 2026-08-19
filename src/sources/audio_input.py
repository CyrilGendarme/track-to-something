"""Capture an external microphone, mixer, or USB audio interface."""

from .live_audio import SoundDeviceSource


class AudioInputSource(SoundDeviceSource):
    """Stream samples from an explicitly selected audio input device."""

    def __init__(self, *, device: int | str, **kwargs):
        super().__init__(device=device, loopback=False, **kwargs)