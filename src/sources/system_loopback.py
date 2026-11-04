"""Capture what an output device is playing (WASAPI loopback, Windows).

PortAudio (sounddevice) can't open an output device for recording, so this
uses the SoundCard package, which talks to WASAPI directly. The audio is the
device's whole mix: every application playing on it.
"""

from __future__ import annotations

import logging
import time
import warnings
from typing import Iterator

from src.config import AUDIO_BLOCK_SIZE
from .audio_source import AudioChunk
from .live_audio import _com_initialized

logger = logging.getLogger(__name__)

# Discontinuities while the stream starts up are normal, not dropped audio
STARTUP_GRACE_S = 1.0


def list_loopback_speakers() -> list[tuple[str, str]]:
    """``(id, name)`` of every output device that can be recorded."""
    import soundcard

    return [(speaker.id, speaker.name) for speaker in soundcard.all_speakers()]


class SystemLoopbackSource:
    """Stream what ``speaker`` is playing, as float32 blocks.

    Args:
        speaker: Output device id or name substring; None for the default
            output device (resolved when the stream starts).
        sample_rate: Capture rate; use the device's mix rate to avoid
            resampling (WASAPI converts otherwise).
        channels: Channels to capture.
        block_size: Frames per chunk.
    """

    def __init__(self, *, speaker: str | None = None, sample_rate: int = 48000,
                 channels: int = 2, block_size: int = AUDIO_BLOCK_SIZE):
        self.speaker = speaker
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.exclusive = False  # loopback always shares the device
        # Blocks WASAPI reported as discontinuous after start-up (dropped audio)
        self.overflows = 0
        self.speaker_name: str | None = None
        self._closed = False

    def _resolve_speaker(self, soundcard):
        if self.speaker is None:
            return soundcard.default_speaker()
        wanted = self.speaker.casefold()
        for speaker in soundcard.all_speakers():
            if speaker.id == self.speaker or wanted in speaker.name.casefold():
                return speaker
        names = ", ".join(s.name for s in soundcard.all_speakers())
        raise ValueError(f"Output device not found: {self.speaker!r} (available: {names})")

    def __iter__(self) -> Iterator[AudioChunk]:
        # Imported here: it initializes COM and enumerates devices on import
        import soundcard

        with _com_initialized():
            speaker = self._resolve_speaker(soundcard)
            self.speaker_name = speaker.name
            microphone = soundcard.get_microphone(speaker.id, include_loopback=True)
            logger.info("Capturing loopback of %s at %d Hz", speaker.name, self.sample_rate)
            with microphone.recorder(samplerate=self.sample_rate, channels=self.channels,
                                     blocksize=self.block_size) as recorder:
                started = time.monotonic()
                while not self._closed:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always", soundcard.SoundcardRuntimeWarning)
                        samples = recorder.record(numframes=self.block_size)
                    if caught and time.monotonic() - started > STARTUP_GRACE_S:
                        self.overflows += 1
                    if not len(samples):
                        continue
                    # No device timestamp: the block's first sample was
                    # captured about one block before it was handed over
                    captured = time.time() - len(samples) / self.sample_rate
                    yield AudioChunk(samples=samples, sample_rate=self.sample_rate, capture_time_s=captured)

    def close(self) -> None:
        """Stop iteration (the current block finishes first). Any thread."""
        self._closed = True
