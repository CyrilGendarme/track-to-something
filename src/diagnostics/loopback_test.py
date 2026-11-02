#!/usr/bin/env python3
"""Real-hardware test: play a known signal into a device, analyze it live.

Plays a synthetic track with a known tempo and key to an output device and
runs the full pipeline on an input device that receives it - typically a
virtual cable (VB-Audio "CABLE Input" -> "CABLE Output"), or a physical
loopback (line out -> line in). Nothing is recorded or saved; only analysis
statistics are printed.

It measures what synthetic tests can't: real device block delivery, driver
overflows, real-time backlog, worker-process start-up, and wall-clock
timing of onset/beat events against the moment each kick reached the
output.

Usage:
    python -m src.diagnostics.loopback_test --out "CABLE Input" --in "CABLE Output"
    python -m src.diagnostics.loopback_test --out 14 --in 17 --seconds 30 --bpm 124
    python -m src.diagnostics.loopback_test --out "CABLE Input" --in "CABLE Output" --lead 0.06

The last line of the report suggests a MOSHPRO_BEAT_LEAD_S value for the
measured path; it only covers what this loop includes (not e.g. a
projector's latency).
"""

from __future__ import annotations

import argparse
import logging
import threading
import time

import numpy as np

from src.config import AUDIO_BLOCK_SIZE
from src.diagnostics import utf8_stdout
from src.diagnostics.signals import kick_track
from src.engine import AudioPipeline, prewarm_job_processes
from src.sources import AudioInputSource

logger = logging.getLogger(__name__)

PREFERRED_HOST_API = "Windows WASAPI"
KICK_MATCH_WINDOW_S = 0.06


def _sd():
    # Imported lazily so job worker processes (which re-import this module
    # as __mp_main__) don't initialize PortAudio; see src.sources.live_audio.
    import sounddevice
    return sounddevice


def resolve_device(spec: str, kind: str) -> int:
    """Device index from an index or a name substring (WASAPI preferred)."""
    sd = _sd()
    if spec.isdigit():
        return int(spec)
    channels_key = "max_input_channels" if kind == "input" else "max_output_channels"
    matches = [
        (i, d) for i, d in enumerate(sd.query_devices())
        if spec.casefold() in d["name"].casefold() and d[channels_key] > 0
    ]
    if not matches:
        raise SystemExit(f"No {kind} device matching {spec!r}")
    for i, d in matches:
        if sd.query_hostapis(d["hostapi"])["name"] == PREFERRED_HOST_API:
            return i
    return matches[0][0]


class Player:
    """Plays a mono signal and records the wall-clock time it reaches the DAC."""

    def __init__(self, y: np.ndarray, sr: int, device: int):
        self.y = y.astype(np.float32)
        self.pos = 0
        self.start_wall: float | None = None  # perf_counter() when sample 0 hit the DAC
        self.done = threading.Event()
        self.stream = _sd().OutputStream(device=device, samplerate=sr, channels=2, dtype="float32",
                                      callback=self._callback)

    def _callback(self, outdata, frames, time_info, _status) -> None:
        if self.start_wall is None:
            self.start_wall = time.perf_counter() + (time_info.outputBufferDacTime - time_info.currentTime)
        chunk = self.y[self.pos:self.pos + frames]
        outdata[:len(chunk)] = chunk[:, None]
        outdata[len(chunk):] = 0
        self.pos += frames
        if self.pos >= len(self.y):
            self.done.set()


def _ms(values) -> str:
    v = np.asarray(values) * 1000
    if v.size == 0:
        return "n/a"
    return f"median {np.median(v):+6.1f} ms, p5 {np.percentile(v, 5):+6.1f}, p95 {np.percentile(v, 95):+6.1f} (n={v.size})"


def run(out_device: int, in_device: int, bpm: float, seconds: float, block: int, lead: float) -> None:
    sd = _sd()
    sr = int(sd.query_devices(in_device)["default_samplerate"])
    out_sr = int(sd.query_devices(out_device)["default_samplerate"])
    if out_sr != sr:
        raise SystemExit(f"Output ({out_sr} Hz) and input ({sr} Hz) default rates differ")
    print(f"Output: [{out_device}] {sd.query_devices(out_device)['name']}")
    print(f"Input:  [{in_device}] {sd.query_devices(in_device)['name']}")
    print(f"Signal: {bpm} BPM kicks over a C major chord, {seconds:.0f}s @ {sr} Hz, {block}-sample blocks\n")

    # Production setup: warm worker processes first, as the GUI does at launch
    prewarm_job_processes()

    events: list[tuple[str, float, float]] = []  # (kind, stream time, wall time)

    def on_event(kind: str, data: dict) -> None:
        events.append((kind, data["timestamp"], time.perf_counter()))

    source = AudioInputSource(device=in_device, sample_rate=sr, block_size=block)
    pipeline = AudioPipeline(audio_source=lambda: source, sample_rate=sr, event_callback=on_event,
                             beat_lead_s=lead)
    pipeline.start()
    time.sleep(0.5)  # let the input stream open before the first kick
    if not pipeline.capture_worker.is_alive():
        pipeline.wait()  # re-raises the device error

    y = kick_track(bpm, seconds, sr)
    player = Player(y, sr, out_device)
    first_result: dict[str, float] = {}
    ages: list[float] = []
    with player.stream:
        while not player.done.wait(0.05):
            fast, _, slow = pipeline.feature_cache.get_all()
            if fast is not None and fast.audio_age_s:
                ages.append(fast.audio_age_s)
            if slow is not None and player.start_wall is not None:
                elapsed = time.perf_counter() - player.start_wall
                if slow.estimated_bpm and "bpm" not in first_result:
                    first_result["bpm"] = elapsed
                if slow.detected_key and "key" not in first_result:
                    first_result["key"] = elapsed
        time.sleep(0.5)  # let the tail reach the input
    pipeline.stop()
    pipeline.wait(timeout=5.0)

    rt = pipeline.realtime_worker
    fast, _, slow = pipeline.feature_cache.get_all()
    period = 60.0 / bpm
    played = np.arange(0.0, seconds, period)  # kick times, relative to sample 0
    played_wall = player.start_wall + played

    # Align capture stream time with playback. The track starts with a kick
    # after silence, so the first detected kick anchors the alignment
    # (matching to the nearest beat alone is ambiguous by whole periods).
    kicks = np.array([e.timestamp_s for e in rt.recent_events(0.0) if e.kind == "kick"])
    if kicks.size == 0:
        raise SystemExit("No kicks detected - is the output routed to the input?")
    anchor = kicks[0] - played[0]
    offsets = np.array([k - anchor - played[int(np.argmin(np.abs(played - (k - anchor))))] for k in kicks])
    stream_offset = anchor + float(np.median(offsets))

    def wall_errors(kind: str, after_s: float) -> list[float]:
        errs = []
        for k, _, wall in events:
            if k != kind:
                continue
            i = int(np.argmin(np.abs(played_wall - wall)))
            if played[i] > after_s and abs(wall - played_wall[i]) < KICK_MATCH_WINDOW_S * 3:
                errs.append(wall - played_wall[i])
        return errs

    def grid_errors(kind: str, after_s: float) -> list[float]:
        errs = []
        for k, ts, _ in events:
            if k == kind and ts - stream_offset > after_s:
                rel = ts - stream_offset
                errs.append(rel - played[int(np.argmin(np.abs(played - rel)))])
        return errs

    print("── Device & real-time health ─────────────────────────────────────")
    print(f"Input overflows reported by the driver: {source.overflows}")
    print(f"Hops analyzed: {rt.hops_processed}, skipped: {rt.hops_skipped}, "
          f"max backlog behind capture: {rt.max_backlog_s * 1000:.1f} ms")
    for job in pipeline.jobs:
        print(f"  job {job.name:12s} runs {job.runs:3d}  skipped {job.skipped:3d}  last {job.last_compute_s * 1000:6.0f} ms")

    print("\n── Analysis vs. ground truth ──────────────────────────────────────")
    print(f"BPM: {slow.estimated_bpm and round(slow.estimated_bpm, 2)} (true {bpm}); "
          f"beat tracker tempo {fast.tempo_bpm and round(fast.tempo_bpm, 2)}, lock {fast.beat_confidence:.2f}")
    print(f"Key: {slow.detected_key} (true C), confidence {slow.key_confidence:.2f}")
    print(f"Time to first result after playback start: "
          + ", ".join(f"{k} {v:.1f}s" for k, v in first_result.items()))
    print(f"Kicks detected: {kicks.size} of {played.size} played")

    print("\n── Timing ────────────────────────────────────────────────────────")
    print(f"Kick timing precision (stream time):  {_ms(offsets - float(np.median(offsets)))}")
    lock_after = seconds / 3
    print(f"Beats vs. kicks (stream time):        {_ms(grid_errors('beat', lock_after))}")
    print(f"Audio age when analyzed (ADC -> hop): {_ms(ages)}")
    print("Wall clock, kick reached output -> event delivered to the app:")
    print(f"  onset events (reactive):            {_ms(wall_errors('onset', 1.0))}")
    beat_wall = wall_errors("beat", lock_after)
    print(f"  beat events (predicted, lead {lead * 1000:.0f} ms):  {_ms(beat_wall)}")
    print("\nNegative wall-clock values mean the event arrived before the kick reached the output.")
    print("Latency between the output and the input's ADC timestamps (e.g. a virtual cable's")
    print("internal buffer) is invisible to the engine; cover it with MOSHPRO_BEAT_LEAD_S.")
    if beat_wall:
        print(f"Suggested MOSHPRO_BEAT_LEAD_S for this path: {max(0.0, lead + float(np.median(beat_wall))):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="output device index or name substring")
    parser.add_argument("--in", dest="inp", required=True, help="input device index or name substring")
    parser.add_argument("--bpm", type=float, default=128.0)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--block", type=int, default=AUDIO_BLOCK_SIZE)
    parser.add_argument("--lead", type=float, default=0.0, help="extra beat lead in seconds (MOSHPRO_BEAT_LEAD_S)")
    args = parser.parse_args()
    utf8_stdout()
    logging.basicConfig(level=logging.WARNING)
    run(resolve_device(args.out, "output"), resolve_device(args.inp, "input"), args.bpm, args.seconds, args.block,
        args.lead)


if __name__ == "__main__":
    main()
