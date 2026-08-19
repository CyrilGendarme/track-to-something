"""Performance monitoring and timing instrumentation for bottleneck analysis."""

from __future__ import annotations

import logging
import time
import threading
from contextlib import contextmanager
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Generator

logger = logging.getLogger(__name__)


@dataclass
class TimingStats:
    """Statistics for a timed operation."""
    operation: str
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    
    @property
    def avg_ms(self) -> float:
        """Average time in milliseconds."""
        return self.total_ms / self.count if self.count > 0 else 0.0
    
    def __str__(self) -> str:
        """Format stats as human-readable string."""
        if self.count == 0:
            return f"{self.operation}: no samples"
        return (
            f"{self.operation}: "
            f"avg={self.avg_ms:.2f}ms, "
            f"min={self.min_ms:.2f}ms, "
            f"max={self.max_ms:.2f}ms, "
            f"n={self.count}"
        )


class PerformanceMonitor:
    """Thread-safe performance monitoring for latency analysis.
    
    Tracks timing of operations and logs periodic summaries to help identify
    bottlenecks in the audio pipeline.
    """
    
    _instance: PerformanceMonitor | None = None
    _lock = threading.Lock()
    
    def __new__(cls) -> PerformanceMonitor:
        """Singleton pattern for global performance monitor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize performance monitor."""
        if self._initialized:
            return
        
        self.stats: dict[str, TimingStats] = {}
        self.lock = threading.RLock()
        self.enabled = True
        self._initialized = True
    
    def record_time(self, operation: str, duration_ms: float) -> None:
        """Record timing for an operation.
        
        Args:
            operation: Name of operation (e.g., "capture_chunk", "process_features")
            duration_ms: Time taken in milliseconds
        """
        if not self.enabled:
            return
        
        with self.lock:
            if operation not in self.stats:
                self.stats[operation] = TimingStats(operation)
            
            stat = self.stats[operation]
            stat.count += 1
            stat.total_ms += duration_ms
            stat.min_ms = min(stat.min_ms, duration_ms)
            stat.max_ms = max(stat.max_ms, duration_ms)
            
            # Log if operation exceeds threshold (30ms = noticeable delay)
            if duration_ms > 30.0:
                logger.warning(f"[SLOW] {operation}: {duration_ms:.2f}ms")
    
    @contextmanager
    def timing_context(self, operation: str) -> Generator[None, None, None]:
        """Context manager for timing a code block.
        
        Usage:
            with perf_monitor.timing_context("operation_name"):
                do_work()
        """
        if not self.enabled:
            yield
            return
        
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.record_time(operation, duration_ms)
    
    def log_summary(self, limit: int = 10) -> None:
        """Log summary of all recorded operations.
        
        Args:
            limit: Only show top N slowest operations
        """
        if not self.stats:
            logger.info("[Performance] No operations recorded yet")
            return
        
        with self.lock:
            logger.info("=" * 70)
            logger.info("[PERFORMANCE SUMMARY]")
            logger.info("=" * 70)
            
            # Sort by average time (slowest first)
            sorted_stats = sorted(
                self.stats.values(),
                key=lambda s: s.avg_ms,
                reverse=True
            )
            
            # Show top slowest operations
            for i, stat in enumerate(sorted_stats[:limit], 1):
                logger.info(f"{i:2d}. {stat}")
            
            if len(sorted_stats) > limit:
                logger.info(f"... and {len(sorted_stats) - limit} more operations")
            
            logger.info("=" * 70)
    
    def log_operation(self, operation: str) -> None:
        """Log stats for a specific operation.
        
        Args:
            operation: Operation name to log
        """
        with self.lock:
            if operation in self.stats:
                logger.info(f"[Stats] {self.stats[operation]}")
            else:
                logger.info(f"[Stats] {operation}: no data")
    
    def reset(self) -> None:
        """Reset all statistics."""
        with self.lock:
            self.stats.clear()
            logger.info("[Performance] Statistics reset")
    
    def get_stats(self, operation: str) -> TimingStats | None:
        """Get stats for a specific operation.
        
        Args:
            operation: Operation name
            
        Returns:
            TimingStats or None if not recorded
        """
        with self.lock:
            return self.stats.get(operation)
    
    def disable(self) -> None:
        """Disable performance monitoring (reduces overhead)."""
        self.enabled = False
        logger.info("[Performance] Monitoring disabled")
    
    def enable(self) -> None:
        """Enable performance monitoring."""
        self.enabled = True
        logger.info("[Performance] Monitoring enabled")


def timer(operation: str):
    """Decorator for timing functions.
    
    Usage:
        @timer("my_operation")
        def expensive_function():
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = PerformanceMonitor()
            if not monitor.enabled:
                return func(*args, **kwargs)
            
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                monitor.record_time(operation, duration_ms)
        
        return wrapper
    return decorator


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return PerformanceMonitor()
