"""Thread-safe circular audio buffer for streaming audio."""

from __future__ import annotations

import threading
import time

import numpy as np

from src.config import DEFAULT_SAMPLE_RATE, BUFFER_CAPACITY_SECONDS
from src.engine.performance import get_performance_monitor


class CircularAudioBuffer:
    """Thread-safe circular buffer for audio chunks."""

    def __init__(self, capacity_s: float = BUFFER_CAPACITY_SECONDS, sample_rate: int = DEFAULT_SAMPLE_RATE):
        """Initialize circular buffer.
        
        Args:
            capacity_s: Buffer capacity in seconds
            sample_rate: Sample rate in Hz
        """
        self.capacity_samples = int(capacity_s * sample_rate)
        self.buffer = np.zeros((self.capacity_samples, 2), dtype=np.float32)
        self.write_pos = 0
        self.lock = threading.RLock()

    def write(self, samples: np.ndarray) -> int:
        """Write audio samples to buffer.
        
        Args:
            samples: Audio data (n_samples, n_channels) in float32
            
        Returns:
            Number of samples written
        """
        perf = get_performance_monitor()
        with perf.timing_context("buffer:write"):
            with self.lock:
                n = len(samples)
                remaining = self.capacity_samples - self.write_pos
                
                if n <= remaining:
                    # Simple case: fits without wrapping
                    self.buffer[self.write_pos:self.write_pos + n] = samples
                    self.write_pos += n
                else:
                    # Wrap around
                    self.buffer[self.write_pos:] = samples[:remaining]
                    self.buffer[:n - remaining] = samples[remaining:]
                    self.write_pos = n - remaining
                
                # Wrap write position
                self.write_pos %= self.capacity_samples
                return n

    def read_latest(self, duration_s: float, sample_rate: int) -> np.ndarray:
        """Read most recent samples.
        
        Args:
            duration_s: Duration to read in seconds
            sample_rate: Sample rate in Hz
            
        Returns:
            Audio samples (n_samples, 2) in float32
        """
        perf = get_performance_monitor()
        with perf.timing_context("buffer:read_latest"):
            n_samples = int(duration_s * sample_rate)
            n_samples = min(n_samples, self.capacity_samples)
            
            with self.lock:
                start = (self.write_pos - n_samples) % self.capacity_samples
                
                if start + n_samples <= self.capacity_samples:
                    # No wrap
                    return self.buffer[start:start + n_samples].copy()
                else:
                    # Wrapped read
                    part1 = self.buffer[start:]
                    part2 = self.buffer[:n_samples - len(part1)]
                    return np.vstack([part1, part2])
