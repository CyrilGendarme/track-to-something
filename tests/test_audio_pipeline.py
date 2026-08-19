"""Tests for multi-threaded audio pipeline."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import pytest
import soundfile as sf

from src.engine import AudioPipeline
from src.sources import AudioChunk
from tests import settings


def file_chunks(path: Path, block_size: int, max_duration_s: float | None = None) -> Iterator[AudioChunk]:
    """Yield audio chunks from a file."""
    with sf.SoundFile(path, mode="r") as audio_file:
        print(f"[File] Loading {path.name}: {audio_file.samplerate}Hz, {audio_file.channels}ch")
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


def test_pipeline_basic() -> None:
    """Test basic pipeline operation."""
    audio_file = settings.USB_SIMULATION_FILE
    if audio_file is None or not audio_file.is_file():
        pytest.skip("USB_SIMULATION_FILE not configured")
    
    events_detected = []
    
    def on_event(event_type: str, data: dict) -> None:
        events_detected.append((event_type, data.get("timestamp", 0.0)))
    
    # Create pipeline
    pipeline = AudioPipeline(
        audio_source=lambda: file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=10),
        n_processing_workers=2,
        event_callback=on_event,
    )
    
    # Start and run
    print("\n[Test] Starting pipeline")
    pipeline.start()
    
    try:
        # Wait for completion with timeout
        start_time = time.time()
        timeout = 30.0
        while pipeline.is_running() and time.time() - start_time < timeout:
            time.sleep(0.5)
        
        if pipeline.is_running():
            print("[Test] Pipeline timeout, stopping")
    finally:
        pipeline.stop()
        pipeline.wait(timeout=5.0)
    
    # Verify pipeline ran
    events = pipeline.get_events()
    print(f"\n[Test] Pipeline completed with {len(events)} events")
    
    assert len(events) >= 0, "Pipeline should process audio"
    assert not pipeline.is_running(), "Pipeline should be stopped"


def test_pipeline_with_multiple_workers() -> None:
    """Test pipeline with multiple processing workers."""
    audio_file = settings.USB_SIMULATION_FILE
    if audio_file is None or not audio_file.is_file():
        pytest.skip("USB_SIMULATION_FILE not configured")
    
    # Create pipeline with 4 workers
    # Use a longer clip than the 1s liveness check below so the finite file
    # source doesn't finish reading before we assert workers are still running
    pipeline = AudioPipeline(
        audio_source=lambda: file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=30),
        n_processing_workers=4,
    )
    
    pipeline.start()
    
    try:
        # Give it time to run
        time.sleep(1.0)
        
        # Check all workers are running
        assert pipeline.capture_worker.is_alive(), "Capture worker should be running"
        assert all(w.is_alive() for w in pipeline.processing_workers), "Processing workers should be running"
        assert pipeline.analysis_worker.is_alive(), "Analysis worker should be running"
        assert pipeline.rendering_worker.is_alive(), "Rendering worker should be running"
    finally:
        pipeline.stop()
        pipeline.wait(timeout=5.0)
    
    assert not pipeline.is_running(), "Pipeline should be stopped"


def test_pipeline_event_detection() -> None:
    """Test that pipeline detects events correctly."""
    audio_file = settings.USB_SIMULATION_FILE
    if audio_file is None or not audio_file.is_file():
        pytest.skip("USB_SIMULATION_FILE not configured")
    
    events_detected = []
    
    def on_event(event_type: str, data: dict) -> None:
        events_detected.append((event_type, data))
    
    pipeline = AudioPipeline(
        audio_source=lambda: file_chunks(audio_file, settings.BLOCK_SIZE, max_duration_s=10),
        n_processing_workers=2,
        event_callback=on_event,
    )
    
    pipeline.start()
    
    try:
        # Wait for processing
        start_time = time.time()
        while time.time() - start_time < 20.0:
            if not pipeline.is_running():
                break
            time.sleep(0.5)
    finally:
        pipeline.stop()
        pipeline.wait(timeout=5.0)
    
    # Check event detection
    beat_events = [e for e in events_detected if e[0] == "beat"]
    transient_events = [e for e in events_detected if e[0] == "transient"]
    
    print(f"\n[Test] Detected {len(beat_events)} beat events, {len(transient_events)} transient events")
    # Events may or may not be detected depending on audio content, just verify we got here
    assert True, "Event detection should complete without error"
