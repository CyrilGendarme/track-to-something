#!/usr/bin/env python3
"""Diagnostic tool to check if audio pipeline workers are running.

This helps debug whether the multi-threaded pipeline is actually processing
chunks in parallel or if there's a bottleneck preventing workers from running.

Usage:
    python -m src.diagnostics.worker_debug
"""

import threading
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
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


def test_pipeline_with_logging():
    """Test the pipeline with detailed thread logging."""
    from src.engine import AudioPipeline
    from tests import settings
    from tests.test_audio_sources_analysis import _file_chunks
    
    audio_file = Path(settings.USB_SIMULATION_FILE)
    if not audio_file.exists():
        logger.error(f"Audio file not found: {audio_file}")
        logger.info("Set USB_SIMULATION_FILE in tests/settings.py")
        return
    
    print(f"\n{'='*70}")
    print(f"PIPELINE WORKER DIAGNOSTIC TEST")
    print(f"{'='*70}")
    print(f"Audio file: {audio_file.name}")
    print(f"Block size: {settings.BLOCK_SIZE}")
    print(f"Processing workers: 4")
    print(f"Max duration: 10 seconds (limited for quick test)")
    print(f"{'='*70}\n")
    
    # Show initial threads
    print("\nBEFORE pipeline.start():")
    list_active_threads()
    
    # Create pipeline
    def audio_source_gen():
        yield from _file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=10)
    
    pipeline = AudioPipeline(
        audio_source=audio_source_gen,
        n_processing_workers=4,
        buffer_capacity_s=5.0,
        sample_rate=48000,
    )
    
    # Start pipeline
    logger.info("Starting pipeline...")
    pipeline.start()
    
    # Show threads after start
    print("\nAFTER pipeline.start() - workers should be running:")
    list_active_threads()
    
    # Monitor worker activity
    print("\nMONITORING WORKERS for 15 seconds:")
    print(f"{'Time':<10} {'Capture':<20} {'Processing':<20} {'Analysis':<20} {'Rendering':<20}")
    print("-" * 70)
    
    for i in range(15):
        time.sleep(1.0)
        active_threads = threading.enumerate()
        capture_active = any("Capture" in t.name and t.is_alive() for t in active_threads)
        processing_active = any("Processing" in t.name and t.is_alive() for t in active_threads)
        analysis_active = any("Analysis" in t.name and t.is_alive() for t in active_threads)
        rendering_active = any("Rendering" in t.name and t.is_alive() for t in active_threads)
        
        capture_mark = "✓" if capture_active else "✗"
        processing_mark = "✓" if processing_active else "✗"
        analysis_mark = "✓" if analysis_active else "✗"
        rendering_mark = "✓" if rendering_active else "✗"
        
        print(f"{i:>2}s      {capture_mark} Capture    {processing_mark} Processing (4x)  {analysis_mark} Analysis     {rendering_mark} Rendering")
        
        # Stop if pipeline finishes early
        if not pipeline.is_running():
            print(f"[Pipeline finished at {i}s]")
            break
    
    # Wait for completion
    logger.info("Waiting for pipeline to finish...")
    pipeline.wait()
    
    # Show threads after completion
    print("\nAFTER pipeline.wait():")
    list_active_threads()
    
    # Show performance stats
    from src.engine import get_performance_monitor
    perf = get_performance_monitor()
    
    if perf.stats:
        print(f"\n{'='*70}")
        print(f"PERFORMANCE METRICS")
        print(f"{'='*70}")
        perf.log_summary(limit=15)
    
    print(f"\n✓ Diagnostic test complete")
    print(f"\nINTERPRETATION:")
    print(f"  ✓ All workers showed ✓: Pipeline working correctly")
    print(f"  ✗ Some workers showed ✗: Check for deadlocks or queue issues")
    print(f"  ✗ Processing/Analysis marked ✗: Possible bottleneck in earlier stages")


if __name__ == "__main__":
    try:
        test_pipeline_with_logging()
    except Exception as e:
        logger.exception("Diagnostic test failed")
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("  1. Check that audio file exists")
        print("  2. Check that all worker threads were created")
        print("  3. Look for exceptions in worker threads")
        print("  4. Check for queue.Full exceptions (may indicate processing too slow)")
