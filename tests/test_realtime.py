"""Unit tests for the ring buffer, real-time analyzer, beat tracker and scheduler."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from src.engine.buffer import RingBuffer
from src.engine.realtime import BeatTracker, RealtimeAnalyzer
from src.engine.scheduler import AnalysisJob, JobScheduler
from tests.synthetic import kick_track

SR = 44100


# ── RingBuffer ──────────────────────────────────────────────────────────────

def test_ring_buffer_reads_exact_spans_across_wraparound() -> None:
    buf = RingBuffer(capacity_samples=10, sample_rate=SR)
    buf.write(np.arange(7, dtype=np.float32))
    buf.write(np.arange(7, 14, dtype=np.float32))  # wraps
    assert buf.total_written == 14
    np.testing.assert_array_equal(buf.read(14, 5), np.arange(9, 14))
    np.testing.assert_array_equal(buf.read(12, 8), np.arange(4, 12))


def test_ring_buffer_detects_overwritten_and_future_spans() -> None:
    buf = RingBuffer(capacity_samples=10, sample_rate=SR)
    buf.write(np.arange(14, dtype=np.float32))
    assert buf.read(14, 11) is None  # sample 3 was overwritten
    assert buf.read(15, 2) is None   # not written yet


def test_ring_buffer_zero_pads_before_stream_start() -> None:
    buf = RingBuffer(capacity_samples=10, sample_rate=SR)
    buf.write(np.ones(3, dtype=np.float32))
    np.testing.assert_array_equal(buf.read(3, 5), [0, 0, 1, 1, 1])


def test_ring_buffer_wait_wakes_on_write_and_close() -> None:
    buf = RingBuffer(capacity_samples=100, sample_rate=SR)
    threading.Timer(0.05, lambda: buf.write(np.zeros(10, dtype=np.float32))).start()
    assert buf.wait_for(10, timeout=2.0) == 10
    threading.Timer(0.05, buf.close).start()
    assert buf.wait_for(50, timeout=2.0) == 10
    assert buf.closed


# ── RealtimeAnalyzer ────────────────────────────────────────────────────────

def _run_analyzer(y: np.ndarray):
    analyzer = RealtimeAnalyzer(SR, fft_size=1024, hop_size=256)
    padded = np.concatenate([np.zeros(1024, dtype=np.float32), y])
    results = []
    for end in range(1024 + 256, padded.size + 1, 256):
        results.append(analyzer.process(padded[end - 1024:end], (end - 1024) / SR))
    return results


def test_analyzer_detects_each_kick_once() -> None:
    bpm = 120.0
    results = _run_analyzer(kick_track(bpm, 6.0, SR))
    kicks = [r.fast.timestamp_s for r in results if r.kick]
    # Kicks at 0.5s intervals; the first ~0.5s is threshold warm-up
    assert 9 <= len(kicks) <= 12
    intervals = np.diff(kicks)
    assert np.allclose(intervals, 60.0 / bpm, atol=0.012)


def test_analyzer_is_silent_on_silence_and_levels_are_bounded() -> None:
    results = _run_analyzer(np.zeros(SR * 2, dtype=np.float32))
    assert not any(r.onset or r.kick for r in results)
    loud = _run_analyzer(kick_track(120.0, 3.0, SR))
    for r in loud:
        for level in (r.medium.bass_energy, r.medium.mid_energy, r.medium.high_energy):
            assert 0.0 <= level <= 1.0


# ── BeatTracker ─────────────────────────────────────────────────────────────

def _drive(tracker: BeatTracker, kicks: list[float], duration: float, prior: float | None, hop: float = 0.005):
    beats, states = [], []
    kick_iter = iter(sorted(kicks))
    next_kick = next(kick_iter, None)
    t = 0.0
    while t < duration:
        t += hop
        kick_time = None
        if next_kick is not None and t >= next_kick:
            kick_time, next_kick = next_kick, next(kick_iter, None)
        state = tracker.update(t, kick_time, prior)
        states.append(state)
        if state.beat:
            beats.append(state.beat_time_s)
    return beats, states


def _grid_errors(beats: list[float], first: float, period: float, after: float) -> list[float]:
    return [((b - first + period / 2) % period) - period / 2 for b in beats if b > after]


def test_beat_tracker_locks_to_prior_and_corrects_phase() -> None:
    period = 0.5
    kicks = [0.13 + i * period for i in range(20)]
    beats, states = _drive(BeatTracker(), kicks, 10.0, prior=120.0)
    assert max(abs(e) for e in _grid_errors(beats, 0.13, period, 5.0)) < 0.002
    assert states[-1].confidence > 0.8
    assert states[-1].tempo_bpm == pytest.approx(120.0)


def test_beat_tracker_corrects_a_slightly_wrong_tempo_prior() -> None:
    """Prior 127.5 BPM, kicks at 128: the learned offset removes the lag."""
    period = 60.0 / 128.0
    kicks = [0.1 + i * period for i in range(60)]
    beats, states = _drive(BeatTracker(), kicks, 28.0, prior=127.5)
    errors = _grid_errors(beats, 0.1, period, 20.0)
    assert max(abs(e) for e in errors) < 0.002
    assert states[-1].tempo_bpm == pytest.approx(128.0, abs=0.1)


def test_beat_tracker_flywheel_survives_short_breakdown_then_releases() -> None:
    kicks = [i * 0.5 for i in range(1, 9)]  # kicks until 4s, then silence
    beats, states = _drive(BeatTracker(), kicks, 16.0, prior=120.0)
    assert any(4.5 < b < 8.0 for b in beats)  # keeps beating through the gap
    assert not any(b > 13.0 for b in beats)   # releases after LOST_AFTER_S
    assert states[-1].confidence == 0.0


def test_beat_tracker_falls_back_to_kick_intervals_without_prior() -> None:
    kicks = [i * 0.4 for i in range(1, 20)]  # 150 BPM
    _, states = _drive(BeatTracker(), kicks, 8.0, prior=None)
    assert states[-1].tempo_bpm == pytest.approx(150.0, abs=1.0)


# ── JobScheduler ────────────────────────────────────────────────────────────

def _slow_job(window: np.ndarray, sr: int) -> int:
    time.sleep(0.3)
    return window.size


def test_scheduler_is_latest_wins_and_reports_window() -> None:
    buf = RingBuffer(SR * 2, SR)
    buf.write(np.ones(SR, dtype=np.float32))
    results = []
    job = AnalysisJob("slow", _slow_job, interval_s=0.05, window_s=0.5, on_result=results.append)
    scheduler = JobScheduler(buf, [job])
    scheduler.start()
    time.sleep(1.0)
    scheduler.stop()
    scheduler.join(timeout=2.0)

    assert 2 <= job.runs <= 4       # ~1s / 0.3s per run, never queued up
    assert job.skipped >= 10        # ticks during a run were dropped
    assert results[0].value == SR // 2
    assert results[0].window_end_s == pytest.approx(1.0)
    assert results[0].window_start_s == pytest.approx(0.5)


# ── Timing: capture clock, kick localization, beat lookahead ────────────────

def test_ring_buffer_clock_maps_stream_time_and_smooths_jitter() -> None:
    buf = RingBuffer(capacity_samples=SR, sample_rate=SR)
    assert buf.unix_time_of(1.0) is None  # no capture timestamps yet
    rng = np.random.default_rng(0)
    block = 512
    for i in range(200):
        jitter = rng.uniform(-0.003, 0.003)  # callback scheduling noise
        buf.write(np.zeros(block, dtype=np.float32), capture_time_s=1000.0 + i * block / SR + jitter)
    assert buf.unix_time_of(2.0) == pytest.approx(1002.0, abs=0.001)


def test_ring_buffer_clock_resyncs_after_a_discontinuity() -> None:
    buf = RingBuffer(capacity_samples=SR, sample_rate=SR)
    buf.write(np.zeros(512, dtype=np.float32), capture_time_s=1000.0)
    # The device stalled for 0.5s: the next block's capture time jumps
    buf.write(np.zeros(512, dtype=np.float32), capture_time_s=1000.0 + 512 / SR + 0.5)
    assert buf.unix_time_of(512 / SR) == pytest.approx(1000.0 + 512 / SR + 0.5)


def test_analyzer_localizes_kick_attack_within_the_hop() -> None:
    bpm = 120.0
    y = kick_track(bpm, 6.0, SR)
    results = _run_analyzer(y)
    kick_times = [r.kick_time_s for r in results if r.kick]
    true_times = np.arange(0.0, 6.0, 60.0 / bpm)
    errors = [k - true_times[np.argmin(np.abs(true_times - k))] for k in kick_times]
    # Hop-end stamps would be 2-9 ms late; attack localization is ~1 ms
    assert max(abs(e) for e in errors) < 0.002


def test_beat_tracker_emits_ahead_by_lookahead_with_exact_time() -> None:
    period = 0.5
    kicks = [0.1 + i * period for i in range(12)]
    tracker = BeatTracker(lookahead_s=0.08)
    emitted = []  # (update time, beat time)
    t, kick_iter = 0.0, iter(kicks)
    next_kick = next(kick_iter)
    while t < 6.0:
        t += 0.005
        kick_time = None
        if next_kick is not None and t >= next_kick:
            kick_time, next_kick = next_kick, next(kick_iter, None)
        state = tracker.update(t, kick_time, 120.0)
        if state.beat:
            emitted.append((t, state.beat_time_s))
    late = [(t, b) for t, b in emitted if b > 3.0]
    assert late
    for t, b in late:
        assert 0.075 <= b - t <= 0.085                  # emitted ~80 ms ahead
        assert abs(((b - 0.1 + 0.25) % 0.5) - 0.25) < 0.002  # exact time on the grid


def test_analyzer_custom_band_follows_its_range_and_can_change_live() -> None:
    t = np.arange(SR * 2) / SR
    tone = (0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)  # steady 1 kHz
    analyzer = RealtimeAnalyzer(SR, fft_size=1024, hop_size=256)

    def run(start: int, hops: int) -> list:
        return [analyzer.process(tone[end - 1024:end], end / SR).medium
                for end in range(start + 1024, start + 1024 + hops * 256, 256)]

    off = run(0, 20)
    assert all(m.custom_energy == 0.0 and m.custom_band_hz is None for m in off)

    analyzer.set_custom_band(800.0, 1200.0)
    inside = run(20 * 256, 100)[-1]
    assert inside.custom_band_hz == (800.0, 1200.0)
    assert inside.custom_energy > 0.9

    # Narrower than one FFT bin: falls back to the nearest bin, still tracks it
    analyzer.set_custom_band(1001.0, 1002.0)
    assert run(120 * 256, 100)[-1].custom_energy > 0.9

    # A band with no energy settles near zero, relative to its own (floor) peak
    analyzer.set_custom_band(5000.0, 8000.0)
    assert run(220 * 256, 100)[-1].custom_energy < 0.1

    analyzer.set_custom_band(None)
    assert run(320 * 256, 1)[-1].custom_band_hz is None
