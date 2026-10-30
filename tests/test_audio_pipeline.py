"""End-to-end tests for the audio pipeline on synthetic audio."""

from __future__ import annotations

import numpy as np
import pytest

from src.engine import AudioPipeline
from tests.synthetic import chunked_source, kick_track

SR = 44100
BPM = 128.0


def _run(duration_s: float, speed: float, use_processes: bool):
    y = kick_track(BPM, duration_s, SR)
    events: list[tuple[str, dict]] = []
    pipeline = AudioPipeline(
        audio_source=chunked_source(y, SR, speed=speed),
        sample_rate=SR,
        event_callback=lambda kind, data: events.append((kind, data)),
        use_processes=use_processes,
    )
    pipeline.start()
    pipeline.wait(timeout=60.0)
    return pipeline, events


def test_pipeline_analyzes_every_hop_in_order() -> None:
    pipeline, events = _run(duration_s=6.0, speed=4.0, use_processes=False)
    realtime = pipeline.realtime_worker

    assert not pipeline.is_running()
    assert realtime.hops_skipped == 0
    assert realtime.hops_processed == int(6.0 * SR) // realtime.hop_size

    onset_times = [data["timestamp"] for kind, data in events if kind == "onset"]
    assert onset_times == sorted(onset_times)
    # Every kick produces an onset (6s at 128 BPM = 13 kicks, first one during warm-up)
    assert len(onset_times) >= 10

    fast, medium, slow = pipeline.feature_cache.get_all()
    assert fast is not None and medium is not None and slow is not None
    # Counters let samplers detect events they didn't see
    assert fast.onset_count == len(onset_times)
    assert fast.beat_count == sum(1 for kind, _ in events if kind == "beat")
    assert 0.0 <= medium.bass_energy <= 1.0
    assert slow.spectral_density_low > slow.spectral_density_high


def test_pipeline_tracks_tempo_beats_and_key() -> None:
    pipeline, events = _run(duration_s=12.0, speed=3.0, use_processes=False)
    fast, _, slow = pipeline.feature_cache.get_all()

    assert slow.estimated_bpm == pytest.approx(BPM, abs=2.0)
    assert slow.detected_key == "C"
    assert fast.tempo_bpm == pytest.approx(BPM, abs=2.0)
    assert fast.beat_confidence > 0.5

    # Once locked, emitted beats sit on the true beat grid (kick attack times
    # are localized within the hop, so this is well under one hop)
    period = 60.0 / BPM
    late_beats = [d["timestamp"] for kind, d in events if kind == "beat" and d["timestamp"] > 6.0]
    assert len(late_beats) >= 10
    errors = [((b + period / 2) % period) - period / 2 for b in late_beats]
    assert max(abs(e) for e in errors) < 0.006


def test_pipeline_jobs_run_in_worker_processes() -> None:
    pipeline, _ = _run(duration_s=14.0, speed=1.0, use_processes=True)
    jobs = {job.name: job for job in pipeline.jobs}
    assert jobs["bpm"].runs >= 1 and jobs["key"].runs >= 1
    _, _, slow = pipeline.feature_cache.get_all()
    assert slow.estimated_bpm == pytest.approx(BPM, abs=2.0)
    assert slow.detected_key == "C"


def test_pipeline_stop_ends_blocking_source() -> None:
    """stop() must unblock a source that is waiting for device data."""
    import threading

    from src.sources import AudioChunk

    class BlockingSource:
        def __init__(self):
            self.closed = threading.Event()

        def __iter__(self):
            yield AudioChunk(np.zeros((512, 2), dtype=np.float32), SR)
            self.closed.wait()  # like a device read with no data arriving

        def close(self):
            self.closed.set()

    source = BlockingSource()
    pipeline = AudioPipeline(audio_source=lambda: source, sample_rate=SR, use_processes=False)
    pipeline.start()
    pipeline.stop()
    pipeline.wait(timeout=5.0)
    assert source.closed.is_set()
    assert not pipeline.capture_worker.is_alive()
    assert not pipeline.realtime_worker.is_alive()


def test_pipeline_rejects_mismatched_sample_rate() -> None:
    y = kick_track(BPM, 1.0, 48000)
    pipeline = AudioPipeline(audio_source=chunked_source(y, 48000), sample_rate=SR, use_processes=False)
    pipeline.start()
    with pytest.raises(ValueError, match="sample rate"):
        pipeline.wait(timeout=5.0)
    pipeline.stop()
