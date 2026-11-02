"""Scheduler for background analysis jobs.

Each job declares how often it runs, how much audio it needs and where it
runs (thread or process). On each tick the scheduler copies the job's window
out of the ring buffer and submits ``fn(window, sample_rate)``.

Jobs are *latest-wins*: if the previous run of a job hasn't finished, the
tick is skipped instead of queued, so a slow job degrades to a lower update
rate instead of building a backlog.

Process jobs share one app-wide process pool that outlives individual
pipelines: spawning a worker and importing librosa takes seconds, so it is
paid once (ideally at app start, see :func:`shared_process_pool`) rather
than on every start/stop of the analysis.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from concurrent.futures import BrokenExecutor, Executor, Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from src.config import SCHEDULER_TICK_S
from src.engine.base import Worker
from src.engine.buffer import RingBuffer

logger = logging.getLogger(__name__)



@dataclass
class JobResult:
    """Result of one job run, with the audio span it covered."""

    job: str
    value: Any
    window_start_s: float
    window_end_s: float
    compute_s: float


@dataclass(frozen=True)
class ProcessPoolSpec:
    """A named, app-wide process pool (see :func:`shared_process_pool`).

    Jobs with different start-up costs should use different pools, so a
    worker busy importing a slow library never delays the other jobs.
    """

    name: str
    max_workers: int = 1
    initializer: Callable[[], None] | None = None  # runs once in each worker at spawn


@dataclass
class AnalysisJob:
    """A periodic analysis over the most recent ``window_s`` of audio.

    With ``process_pool`` set, ``fn`` runs in that pool's worker processes and
    must be a module-level function (it is pickled); otherwise it runs in the
    scheduler's thread pool. It receives ``(mono_window, sample_rate)``.
    """

    name: str
    fn: Callable[[np.ndarray, int], Any]
    interval_s: float
    window_s: float
    on_result: Callable[[JobResult], None]
    process_pool: ProcessPoolSpec | None = None
    min_window_s: float = 0.0  # don't run before this much audio exists

    # Runtime state
    _future: Future | None = field(default=None, repr=False)
    _published: threading.Event = field(default_factory=threading.Event, repr=False)
    _next_run: float = field(default=0.0, repr=False)
    runs: int = 0
    skipped: int = 0
    last_compute_s: float = 0.0


def _noop() -> None:
    """Placeholder task used to spawn worker processes early."""


_shared_pools: dict[str, ProcessPoolExecutor] = {}
_shared_pools_lock = threading.Lock()


def shared_process_pool(spec: ProcessPoolSpec) -> ProcessPoolExecutor:
    """Return the app-wide pool named ``spec.name``, creating it if needed.

    Calling this early (e.g. when the GUI opens) spawns the workers and runs
    the initializer in each, so the first job doesn't wait for it. The spec
    of the first call for a name wins.
    """
    with _shared_pools_lock:
        pool = _shared_pools.get(spec.name)
        if pool is None:
            pool = ProcessPoolExecutor(max_workers=spec.max_workers, initializer=spec.initializer)
            # Workers are spawned on demand: submit one task per worker so all
            # of them start (and warm up) now.
            for _ in range(spec.max_workers):
                pool.submit(_noop)
            _shared_pools[spec.name] = pool
        return pool


def _discard_shared_process_pool(spec: ProcessPoolSpec, pool: Executor) -> None:
    """Drop a broken pool so the next call to shared_process_pool recreates it."""
    with _shared_pools_lock:
        if _shared_pools.get(spec.name) is pool:
            del _shared_pools[spec.name]
    pool.shutdown(wait=False, cancel_futures=True)


@atexit.register
def shutdown_shared_process_pools() -> None:
    """Stop all shared worker processes (runs automatically at exit)."""
    with _shared_pools_lock:
        pools = list(_shared_pools.values())
        _shared_pools.clear()
    for pool in pools:
        pool.shutdown(wait=False, cancel_futures=True)


class JobScheduler(Worker):
    """Runs :class:`AnalysisJob` s at their own cadence on the ring buffer."""

    def __init__(
        self,
        buffer: RingBuffer,
        jobs: list[AnalysisJob],
        thread_workers: int = 2,
        daemon: bool = True,
    ):
        """Initialize the scheduler.

        Args:
            buffer: Ring buffer the job windows are read from
            jobs: Jobs to run
            thread_workers: Size of the thread pool for in-process jobs
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name="JobScheduler", daemon=daemon)
        self.buffer = buffer
        self.jobs = jobs
        self._thread_pool = ThreadPoolExecutor(max_workers=thread_workers, thread_name_prefix="job")
        for job in jobs:
            if job.process_pool is not None:
                shared_process_pool(job.process_pool)  # start warming up now

    def _executor_for(self, job: AnalysisJob) -> Executor:
        if job.process_pool is not None:
            return shared_process_pool(job.process_pool)
        return self._thread_pool

    def _work(self) -> None:
        sr = self.buffer.sample_rate
        while not self.is_stopped():
            now = time.monotonic()
            for job in self.jobs:
                if now < job._next_run:
                    continue
                job._next_run = now + job.interval_s
                if job._future is not None and not job._future.done():
                    job.skipped += 1
                    continue
                window, end = self.buffer.read_latest(int(job.window_s * sr))
                if window.size < job.min_window_s * sr or not np.any(window):
                    continue
                self._submit(job, window, end)
            self._stop_event.wait(SCHEDULER_TICK_S)

    def _submit(self, job: AnalysisJob, window: np.ndarray, end: int) -> None:
        sr = self.buffer.sample_rate
        started = time.perf_counter()
        executor = self._executor_for(job)
        try:
            future = executor.submit(job.fn, window, sr)
        except BrokenExecutor:
            # A worker process died; replace the pool and retry on the next tick
            logger.error("[JobScheduler] process pool %s broken, recreating it", job.process_pool.name)
            _discard_shared_process_pool(job.process_pool, executor)
            return
        except RuntimeError:  # executor shut down while stopping
            return
        job._future = future
        job._published.clear()
        job.runs += 1

        def done(f: Future) -> None:
            try:
                job.last_compute_s = time.perf_counter() - started
                if f.cancelled():
                    return
                exc = f.exception()
                if exc is not None:
                    logger.error("[JobScheduler] job %s failed: %s", job.name, exc, exc_info=exc)
                    return
                result = JobResult(job.name, f.result(), (end - window.size) / sr, end / sr, job.last_compute_s)
                try:
                    job.on_result(result)
                except Exception:  # noqa: BLE001 - a consumer bug must not kill the scheduler
                    logger.exception("[JobScheduler] on_result for %s failed", job.name)
            finally:
                job._published.set()

        future.add_done_callback(done)

    def stop(self) -> None:
        """Stop scheduling and abandon jobs that are still running."""
        super().stop()
        self._shutdown_pools()

    def finish(self, timeout: float | None = None, final_pass: bool = True) -> None:
        """Stop scheduling, but let running jobs complete and publish first.

        Used when a finite source (e.g. a file) has been fully analyzed. With
        ``final_pass``, every job then runs once more on the final window: a
        file is read much faster than the jobs' wall-clock intervals, so
        otherwise some jobs might never have seen a full window.
        """
        super().stop()
        if self.is_alive():
            self.join(timeout=timeout)
        deadline = None if timeout is None else time.monotonic() + timeout
        self._wait_published(deadline)  # in-flight runs publish before the final pass
        if final_pass:
            sr = self.buffer.sample_rate
            for job in self.jobs:
                window, end = self.buffer.read_latest(int(job.window_s * sr))
                if window.size >= job.min_window_s * sr and np.any(window):
                    self._submit(job, window, end)
            self._wait_published(deadline)
        self._shutdown_pools()

    def _wait_published(self, deadline: float | None) -> None:
        for job in self.jobs:
            if job._future is None:
                continue
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            job._published.wait(remaining)

    def _shutdown_pools(self) -> None:
        # The shared process pool outlives this scheduler; only drop our runs
        for job in self.jobs:
            if job._future is not None:
                job._future.cancel()
        self._thread_pool.shutdown(wait=False, cancel_futures=True)
