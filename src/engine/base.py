"""Base worker classes for the audio pipeline."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from queue import Queue
from typing import Any

logger = logging.getLogger(__name__)


class Worker(ABC, threading.Thread):
    """Base class for pipeline worker threads."""

    def __init__(self, name: str, daemon: bool = False):
        """Initialize worker thread.
        
        Args:
            name: Worker thread name (for debugging)
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, daemon=daemon)
        self._stop_event = threading.Event()
        self._error: Exception | None = None

    @abstractmethod
    def _work(self) -> None:
        """Main work loop. Must check self._stop_event regularly."""
        pass

    def run(self) -> None:
        """Thread main entry point. Handles exceptions and cleanup."""
        try:
            logger.debug(f"[{self.name}] Starting")
            self._work()
        except Exception as e:
            logger.exception(f"[{self.name}] Error")
            self._error = e
        finally:
            logger.debug(f"[{self.name}] Stopped")

    def stop(self) -> None:
        """Signal worker to stop gracefully."""
        logger.debug(f"[{self.name}] Stop requested")
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """Check if stop was requested."""
        return self._stop_event.is_set()

    def get_error(self) -> Exception | None:
        """Return any error that occurred in this worker."""
        return self._error

    def join(self, timeout: float | None = None) -> None:
        """Wait for worker to finish."""
        super().join(timeout=timeout)
        if self._error:
            raise self._error


class QueuedWorker(Worker):
    """Base worker that receives work items from a queue."""

    def __init__(self, name: str, input_queue: Queue, daemon: bool = False):
        """Initialize queued worker.
        
        Args:
            name: Worker thread name
            input_queue: Queue to receive work items from
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, daemon=daemon)
        self.input_queue = input_queue

    @abstractmethod
    def _process_item(self, item: Any) -> None:
        """Process a single item from the queue."""
        pass

    def _work(self) -> None:
        """Main work loop consuming queue items."""
        import queue as queue_module
        
        while not self.is_stopped():
            try:
                # Use timeout to check stop flag periodically
                item = self.input_queue.get(timeout=0.1)
                if item is None:  # Poison pill
                    break
                self._process_item(item)
            except queue_module.Empty:
                # Timeout - loop to check stop flag
                pass
