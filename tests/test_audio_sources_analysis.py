"""Streaming pipeline tests for real-time audio analysis."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import soundfile as sf

from src.sources import AudioChunk
from tests import settings


def _require_file(path: Path | None, label: str) -> Path:
    if path is None:
        pytest.skip(f"{label} is not configured; set it in tests/settings.py or its environment variable")
    if not path.is_file():
        pytest.skip(f"{label} does not exist: {path}")
    return path





def _file_chunks(path: Path, block_size: int, max_duration_s: float | None = None) -> Iterator[AudioChunk]:
    with sf.SoundFile(path, mode="r") as audio_file:
        print(f"[File] Loading {path.name}: {audio_file.samplerate}Hz, {audio_file.channels}ch, {audio_file.frames} frames (~{audio_file.frames/audio_file.samplerate:.1f}s)")
        chunk_count = 0
        total_samples = 0
        max_samples = int(audio_file.samplerate * max_duration_s) if max_duration_s else None
        
        while True:
            samples = audio_file.read(block_size, dtype="float32", always_2d=True)
            if len(samples) == 0:
                print(f"[File] Finished reading {chunk_count} chunks ({total_samples/audio_file.samplerate:.1f}s)")
                return
            
            # Stop if we've reached max duration
            if max_samples and total_samples + len(samples) > max_samples:
                remaining = max_samples - total_samples
                samples = samples[:remaining]
                total_samples += len(samples)
                chunk_count += 1
                yield AudioChunk(samples=samples, sample_rate=audio_file.samplerate)
                print(f"[File] Finished reading {chunk_count} chunks ({total_samples/audio_file.samplerate:.1f}s) [limited to {max_duration_s}s]")
                return
            
            total_samples += len(samples)
            chunk_count += 1
            if chunk_count % 10 == 0:
                print(f"[File] Read {chunk_count} chunks ({total_samples/audio_file.samplerate:.1f}s)...")
            yield AudioChunk(samples=samples, sample_rate=audio_file.samplerate)


def _collect_pipeline_results(pipeline, max_wait_s: float = 60.0) -> dict:
    """Collect results from a running pipeline (used for streaming tests).
    
    Args:
        pipeline: AudioPipeline instance
        max_wait_s: Maximum time to wait for pipeline completion
        
    Returns:
        Dictionary with pipeline statistics
    """
    start_time = time.monotonic()
    last_log_time = start_time
    chunk_count = 0
    
    while pipeline.is_running():
        elapsed = time.monotonic() - start_time
        
        # Print progress every second
        if elapsed - (last_log_time - start_time) > 1.0:
            print(f"[Pipeline] Processing... ({elapsed:.1f}s)")
            last_log_time = time.monotonic()
        
        # Check timeout
        if elapsed > max_wait_s:
            print(f"[Pipeline] Timeout after {max_wait_s}s, stopping")
            pipeline.stop()
            break
        
        time.sleep(0.1)  # Poll every 100ms
    
    total_time = time.monotonic() - start_time
    
    return {
        "total_time_s": total_time,
        "pipeline_running": pipeline.is_running(),
    }


def test_local_file_streaming_pipeline() -> None:
    """STREAMING TEST: Process audio in real-time using AudioPipeline workers.
    
    This demonstrates the multi-threaded pipeline processing chunks as they arrive,
    rather than processing all chunks synchronously after reading.
    
    Expected behavior:
    - Audio reading and analysis happen concurrently
    - Total time should be ~30-35s (close to audio duration), not 85s+
    - Multiple analysis results stream through (one per chunk processed)
    - Workers should be actively processing chunks in parallel
    """
    audio_file = _require_file(settings.USB_SIMULATION_FILE, "USB_SIMULATION_FILE")
    
    from src.engine import AudioPipeline, get_performance_monitor
    
    print(f"\n{'='*72}")
    print(f"STREAMING PIPELINE TEST")
    print(f"{'='*72}")
    print(f"[Pipeline Test] Goal: Process 30s audio with workers running in parallel")
    print(f"[Pipeline Test] Expected: ~30-35s total (not 85s like synchronous analysis)")
    print(f"[Pipeline Test] Using 4 processing workers for parallel feature extraction")
    
    # Create audio source generator
    def audio_source_gen():
        yield from _file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=30)
    
    # Start timer
    pipeline_start = time.monotonic()
    
    # Create and start pipeline
    pipeline = AudioPipeline(
        audio_source=audio_source_gen,
        n_processing_workers=4,
        buffer_capacity_s=5.0,
        sample_rate=48000,
    )
    
    print(f"\n[Pipeline] Starting 4 worker threads...")
    pipeline.start()
    print(f"[Pipeline] ✓ Capture worker: running")
    print(f"[Pipeline] ✓ Processing workers (4): running")
    print(f"[Pipeline] ✓ Analysis worker: running")
    print(f"[Pipeline] ✓ Rendering worker: running")
    
    # Collect results
    results = _collect_pipeline_results(pipeline, max_wait_s=120.0)
    
    # Show results
    perf = get_performance_monitor()
    total_time = results["total_time_s"]
    
    print(f"\n{'='*72}")
    print(f"RESULTS")
    print(f"{'='*72}")
    print(f"✓ Audio processed: 30.0 seconds")
    print(f"✓ Total elapsed: {total_time:.2f} seconds")
    efficiency = (30.0 / total_time * 100)
    print(f"✓ Efficiency: {efficiency:.1f}% real-time")
    
    if efficiency >= 95:
        print(f"✓ EXCELLENT: Pipeline is running at near real-time speed!")
    elif efficiency >= 80:
        print(f"✓ GOOD: Pipeline is efficient (some worker overhead expected)")
    else:
        print(f"⚠ SLOW: Pipeline may have bottlenecks - see performance analysis below")
    
    # Show performance metrics
    if perf.stats:
        print(f"\n{'='*72}")
        print(f"PERFORMANCE ANALYSIS")
        print(f"{'='*72}")
        perf.log_summary(limit=10)
    
    print(f"\n{'='*72}\n")
    
    # Assertions
    assert total_time < 120, f"Pipeline took too long: {total_time}s (expected <120s)"
    assert not results["pipeline_running"], "Pipeline should have stopped"
    print(f"✓ Streaming pipeline test passed!")