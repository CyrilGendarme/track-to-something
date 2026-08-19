"""Audio capture worker - reads from source and feeds to pipeline."""

from __future__ import annotations

import logging
import time
from queue import Queue
from typing import Any, Callable

import numpy as np
from scipy import signal as scipy_signal

from src.config import AUDIO_BIT_DEPTH, AUDIO_CHANNELS, AUDIO_APPLY_HPF
from src.engine.base import Worker
from src.engine.buffer import CircularAudioBuffer
from src.engine.messages import AudioChunkMessage
from src.engine.performance import get_performance_monitor

logger = logging.getLogger(__name__)


class AudioCaptureWorker(Worker):
    """Captures audio from a source and feeds to processing queue."""

    def __init__(
        self,
        name: str,
        audio_source: Callable[[], Any],
        output_queue: Queue,
        buffer: CircularAudioBuffer,
        daemon: bool = False,
        sample_rate: int = 22050,
    ):
        """Initialize audio capture worker.
        
        Args:
            name: Worker thread name
            audio_source: Callable that returns an iterable of AudioChunk
            output_queue: Queue to send AudioChunkMessage to
            buffer: Circular buffer to store captured audio
            daemon: If True, thread will not prevent program exit
            sample_rate: Sample rate for HPF design
        """
        super().__init__(name=name, daemon=daemon)
        self.audio_source = audio_source
        self.output_queue = output_queue
        self.buffer = buffer
        self.chunk_count = 0
        self.sample_rate = sample_rate
        
        # Initialize high-pass filter (20 Hz cutoff) if needed
        self._hpf_b = None
        self._hpf_a = None
        self._hpf_state = None
        
        if AUDIO_APPLY_HPF:
            # Design high-pass filter: 20 Hz cutoff at given sample rate
            nyquist = sample_rate / 2
            normalized_cutoff = 20.0 / nyquist
            # Ensure cutoff is in valid range (0, 1)
            normalized_cutoff = max(0.001, min(0.999, normalized_cutoff))
            
            self._hpf_b, self._hpf_a = scipy_signal.butter(
                N=2,  # Order 2 (fast, effective)
                Wn=normalized_cutoff,
                btype='high'
            )
            # Initialize filter state for scipy.signal.sosfilt_zi (for channels)
            self._hpf_state = None

    def _reduce_bit_depth(self, samples: np.ndarray) -> np.ndarray:
        """Reduce audio bit depth to configured depth.
        
        Args:
            samples: Audio samples in float32 [-1, 1]
            
        Returns:
            Audio samples with reduced bit depth (still float32, but quantized)
        """
        if AUDIO_BIT_DEPTH >= 16:
            return samples  # No reduction needed
        
        # Quantize to N-bit representation
        max_levels = (1 << AUDIO_BIT_DEPTH) - 1  # 2^N - 1
        quantized = np.round(samples * max_levels) / max_levels
        return np.clip(quantized, -1.0, 1.0)

    def _convert_to_mono(self, samples: np.ndarray) -> np.ndarray:
        """Convert stereo audio to mono if configured.
        
        Args:
            samples: Audio samples shape (N, 2) for stereo
            
        Returns:
            Audio samples shape (N, 1) for mono or original if not mono
        """
        if AUDIO_CHANNELS == 1 and samples.ndim == 2 and samples.shape[1] > 1:
            # Average stereo channels to mono
            mono = np.mean(samples, axis=1, keepdims=True)
            return mono
        
        return samples

    def _apply_hpf(self, samples: np.ndarray) -> np.ndarray:
        """Apply high-pass filter to remove rumble below 20 Hz.
        
        Args:
            samples: Audio samples shape (N,) or (N, C)
            
        Returns:
            Filtered audio samples
        """
        if not AUDIO_APPLY_HPF or self._hpf_b is None:
            return samples
        
        # Handle both mono and multi-channel
        if samples.ndim == 1:
            # Mono: apply filter directly
            filtered = scipy_signal.lfilter(
                self._hpf_b, self._hpf_a, samples
            )
            return filtered
        else:
            # Multi-channel: apply filter to each channel
            filtered = np.zeros_like(samples)
            for ch in range(samples.shape[1]):
                filtered[:, ch] = scipy_signal.lfilter(
                    self._hpf_b, self._hpf_a, samples[:, ch]
                )
            return filtered

    def _work(self) -> None:
        """Capture audio and feed to processing queue."""
        try:
            perf = get_performance_monitor()
            source = self.audio_source()
            for chunk in source:
                if self.is_stopped():
                    break
                
                chunk_start = time.perf_counter()
                
                # Convert to float32 stereo if needed
                samples = np.asarray(chunk.samples, dtype=np.float32)
                if samples.ndim == 1:
                    samples = np.column_stack([samples, samples])
                elif samples.ndim == 2 and samples.shape[1] == 1:
                    samples = np.column_stack([samples, samples])
                
                # Apply audio quality reduction (in order: HPF → bit depth → channels)
                with perf.timing_context("capture:audio_processing"):
                    # 1. Apply high-pass filter to remove rumble
                    if AUDIO_APPLY_HPF:
                        samples = self._apply_hpf(samples)
                    
                    # 2. Reduce bit depth for memory efficiency
                    if AUDIO_BIT_DEPTH < 16:
                        samples = self._reduce_bit_depth(samples)
                    
                    # 3. Convert to mono if configured
                    if AUDIO_CHANNELS == 1:
                        samples = self._convert_to_mono(samples)
                
                # Store in circular buffer
                with perf.timing_context("capture:buffer_write"):
                    self.buffer.write(samples)
                
                # Send to processing
                with perf.timing_context("capture:queue_put"):
                    msg = AudioChunkMessage(samples=samples, sample_rate=int(chunk.sample_rate))
                    self.output_queue.put(msg)
                
                self.chunk_count += 1
                
                # Log timing every 100 chunks
                if self.chunk_count % 100 == 0:
                    chunk_duration_ms = (time.perf_counter() - chunk_start) * 1000
                    logger.debug(f"[{self.name}] Chunk {self.chunk_count}: {chunk_duration_ms:.2f}ms")
        except Exception as e:
            logger.exception(f"[{self.name}] Audio source error")
            raise
