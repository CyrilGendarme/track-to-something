#!/usr/bin/env python3
"""Demo: Slow tier audio analysis with tonality detection.

Shows the new comprehensive slow-tier analysis including:
- Overall amplitude, RMS, peak
- Bass/mid/high energy levels
- Spectral characteristics (centroid, density distribution)
- Musical key detection (tonality)
- Onset/beat detection
- Tempo tracking
- Energy trend for scene changes
- Frequency band envelopes
"""

import numpy as np
from src.analysis.tiers.slow import SlowAnalyzer

def generate_test_signal(sample_rate=22050, duration_s=1.0, frequency_hz=440.0):
    """Generate a test audio signal (sine wave at given frequency).
    
    Args:
        sample_rate: Audio sample rate
        duration_s: Duration in seconds
        frequency_hz: Frequency of sine wave
        
    Returns:
        Stereo audio array (n_samples, 2)
    """
    n_samples = int(sample_rate * duration_s)
    t = np.arange(n_samples) / sample_rate
    
    # Create sine wave with slight modulation
    wave = np.sin(2 * np.pi * frequency_hz * t)
    wave *= (1 + 0.3 * np.sin(2 * np.pi * 2 * t))  # Amplitude modulation
    
    # Make stereo
    stereo = np.column_stack([wave, wave])
    return stereo.astype(np.float32)


def demo_tonality_detection():
    """Demonstrate tonality detection on different musical signals."""
    print("=" * 80)
    print("SLOW TIER ANALYSIS - TONALITY DETECTION DEMO")
    print("=" * 80)
    
    sample_rate = 22050
    analyzer = SlowAnalyzer(sample_rate=sample_rate, window_size_ms=100.0)
    
    # Test 1: C major (440 Hz A, which is in C major scale)
    print("\n[1] C Major Scale")
    print("-" * 40)
    c_major_freqs = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]  # C D E F G A B C
    
    for freq in c_major_freqs:
        audio = generate_test_signal(sample_rate, duration_s=0.5, frequency_hz=freq)
        features = analyzer.analyze(audio, timestamp_s=0.0)
        print(f"  Freq: {freq:7.2f} Hz -> Key: {features.detected_key:4s} (conf: {features.key_confidence:.2f})")
    
    # Test 2: A minor
    print("\n[2] A Minor Scale")
    print("-" * 40)
    analyzer = SlowAnalyzer(sample_rate=sample_rate, window_size_ms=100.0)  # Reset
    a_minor_freqs = [220.00, 246.94, 261.63, 293.66, 329.63, 349.23, 392.00, 440.00]  # A B C D E F G A
    
    for freq in a_minor_freqs:
        audio = generate_test_signal(sample_rate, duration_s=0.5, frequency_hz=freq)
        features = analyzer.analyze(audio, timestamp_s=0.0)
        print(f"  Freq: {freq:7.2f} Hz -> Key: {features.detected_key:4s} (conf: {features.key_confidence:.2f})")
    
    # Test 3: Full analysis on a complex signal
    print("\n[3] Full Slow-Tier Analysis")
    print("-" * 40)
    analyzer = SlowAnalyzer(sample_rate=sample_rate, window_size_ms=100.0)
    
    # Create a more complex signal (multiple frequencies)
    audio = generate_test_signal(sample_rate, duration_s=0.5, frequency_hz=440.0)
    audio_with_bass = audio.copy()
    
    # Add bass component
    bass = np.sin(2 * np.pi * 55 * np.arange(len(audio)) / sample_rate)
    audio_with_bass[:, 0] = audio[:, 0] * 0.7 + bass * 0.3
    audio_with_bass[:, 1] = audio[:, 1] * 0.7 + bass * 0.3
    
    features = analyzer.analyze(audio_with_bass, timestamp_s=0.0)
    
    print(f"\n  AMPLITUDE METRICS:")
    print(f"    Overall Amplitude: {features.overall_amplitude:.3f} (0-1)")
    print(f"    RMS:              {features.rms:.3f} (0-1)")
    print(f"    Peak:             {features.peak:.3f} (0-1)")
    
    print(f"\n  FREQUENCY BAND ENERGY:")
    print(f"    Bass (20-250 Hz):     {features.bass_energy:.3f} (0-1)")
    print(f"    Mid (250-4000 Hz):    {features.mid_energy:.3f} (0-1)")
    print(f"    High (4000-20000 Hz): {features.high_energy:.3f} (0-1)")
    
    print(f"\n  SPECTRAL CHARACTERISTICS:")
    print(f"    Spectral Centroid:    {features.spectral_centroid_hz:.1f} Hz")
    print(f"    Bass Density:         {features.spectral_density_low:.3f} (proportion)")
    print(f"    Mid Density:          {features.spectral_density_mid:.3f} (proportion)")
    print(f"    High Density:         {features.spectral_density_high:.3f} (proportion)")
    
    print(f"\n  TONALITY (MUSICAL KEY):")
    print(f"    Detected Key:         {features.detected_key or 'Unknown'}")
    print(f"    Key Confidence:       {features.key_confidence:.3f} (0-1)")
    
    print(f"\n  TRANSIENT & BEAT DETECTION:")
    print(f"    Onset Detected:       {features.onset_detected}")
    print(f"    Beat Detected:        {features.beat_detected}")
    print(f"    Beat Confidence:      {features.beat_confidence:.3f} (0-1)")
    
    print(f"\n  TEMPO TRACKING:")
    print(f"    Estimated BPM:        {features.estimated_bpm or 'Not detected'}")
    print(f"    Beat Stability:       {features.beat_stability:.3f} (0-1)")
    
    print(f"\n  DYNAMICS & TREND:")
    print(f"    Average Energy:       {features.average_energy:.3f} (0-1)")
    print(f"    Energy Variance:      {features.energy_variance:.3f}")
    print(f"    Energy Trend:         {features.energy_trend:+.3f} (-1=decreasing, +1=increasing)")
    
    print(f"\n  FREQUENCY BAND ENVELOPES:")
    if features.band_bass_envelope:
        print(f"    Bass Envelope:        {[f'{x:.2f}' for x in features.band_bass_envelope[:5]]}... ({len(features.band_bass_envelope)} points)")
    if features.band_mid_envelope:
        print(f"    Mid Envelope:         {[f'{x:.2f}' for x in features.band_mid_envelope[:5]]}... ({len(features.band_mid_envelope)} points)")
    if features.band_high_envelope:
        print(f"    High Envelope:        {[f'{x:.2f}' for x in features.band_high_envelope[:5]]}... ({len(features.band_high_envelope)} points)")
    
    print("\n" + "=" * 80)
    print("SLOW-TIER ANALYSIS USAGE FOR VIDEO/LIGHTING CONTROL:")
    print("=" * 80)
    print("""
The slow tier provides aggregate metrics for:

1. SCENE CHANGES (via overall_energy + energy_trend):
   - Low energy + negative trend → fade to dark scene
   - High energy + positive trend → build to climax
   - Energy variance → stability for smooth transitions

2. COLOR PALETTE (via spectral_density_low/mid/high):
   - High bass density (spectral_density_low > 0.4) → warm colors (red/orange)
   - High mid density (spectral_density_mid > 0.4) → mid colors (green/yellow)
   - High high density (spectral_density_high > 0.4) → cool colors (blue/purple)

3. ANIMATION SPEED (via estimated_bpm + beat_stability):
   - estimated_bpm → animation tempo (120 BPM = 2 beats/sec)
   - beat_stability > 0.7 → smooth predictable motion
   - beat_stability < 0.3 → glitchy/chaotic effects

4. MUSICAL KEY (via detected_key + key_confidence):
   - detected_key → harmonic color grading (different keys → different palettes)
   - key_confidence > 0.6 → apply strong key-based coloring
   - key_confidence < 0.4 → use spectral density fallback

5. DYNAMICS (via amplitude/RMS + beat_detected):
   - Overall amplitude surge + onset_detected → flash/impact effect
   - RMS trend + beat_confidence → synchronized pulsing
    """)


if __name__ == "__main__":
    demo_tonality_detection()
