"""Sounddevice-backed live audio source."""

from __future__ import annotations

from queue import Queue
from typing import Iterator

import numpy as np
import sounddevice as sd

from src.config import DEFAULT_SAMPLE_RATE, LOOPBACK_DEFAULT_SAMPLE_RATE
from .audio_source import AudioChunk


class SoundDeviceSource:
    """Pull float32 blocks from an input or WASAPI loopback device."""

    def __init__(self, *, device: int | str, sample_rate: int = DEFAULT_SAMPLE_RATE,
                 channels: int = 2, block_size: int = 4096, loopback: bool = False):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.loopback = loopback
        self._chunks: Queue[np.ndarray | None] = Queue()
        self._stream: sd.InputStream | None = None
        self._closed = False

    def _callback(self, indata, _frames, _time, _status) -> None:
        self._chunks.put(indata.copy())

    def __iter__(self) -> Iterator[AudioChunk]:
        if self.loopback:
            yield from self._iter_loopback()
            return

        self._stream = sd.InputStream(device=self.device, samplerate=self.sample_rate,
                                      channels=self.channels, blocksize=self.block_size,
                                      dtype="float32", callback=self._callback)
        with self._stream:
            while True:
                samples = self._chunks.get()
                if samples is None:
                    break
                yield AudioChunk(samples=samples, sample_rate=self.sample_rate)

    def _iter_loopback(self) -> Iterator[AudioChunk]:
        """Capture a Windows speaker loopback using sounddevice backend."""
        import sounddevice as sd
        
        # Find the loopback device
        loopback_device = self._find_loopback_device(sd)
        
        self._stream = sd.InputStream(
            device=loopback_device,
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.block_size,
            dtype="float32",
            callback=self._callback,
        )
        with self._stream:
            while not self._closed:
                try:
                    samples = self._chunks.get(timeout=1.0)  # Timeout to check _closed flag
                    if samples is None:
                        break
                    yield AudioChunk(samples=samples, sample_rate=self.sample_rate)
                except Exception:
                    # Timeout or empty queue, check if we should exit
                    if self._closed:
                        break

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
        self._closed = True
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._chunks.put(None)