"""Audio capture worker - pulls blocks from a source into the ring buffer."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

import numpy as np
from scipy import signal as scipy_signal

from src.config import AUDIO_APPLY_HPF, AUDIO_BIT_DEPTH
from src.engine.base import Worker
from src.engine.buffer import RingBuffer

logger = logging.getLogger(__name__)

HPF_CUTOFF_HZ = 20.0


class AudioCaptureWorker(Worker):
    """The single writer of the ring buffer.

    Does only cheap, stateful conditioning (mono mix, high-pass, optional
    quantization) so it never holds up the device. All analysis happens in
    readers of the ring buffer.
    """

    def __init__(
        self,
        name: str,
        audio_source: Callable[[], Any],
        buffer: RingBuffer,
        daemon: bool = False,
    ):
        """Initialize audio capture worker.

        Args:
            name: Worker thread name
            audio_source: Callable that returns an iterable of AudioChunk
            buffer: Ring buffer to write captured mono audio into
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, daemon=daemon)
        self.audio_source = audio_source
        self.buffer = buffer
        self.chunk_count = 0
        self._source: Any = None
        self._hpf_sos: np.ndarray | None = None
        self._hpf_zi: np.ndarray | None = None
        if AUDIO_APPLY_HPF:
            self._hpf_sos = scipy_signal.butter(2, HPF_CUTOFF_HZ, btype="high", fs=buffer.sample_rate, output="sos")
            self._hpf_zi = np.zeros((self._hpf_sos.shape[0], 2))

    def _condition(self, samples: np.ndarray) -> np.ndarray:
        """Mix to mono, high-pass (state carried across chunks), quantize."""
        mono = samples.mean(axis=1) if samples.ndim == 2 else samples
        mono = mono.astype(np.float64, copy=False)
        if self._hpf_sos is not None:
            mono, self._hpf_zi = scipy_signal.sosfilt(self._hpf_sos, mono, zi=self._hpf_zi)
        if AUDIO_BIT_DEPTH < 16:
            levels = (1 << (AUDIO_BIT_DEPTH - 1)) - 1
            mono = np.clip(np.round(mono * levels) / levels, -1.0, 1.0)
        return mono.astype(np.float32)

    def _work(self) -> None:
        """Capture audio until the source ends or stop is requested."""
        try:
            self._source = self.audio_source()
            for chunk in self._source:
                if self.is_stopped():
                    break
                if int(chunk.sample_rate) != self.buffer.sample_rate:
                    raise ValueError(
                        f"Source sample rate {chunk.sample_rate} Hz does not match the "
                        f"pipeline sample rate {self.buffer.sample_rate} Hz"
                    )
                self.buffer.write(self._condition(np.asarray(chunk.samples, dtype=np.float32)))
                self.chunk_count += 1
        finally:
            self.buffer.close()
            self._close_source()

    def stop(self) -> None:
        """Request stop and close the source so a blocking read returns."""
        super().stop()
        # A generator can't be closed from another thread while it is running;
        # it sees the stop flag on its next chunk instead.
        if self._source is not None and not inspect.isgenerator(self._source):
            self._close_source()

    def _close_source(self) -> None:
        close = getattr(self._source, "close", None)
        if close is None:
            return
        try:
            close()
        except Exception:  # noqa: BLE001 - closing is best effort
            logger.debug("[%s] Error closing audio source", self.name, exc_info=True)
