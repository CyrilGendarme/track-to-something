"""Base worker classes for the audio pipeline."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod

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
