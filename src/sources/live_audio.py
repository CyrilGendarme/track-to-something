"""Sounddevice-backed live audio source."""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from queue import Empty, Queue
from typing import TYPE_CHECKING, Iterator

import numpy as np

from src.config import AUDIO_BLOCK_SIZE, DEFAULT_SAMPLE_RATE, DEVICE_LATENCY, WASAPI_EXCLUSIVE
from .audio_source import AudioChunk

if TYPE_CHECKING:
    import sounddevice as sd

# sounddevice is imported lazily: importing it initializes PortAudio (driver
# enumeration), and the job worker processes - which re-import the main
# module on Windows - have no use for that.

_COINIT_MULTITHREADED = 0

logger = logging.getLogger(__name__)


@contextmanager
def _com_initialized():
    """Initialize COM on the current thread (Windows only).

    PortAudio's WASAPI backend needs COM on the thread that opens the stream.
    PortAudio initializes it on the thread that imported sounddevice (in the
    GUI, the Tk thread), so opening a WASAPI stream from the capture thread
    otherwise fails with "Unanticipated host error". MME and DirectSound
    don't need it.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes

    ole32 = ctypes.windll.ole32
    hr = ole32.CoInitializeEx(None, _COINIT_MULTITHREADED)
    try:
        yield
    finally:
        if hr in (0, 1):  # S_OK / S_FALSE: balance our initialization
            ole32.CoUninitialize()


class SoundDeviceSource:
    """Pull float32 blocks from an input or WASAPI loopback device."""

    def __init__(self, *, device: int | str, sample_rate: int = DEFAULT_SAMPLE_RATE,
                 channels: int = 2, block_size: int = AUDIO_BLOCK_SIZE, loopback: bool = False,
                 latency: str | float = DEVICE_LATENCY, wasapi_exclusive: bool = WASAPI_EXCLUSIVE):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.loopback = loopback
        self.latency = latency
        self.wasapi_exclusive = wasapi_exclusive
        # Whether the opened stream actually got WASAPI exclusive mode
        self.exclusive = False
        self._chunks: Queue[tuple[np.ndarray, float] | None] = Queue()
        self._stream: sd.InputStream | None = None
        self._closed = False
        # Blocks the device reported as dropped/corrupted (PortAudio status flags)
        self.overflows = 0
        # Input latency declared by the opened stream (seconds)
        self._input_latency = 0.0

    def _callback(self, indata, frames, time_info, status) -> None:
        # Runs on the PortAudio thread: copy and hand off, nothing else.
        if status:
            self.overflows += 1
        # Unix time of the block's first sample. The driver's ADC timestamp is
        # used only when plausible: PortAudio's WASAPI backend reports it
        # several ms in the *future*. Otherwise: arrival time minus the block
        # duration and the stream's declared input latency. (Scheduling jitter
        # is smoothed by the ring buffer's clock.)
        now = time.time()
        block_age = time_info.currentTime - time_info.inputBufferAdcTime
        if not (time_info.inputBufferAdcTime > 0 and frames / self.sample_rate <= block_age < 1.0):
            block_age = frames / self.sample_rate + self._input_latency
        self._chunks.put((indata.copy(), now - block_age))

    def __iter__(self) -> Iterator[AudioChunk]:
        import sounddevice as sd

        device = self._find_loopback_device(sd) if self.loopback else self.device
        # The stream is opened and closed by the iterating thread only; close()
        # just wakes it up with a sentinel.
        with _com_initialized():
            self._stream = self._open_stream(sd, device)
            self._input_latency = float(self._stream.latency)
            with self._stream:
                while not self._closed:
                    try:
                        item = self._chunks.get(timeout=1.0)
                    except Empty:
                        continue
                    if item is None:
                        break
                    samples, captured = item
                    yield AudioChunk(samples=samples, sample_rate=self.sample_rate, capture_time_s=captured)
            self._stream = None

    def _open_stream(self, sd, device) -> "sd.InputStream":
        def open_(extra_settings=None):
            return sd.InputStream(device=device, samplerate=self.sample_rate, channels=self.channels,
                                  blocksize=self.block_size, latency=self.latency, dtype="float32",
                                  callback=self._callback, extra_settings=extra_settings)

        if self.wasapi_exclusive and self._is_wasapi(sd, device):
            try:
                stream = open_(sd.WasapiSettings(exclusive=True))
                self.exclusive = True
                return stream
            except sd.PortAudioError as exc:
                logger.warning("WASAPI exclusive mode refused (%s); using shared mode", exc)
        self.exclusive = False
        return open_()

    @staticmethod
    def _is_wasapi(sd, device) -> bool:
        try:
            info = sd.query_devices(device, "input")
            return "WASAPI" in sd.query_hostapis(info["hostapi"])["name"]
        except (ValueError, sd.PortAudioError):
            return False

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
