#!/usr/bin/env python3
"""Diagnostic tool to check that the audio pipeline keeps up with real time.

Feeds a local audio file at real-time pace and prints, once per second,
whether each thread is alive, how many hops the real-time path analyzed or
skipped, and how often each background job ran, was skipped (latest-wins)
and how long it took.

Usage:
    python -m src.diagnostics.worker_debug
"""

import logging
import threading
import time
from pathlib import Path

import soundfile as sf

from src.diagnostics import utf8_stdout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(threadName)-15s] %(levelname)-8s: %(message)s'
)
logger = logging.getLogger(__name__)


def list_active_threads():
    """Show all currently active threads."""
    active = threading.enumerate()
    print(f"\n{'='*70}")
    print(f"ACTIVE THREADS ({len(active)})")
    print(f"{'='*70}")
    for thread in active:
        daemon_str = "(daemon)" if thread.daemon else "(user)"
        status_str = "✓ alive" if thread.is_alive() else "✗ dead"
        print(f"  {thread.name:30s} {daemon_str:10s} {status_str}")
    print(f"{'='*70}\n")


def test_pipeline_with_logging(max_duration_s: float = 20.0):
    """Run the pipeline on a file at real-time pace and report its health."""
    from src.engine import AudioPipeline
    from src.sources import AudioChunk
    from tests import settings

    audio_file = Path(settings.USB_SIMULATION_FILE)
    if not audio_file.exists():
        logger.error(f"Audio file not found: {audio_file}")
        logger.info("Set USB_SIMULATION_FILE in tests/settings.py")
        return

    info = sf.info(str(audio_file))
    block = 512

    def paced_source():
        """Yield the file in small blocks at real-time pace, like a live device."""
        with sf.SoundFile(audio_file) as f:
            max_samples = int(max_duration_s * f.samplerate)
            read = 0
            while read < max_samples:
                samples = f.read(block, dtype="float32", always_2d=True)
                if len(samples) == 0:
                    return
                read += len(samples)
                yield AudioChunk(samples=samples, sample_rate=f.samplerate)
                time.sleep(len(samples) / f.samplerate)

    print(f"\n{'='*70}")
    print("PIPELINE DIAGNOSTIC")
    print(f"{'='*70}")
    print(f"Audio file: {audio_file.name} ({info.samplerate} Hz)")
    print(f"Duration: {max_duration_s:.0f}s at real-time pace, {block}-sample blocks")
    print(f"{'='*70}\n")

    pipeline = AudioPipeline(audio_source=paced_source, sample_rate=info.samplerate)
    pipeline.start()

    print("\nAFTER pipeline.start():")
    list_active_threads()

    realtime = pipeline.realtime_worker
    print(f"{'Time':<6} {'Capture':<9} {'Realtime':<9} {'Hops':>7} {'Skipped':>8}   Jobs (runs/skipped/last ms)")
    print("-" * 90)
    for i in range(int(max_duration_s) + 5):
        time.sleep(1.0)
        jobs = "  ".join(
            f"{job.name}:{job.runs}/{job.skipped}/{job.last_compute_s * 1000:.0f}" for job in pipeline.jobs
        )
        print(
            f"{i:>3}s   {'✓' if pipeline.capture_worker.is_alive() else '✗':<9} "
            f"{'✓' if realtime.is_alive() else '✗':<9} {realtime.hops_processed:>7} "
            f"{realtime.hops_skipped:>8}   {jobs}"
        )
        if not pipeline.is_running():
            print(f"[Pipeline finished at {i}s]")
            break

    pipeline.stop()
    pipeline.wait(timeout=5.0)

    _, _, slow = pipeline.feature_cache.get_all()
    if slow is not None:
        print(f"\nLast slow features: BPM={slow.estimated_bpm} (stability {slow.beat_stability:.2f}), "
              f"key={slow.detected_key} ({slow.key_confidence:.2f})")

    print("\nINTERPRETATION:")
    print("  Skipped hops > 0: the real-time path could not keep up (CPU starved)")
    print("  Job skipped count growing fast: that job is slower than its interval")


if __name__ == "__main__":
    utf8_stdout()
    try:
        test_pipeline_with_logging()
    except Exception as e:
        logger.exception("Diagnostic failed")
        print(f"\nError: {e}")
