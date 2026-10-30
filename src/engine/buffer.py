"""Thread-safe mono ring buffer addressed by absolute sample index."""

from __future__ import annotations

import threading

import numpy as np

# Capture clock smoothing (EMA weight per write) and the jump that is treated
# as a discontinuity rather than jitter.
CLOCK_SMOOTHING = 0.05
CLOCK_RESYNC_S = 0.1


class RingBuffer:
    """Single-writer / multi-reader ring buffer for mono float32 audio.

    Positions are absolute sample counts since the stream started
    (``total_written``), so readers can ask for an exact span, detect that
    they fell behind (the span was overwritten), and tag their results with
    the samples they covered.
    """

    def __init__(self, capacity_samples: int, sample_rate: int):
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be positive")
        self.capacity = int(capacity_samples)
        self.sample_rate = int(sample_rate)
        self._data = np.zeros(self.capacity, dtype=np.float32)
        self._total_written = 0
        self._closed = False
        # Smoothed (capture Unix time - stream time) offset; None until the
        # source provides capture times
        self._clock_offset: float | None = None
        self._cond = threading.Condition(threading.Lock())

    @property
    def total_written(self) -> int:
        with self._cond:
            return self._total_written

    @property
    def closed(self) -> bool:
        with self._cond:
            return self._closed

    def write(self, samples: np.ndarray, capture_time_s: float | None = None) -> None:
        """Append mono samples and wake up readers waiting for new data.

        Args:
            samples: Mono samples
            capture_time_s: Unix time the first sample was captured, if known
        """
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        n = samples.size
        if n == 0:
            return
        if n > self.capacity:
            samples = samples[-self.capacity:]
        with self._cond:
            if capture_time_s is not None:
                offset = capture_time_s - self._total_written / self.sample_rate
                if self._clock_offset is None or abs(offset - self._clock_offset) > CLOCK_RESYNC_S:
                    self._clock_offset = offset  # first write, or a discontinuity (e.g. dropout)
                else:
                    # EMA smooths per-block callback jitter; tolerates slow clock drift
                    self._clock_offset += CLOCK_SMOOTHING * (offset - self._clock_offset)
            start = self._total_written % self.capacity
            m = samples.size
            first = min(m, self.capacity - start)
            self._data[start:start + first] = samples[:first]
            if first < m:
                self._data[:m - first] = samples[first:]
            self._total_written += n
            self._cond.notify_all()

    def close(self) -> None:
        """Mark the stream as finished (wakes up waiting readers)."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def unix_time_of(self, stream_time_s: float) -> float | None:
        """Wall-clock (Unix) time at which stream time ``stream_time_s`` was
        captured, or None if the source doesn't provide capture times."""
        with self._cond:
            offset = self._clock_offset
        return None if offset is None else offset + stream_time_s

    def wait_for(self, position: int, timeout: float) -> int:
        """Block until ``total_written >= position``, the buffer is closed, or timeout.

        Returns the current ``total_written``.
        """
        with self._cond:
            self._cond.wait_for(lambda: self._total_written >= position or self._closed, timeout=timeout)
            return self._total_written

    def read(self, end: int, n: int) -> np.ndarray | None:
        """Return the ``n`` samples ending at absolute position ``end``.

        Returns None if part of that span has already been overwritten or has
        not been written yet. Samples before the stream start read as zeros.
        """
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        with self._cond:
            start = end - n
            pad = max(0, -start)
            start = max(0, start)
            if end > self._total_written or start < self._total_written - self.capacity:
                return None
            out = np.empty(end - start, dtype=np.float32)
            i0 = start % self.capacity
            first = min(out.size, self.capacity - i0)
            out[:first] = self._data[i0:i0 + first]
            if first < out.size:
                out[first:] = self._data[:out.size - first]
        if pad:
            out = np.concatenate([np.zeros(pad, dtype=np.float32), out])
        return out

    def read_latest(self, n: int) -> tuple[np.ndarray, int]:
        """Return up to the latest ``n`` samples and the absolute end position."""
        with self._cond:
            end = self._total_written
        n = min(n, self.capacity, end)
        data = self.read(end, n)
        if data is None:  # overwritten between the two locks; retry once at the new end
            with self._cond:
                end = self._total_written
            data = self.read(end, min(n, end))
        return (data if data is not None else np.zeros(0, dtype=np.float32)), end
