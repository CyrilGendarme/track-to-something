# Feature Extraction Guide

Complete reference of audio features extracted by the engine.

## Feature Hierarchy

```
Audio Input
    ↓
[STFT Computation]
    ↓
├── Amplitude Analysis
│   ├── RMS (Root Mean Square)
│   ├── Peak (Maximum amplitude)
│   └── Overall (Normalized combination)
│
├── Spectral Analysis
│   ├── Frequency Bins (0-22050 Hz)
│   ├── Power Spectrum
│   └── Magnitude Spectrum
│
└── Feature Extraction
    ├── Frequency Band Energy
    │   ├── Bass (20-250 Hz)
    │   ├── Mid (250-4k Hz)
    │   └── High (4k-20k Hz)
    │
    ├── Spectral Features
    │   ├── Centroid (brightness)
    │   ├── Dominant Frequency
    │   ├── Spectral Density
    │   └── Spectral Shape
    │
    └── Temporal Features
        ├── Onset (attack detection)
        ├── Beat Confidence
        ├── Tempo (BPM)
        └── Envelopes (per-band over time)
```

## Amplitude Features

### Overall Amplitude
**Range**: 0.0 - 1.0 (normalized)

```python
overall_amplitude = max(abs(samples))
```

**Interpretation**:
- 0.0 = silence
- 0.3-0.5 = quiet to moderate
- 0.7-0.9 = loud
- > 0.9 = very loud/clipping risk

### RMS (Root Mean Square)
**Range**: 0.0 - 1.0 (normalized)

```python
rms = sqrt(mean(samples^2))
```

**Interpretation**:
- Perceptual loudness (better than peak)
- Used for energy-based features
- More stable than peak

### Peak
**Range**: 0.0 - 1.0 (normalized)

```python
peak = max(abs(samples))
```

**Interpretation**:
- Headroom before clipping
- Useful for dynamics compression
- Can spike on transients

## Spectral Features

### Frequency Bands

Three primary frequency bands cover human hearing (20Hz - 20kHz):

#### Bass Band (20-250 Hz)
```python
bass_energy = mean(magnitude[20Hz:250Hz]) → normalized 0-1
```

**Content**:
- Kick drums, bass guitar, sub-bass
- Low-frequency ambience

**Use**: Object scaling, screen shake, rumble effects

#### Mid Band (250-4000 Hz)
```python
mid_energy = mean(magnitude[250Hz:4000Hz]) → normalized 0-1
```

**Content**:
- Snare, claps, vocals, melody instruments
- Main content range

**Use**: Transient effects, brightness tracking

#### High Band (4000-20000 Hz)
```python
high_energy = mean(magnitude[4000Hz:20000Hz]) → normalized 0-1
```

**Content**:
- Hi-hats, cymbals, shakers, presence
- Detail and brightness

**Use**: Whiteness/saturation, sparkle effects

### Spectral Centroid
**Range**: 0 Hz - 22050 Hz

```python
centroid_hz = sum(freq * magnitude) / sum(magnitude)
```

**Interpretation**:
- Brightness/brightness of audio
- Low centroid = dark (bass-heavy)
- High centroid = bright (treble-heavy)

**Normalization** (0-1):
```python
brightness = (centroid_hz - 1000) / 10000  # Adjust range for your audio
```

**Use**: Color hue mapping, spectral filtering

### Spectral Density

Proportion of energy in each band:

```python
total_energy = bass_energy + mid_energy + high_energy

spectral_density_bass = bass_energy / total_energy
spectral_density_mid = mid_energy / total_energy
spectral_density_high = high_energy / total_energy

# All sum to 1.0
```

**Interpretation**:
- Describes tonal character
- Bass-heavy: [0.7, 0.2, 0.1]
- Balanced: [0.3, 0.4, 0.3]
- Bright: [0.1, 0.2, 0.7]

**Use**: Color palette selection, EQ visualization

### Dominant Frequency
**Range**: 0 Hz - 22050 Hz

```python
dominant_freq = frequency_of_max_magnitude
```

**Interpretation**:
- Most prominent frequency
- Usually fundamental or formant

**Use**: Tone detection, pitch estimation

## Temporal Features

### Onset Detection

**Definition**: Rapid rise in energy (attack/transient)

```python
onset_detected = (energy_current > energy_previous * threshold)
onset_strength = (energy_current - energy_previous) / threshold
```

**Range**: 0.0 - 1.0 (strength)

**Interpretation**:
- 0.0 = smooth
- 0.3 = subtle attack
- 0.6 = moderate onset
- > 0.9 = sharp transient (kick/snare)

**Types**:
- **Percussion onset**: Sharp, short duration
- **Vocal onset**: Moderate, structured
- **Instrumental onset**: Varies by instrument
- **Ambient onset**: Subtle, sustained

**Use**: Triggering events, particle effects, percussion detection

### Beat Confidence
**Range**: 0.0 - 1.0

```python
beat_confidence = stability_of_beat_interval_relative_to_tempo_model
```

**Interpretation**:
- 0.0 = Very uncertain beat
- 0.5 = Moderate confidence
- 0.9+ = Very stable beat

**Factors**:
- Tempo consistency
- Spectral content
- Energy peaks alignment

**Use**: Beat-synced effects, rhythm game scoring

### Tempo (BPM)
**Range**: 50 - 200 BPM (typical), 30 - 300 (extreme)

```python
bpm = 60 / mean_beat_interval_seconds
```

**Estimation**:
- From beat peak intervals
- Energy envelope periodicity
- Spectral peak spacing

**Use**: Animation speed, effect timing

### Spectral Envelopes

Per-band energy over time (10 frames):

```python
band_bass_envelope = [energy_bass_frame0, energy_bass_frame1, ..., energy_bass_frame9]
```

**Shape**:
- Tuple of 10 float values (0-1)
- Shows energy evolution
- Useful for visualization

**Example**:
```
Bass envelope: (0.2, 0.3, 0.5, 0.8, 0.9, 0.7, 0.4, 0.2, 0.1, 0.05)
↓ ↓ ↓ PEAK ↓ ↓ ↓ ↓ ↓
```

**Use**: Waveform visualization, attack/decay visualization

## Derived Features

### Overall Energy
```python
overall_energy = (bass_energy + mid_energy + high_energy) / 3
```

### Energy Trend
**Range**: -1.0 to 1.0

```python
trend = (current_energy - average_energy) / average_energy
```

**Interpretation**:
- -1.0 = Energy dropping significantly
- 0.0 = Energy stable
- +1.0 = Energy building significantly

**Use**: Scene transitions, animation speed

### Dynamics
**Range**: 0.0 - 1.0

```python
dynamics = peak / rms
```

**Interpretation**:
- Ratio of dynamic range
- 1.0 = No dynamics (constant energy)
- 2.0+ = High dynamics (varying energy)

**Use**: Compressor settings, effect sharpness

### Energy Variance
**Range**: 0.0 - 1.0

```python
variance = std_dev(energy_over_window)
```

**Interpretation**:
- 0.0 = Constant energy (ambient)
- 0.3-0.5 = Moderate variation
- > 0.7 = Highly dynamic (drums)

**Use**: Complexity detection, scene characterization

## Feature Combinations

Useful combinations for specific effects:

### Attack Detection
```python
is_attack = onset_detected and onset_strength > 0.6
```

### Kick Drum Indicator
```python
is_kick = (bass_energy > 0.7) and onset_detected
kick_strength = bass_energy * onset_strength
```

### Snare/Hi-Hat Indicator
```python
is_snare = (high_energy > 0.6) and onset_detected and bass_energy < 0.3
snare_strength = high_energy * onset_strength
```

### Brightness Indicator
```python
brightness = (high_energy + spectral_centroid_hz / 22050) / 2
```

### Loudness Indicator
```python
# Perceptual loudness using A-weighting concept
loudness = overall_amplitude * (1.0 + high_energy * 0.3)
```

## Normalization

All features are normalized to 0-1 range:

```python
# Linear normalization
normalized = (value - min_value) / (max_value - min_value)

# Clipping
normalized = max(0, min(1, normalized))

# Log-scale (for values with large dynamic range)
normalized = log(value + epsilon) / log(max_value + epsilon)

# Perceptual weighting (for loudness)
normalized = sqrt(value)  # Perceptual relationship
```

## Time Scales

| Feature | Time Scale | Latency | Use Case |
|---------|-----------|---------|----------|
| Peak | Instantaneous | 0ms | Immediate response |
| RMS | ~20ms window | 10-20ms | Energy tracking |
| Onset | ~100ms window | 50-100ms | Attack detection |
| Beat | ~500ms window | 200-500ms | Tempo tracking |
| Spectral | Per-chunk | 10-50ms | Color/brightness |
| Centroid | Per-chunk | 10-50ms | Spectral tracking |

## Resolution

### Frequency Resolution
```
resolution_hz = sample_rate / n_fft
= 44100 / 2048
= 21.5 Hz per bin
```

At 44.1kHz, ~2Hz resolution (good for bass/mid, less for super-low bass)

### Time Resolution
```
time_per_frame = hop_length / sample_rate
= 512 / 44100
= 11.6 ms per chunk
```

At 21fps, ~50ms for multiple chunks to accumulate

### Trade-offs
- Larger n_fft = Better frequency resolution, worse time resolution
- Smaller n_fft = Better time resolution, worse frequency resolution
- Current setting (2048/512) = Good middle ground

## Quality Indicators

### Signal-to-Noise Ratio
Check if audio is too quiet:
```python
if rms < 0.05:
    # Audio too quiet, increase source volume
```

### Clipping Detection
```python
if peak > 0.99:
    # Audio clipping, reduce input gain
```

### Spectral Flatness
```python
flatness = geometric_mean(magnitude) / arithmetic_mean(magnitude)
# Flatness=1.0: White noise
# Flatness<0.1: Tonal content
```

## Extraction Pipeline

```
1. Read 2048 audio samples
2. Apply Hann window
3. Compute FFT (2048 points)
4. Calculate magnitude spectrum
5. Compute RMS and peak
6. Sum energy per frequency band
7. Calculate spectral centroid
8. Detect onsets
9. Estimate beat confidence
10. Calculate BPM
11. Record envelope
12. Return AudioFeaturesMessage
```

Time: ~10-20ms on modern CPU

## External References

- **STFT**: Short-Time Fourier Transform (Spectrogram)
- **Centroid**: Mass-weighted center frequency
- **Onset Detection**: Spectral flux or energy jump
- **Tempo Estimation**: Inter-beat-interval statistics
- **A-Weighting**: Perceptual frequency response curve

See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) for implementation details and [06_TIERED_ANALYSIS.md](06_TIERED_ANALYSIS.md) for how features are organized across tiers.
