# Analysis methods

How each output is computed, and its known limits.

## Real-time path (every 256-sample hop, 1024-sample Hann frame)

**Onsets.** Log-compressed magnitude spectrum (`log1p(1000·|X|)`),
half-wave rectified difference from the previous frame, averaged over bins
(spectral flux). An onset fires when:

- the flux exceeds an adaptive threshold: mean + 2·std of the last 1.5 s;
- the hop is louder than −60 dBFS;
- at least 80 ms have passed since the last onset.

**Kicks.** The same flux restricted to the bass band, with its own adaptive
threshold and a 200 ms refractory period. When a kick fires, its attack time
is located: the last three hops are low-passed at 250 Hz, their Hilbert
amplitude envelope is taken, and the attack is where the envelope first
climbs 25 % of the way from its pre-kick level to its peak. Measured error
is 0.3–2 ms (±1 ms), versus 2–9 ms for stamping the end of the hop.

**Band levels.** RMS magnitude per band, divided by a per-band peak that
decays with a 4 s time constant (with an absolute floor), then smoothed with
a 10 ms attack and 150 ms release.

## Dynamics job (thread, every 0.25 s, 2 s window)

A 2048-point STFT of the window gives:

- **Spectral densities**: the share of power per band.
- **Band envelopes**: band amplitude over time, resampled to 20 points and
  normalized to the window's loudest point.
- **Energy variance**: the coefficient of variation of the frame loudness.
- **Energy trend**: the linear slope of normalized frame loudness, per
  second, clipped to ±1.

## BPM jobs (processes, every 1 s, 8 s window)

Three independent detectors in two jobs:

| Method | Job / pool | Idea |
|---|---|---|
| `dynamic_kick_band` | `bpm` / signal | find the loudest low-frequency peak (30–180 Hz), band-pass around it, autocorrelate its onset envelope |
| `comb_filter_bank` | `bpm` / signal | normalized autocorrelation of the loudness envelope, scored on a 0.5 BPM grid (60–200) with parabolic refinement |
| `librosa_beat_track` | `bpm_librosa` / librosa | librosa's dynamic-programming beat tracker |

**Consensus** (`consensus_bpm`):

- Starts with the estimates whose confidence is ≥ 0.95, lowering the bar in
  0.05 steps until at least one qualifies.
- In that tier, the most confident estimate sets the tempo. Others are
  averaged in only if they agree within 4 %, after folding half or double
  tempo onto it.
- So 64 vs 128 never averages to 96.

The confidence scales of the three methods aren't strictly comparable, which
is why agreement matters more than the raw numbers.

## Key job (process, every 2 s, 8 s window)

- **Chromagram.** 8192-point frames (50 % overlap) give an averaged magnitude
  spectrum. Each bin in 60–2100 Hz is assigned to its nearest pitch class
  (`np.bincount`). Lower bins are too coarse to resolve semitones; higher
  bins are dominated by cymbals.
- **Templates.** Pearson correlation against the 24 rotated
  Krumhansl–Kessler profiles (12 major, 12 minor).
- **Confidence.** Best correlation × the margin over the second best
  (a 0.15 margin counts as fully confident). Relative major/minor keys
  typically score close together, which is reflected as lower confidence.
- **Smoothing.** A confidence-weighted vote over the last 4 estimates
  (about 8 s).

Validated on synthetic signals for all 24 keys and on I–IV–V–I / i–iv–V–i
cadences. Real mixes with heavy bass or atonal sections will be less
reliable; watch `key_confidence`.

## Capture conditioning

- Stereo is averaged to mono.
- A 2nd-order 20 Hz Butterworth high-pass removes DC and rumble. It's
  designed at the real sample rate, and its state carries across chunks.
- Optional quantization (`MOSHPRO_BIT_DEPTH` < 16; off by default).
