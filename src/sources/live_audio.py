"""Sounddevice-backed live audio source."""

from __future__ import annotations

from queue import Empty, Queue
from typing import Iterator

import numpy as np
import sounddevice as sd

from src.config import AUDIO_BLOCK_SIZE, DEFAULT_SAMPLE_RATE
from .audio_source import AudioChunk


class SoundDeviceSource:
    """Pull float32 blocks from an input or WASAPI loopback device."""

    def __init__(self, *, device: int | str, sample_rate: int = DEFAULT_SAMPLE_RATE,
                 channels: int = 2, block_size: int = AUDIO_BLOCK_SIZE, loopback: bool = False):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.loopback = loopback
        self._chunks: Queue[np.ndarray | None] = Queue()
        self._stream: sd.InputStream | None = None
        self._closed = False

    def _callback(self, indata, _frames, _time, _status) -> None:
        # Runs on the PortAudio thread: copy and hand off, nothing else.
        self._chunks.put(indata.copy())

    def __iter__(self) -> Iterator[AudioChunk]:
        device = self._find_loopback_device(sd) if self.loopback else self.device
        self._stream = sd.InputStream(device=device, samplerate=self.sample_rate,
                                      channels=self.channels, blocksize=self.block_size,
                                      dtype="float32", callback=self._callback)
        # The stream is opened and closed by the iterating thread only; close()
        # just wakes it up with a sentinel.
        with self._stream:
            while not self._closed:
                try:
                    samples = self._chunks.get(timeout=1.0)
                except Empty:
                    continue
                if samples is None:
                    break
                yield AudioChunk(samples=samples, sample_rate=self.sample_rate)
        self._stream = None

    def _find_loopback_device(self, sounddevice_module) -> int:
        """Find a Windows loopback/stereo mix device index."""
        devices = sounddevice_module.query_devices()
        
        # Search for loopback devices by name
        loopback_keywords = [
            "stereo mix",
            "what u hear",
            "wasapi loopback",
            "loopback",
            "virtual",
            "speaker mix",
        ]
        
        for i, device in enumerate(devices):
            if device.get("max_input_channels", 0) == 0:
                continue  # Skip output-only devices
            name_lower = device.get("name", "").casefold()
            for keyword in loopback_keywords:
                if keyword in name_lower:
                    return i
        
        # If device is explicitly set, try to use it
        if self.device is not None:
            if isinstance(self.device, int):
                return self.device
            # Try to find by name
            device_name = str(self.device).casefold()
            for i, device in enumerate(devices):
                if device_name in device.get("name", "").casefold():
                    if device.get("max_input_channels", 0) > 0:
                        return i
            raise ValueError(f"Loopback device not found: {self.device}")
        
        # Last resort: list available devices for user
        device_list = "\n  ".join(
            f"[{i}] {d.get('name', 'Unknown')} "
            f"(in:{d.get('max_input_channels', 0)} out:{d.get('max_output_channels', 0)})"
            for i, d in enumerate(devices)
        )
        raise RuntimeError(
            f"No loopback device found. Available devices:\n  {device_list}\n\n"
            f"To enable loopback:\n"
            f"  1. Enable 'Stereo Mix' in Windows Sound Settings\n"
            f"  2. Set MOSHPRO_TEST_APPLICATION_DEVICE with the device name or index"
        )

    def close(self) -> None:
        """Stop iteration. Safe to call more than once and from any thread."""
        if self._closed:
            return
        self._closed = True
        self._chunks.put(None)
