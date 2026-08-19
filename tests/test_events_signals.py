#!/usr/bin/env python
"""Quick validation of events/signals separation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.engine import (
    EventType, AudioEvent, ContinuousSignals, AudioFrame, merge_frames
)

print('Testing Events vs Continuous Signals Separation')
print('=' * 70)
print()

# Test 1: Create an event
print('1. AudioEvent creation:')
kick = AudioEvent(
    event_type=EventType.KICK,
    timestamp_s=10.5,
    strength=0.9,
    confidence=0.95,
    metadata={'detected_hz': 120},
)
print(f'   {kick}')
print(f'   Type: {kick.event_type.value}')
print(f'   Strength: {kick.strength:.2f}')
print()

# Test 2: Create continuous signals
print('2. ContinuousSignals creation:')
signals = ContinuousSignals(
    timestamp_s=10.5,
    immediate_energy=0.75,
    immediate_energy_derivative=0.1,
    bass_energy=0.85,
    mid_energy=0.60,
    high_energy=0.45,
    brightness=0.72,
    spectral_centroid_hz=2500,
    spectral_density_bass=0.5,
    spectral_density_mid=0.3,
    spectral_density_high=0.2,
    bass_energy_derivative=0.05,
    overall_energy_derivative=0.03,
    average_energy=0.68,
    energy_variance=0.15,
    energy_trend=0.3,
    estimated_bpm=128.0,
    beat_stability=0.92,
    beat_phase_0to1=0.45,
    predicted_beat_timestamp_s=11.0,
    prediction_confidence=0.95,
)
print(f'   Bass: {signals.bass_energy:.2f}, Brightness: {signals.brightness:.2f}')
print(f'   Trend: {signals.energy_trend:+.2f}, BPM: {signals.estimated_bpm}')
print()

# Test 3: Create audio frame
print('3. AudioFrame (combined):')
frame = AudioFrame(
    timestamp_s=10.5,
    signals=signals,
    events=[kick],
)
print(f'   {frame}')
print()

# Test 4: Event types
print('4. Event types available:')
types = [e.value for e in EventType]
print(f'   {len(types)} types: {", ".join(types[:5])}...')
print()

# Test 5: Multiple events
print('5. Multiple events:')
events = [
    AudioEvent(EventType.KICK, timestamp_s=10.5, strength=0.9),
    AudioEvent(EventType.ONSET, timestamp_s=10.52, strength=0.6),
    AudioEvent(EventType.ENERGY_SPIKE, timestamp_s=10.51, strength=0.8),
]
frame2 = AudioFrame(timestamp_s=10.5, signals=signals, events=events)
print(f'   Frame with {len(frame2.events)} events')
for e in frame2.events:
    print(f'   - {e.event_type.value}: strength={e.strength:.2f}')
print()

print('=' * 70)
print('[SUCCESS] Events/Signals separation validated!')
print()
print('Concepts:')
print('  - EVENTS: Discrete, point-in-time, trigger callbacks')
print('  - SIGNALS: Continuous, smooth, animate over time')
print('  - FRAME: Container for both at same timestamp')
