"""Example usage of the multi-threaded audio pipeline."""

from __future__ import annotations

import time
from pathlib import Path

import soundfile as sf

from src.engine import AudioPipeline
from src.sources import AudioChunk


def example_file_source(file_path: Path, block_size: int = 4096):
    """Yield audio chunks from a file."""
    with sf.SoundFile(file_path, mode="r") as audio_file:
        print(f"[Source] Loading {file_path.name}: {audio_file.samplerate}Hz, {audio_file.channels}ch")
        while True:
            samples = audio_file.read(block_size, dtype="float32", always_2d=True)
            if len(samples) == 0:
                break
            yield AudioChunk(samples=samples, sample_rate=audio_file.samplerate)


def on_event(event_type: str, data: dict) -> None:
    """Callback for pipeline events."""
    print(f"[Event] {event_type} at {data.get('timestamp', 0):.2f}s: {data}")


def main():
    """Run the example pipeline."""
    # Path to test audio file
    audio_file = Path("tests/audio/sample.mp3")  # Update this path
    
    if not audio_file.exists():
        print(f"Audio file not found: {audio_file}")
        print("Please update the path in this example")
        return
    
    # Create pipeline with 2 processing workers
    pipeline = AudioPipeline(
        audio_source=lambda: example_file_source(audio_file, block_size=4096),
        n_processing_workers=2,
        buffer_capacity_s=5.0,
        sample_rate=48000,
        event_callback=on_event,
    )
    
    print("\n=== Starting Audio Pipeline ===\n")
    pipeline.start()
    
    try:
        # Let pipeline run for a bit
        while pipeline.is_running():
            time.sleep(0.5)
            # Optionally check events periodically
            events = pipeline.get_events()
            if events:
                print(f"[Main] Total events detected: {len(events)}")
    except KeyboardInterrupt:
        print("\n[Main] Interrupted")
    finally:
        print("\n[Main] Stopping pipeline...")
        pipeline.stop()
        pipeline.wait(timeout=5.0)
        
        # Print summary
        events = pipeline.get_events()
        print(f"\n=== Pipeline Summary ===")
        print(f"Total events: {len(events)}")
        for timestamp, event_type in events[:10]:  # Print first 10
            print(f"  {timestamp:.2f}s: {event_type}")
        if len(events) > 10:
            print(f"  ... and {len(events) - 10} more")


if __name__ == "__main__":
    main()
