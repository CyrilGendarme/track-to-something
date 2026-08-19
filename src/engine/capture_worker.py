"""Audio capture worker - reads from source and feeds to pipeline."""

from __future__ import annotations

import logging
import time
from queue import Queue
from typing import Any, Callable

import numpy as np

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
    ):
        """Initialize audio capture worker.
        
        Args:
            name: Worker thread name
            audio_source: Callable that returns an iterable of AudioChunk
            output_queue: Queue to send AudioChunkMessage to
            buffer: Circular buffer to store captured audio
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, daemon=daemon)
        self.audio_source = audio_source
        self.output_queue = output_queue
        self.buffer = buffer
        self.chunk_count = 0

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
