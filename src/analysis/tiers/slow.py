"""Slow audio analyzer - 100-500ms latency for overall dynamics, tempo, and tonality."""

from __future__ import annotations

import logging

import numpy as np
from scipy import signal

from src.config import (
    DEFAULT_SAMPLE_RATE,
    SLOW_WINDOW_MS,
    BEAT_ANALYSIS_WINDOW_MS,
    BEAT_HISTORY_SIZE,
    TONALITY_HISTORY_SIZE,
    FREQ_BAND_BASS_MAX,
    FREQ_BAND_BASS_MIN,
    FREQ_BAND_MID_MIN,
    FREQ_BAND_MID_MAX,
    FREQ_BAND_HIGH_MIN,
    FREQ_BAND_HIGH_MAX,
)
from .features import SlowFeatures

logger = logging.getLogger(__name__)


class SlowAnalyzer:
    """Analyzes audio in 100-500ms windows for overall shape, tempo, and tonality."""
    
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, window_size_ms: float = SLOW_WINDOW_MS, beat_analysis_window_ms: float = BEAT_ANALYSIS_WINDOW_MS, max_beat_history: int = BEAT_HISTORY_SIZE):
        """Initialize slow analyzer.
        
        Args:
            sample_rate: Audio sample rate in Hz (default from config)
            window_size_ms: Analysis window in milliseconds (default from config)
            beat_analysis_window_ms: Longer window for beat/tempo analysis (default from config)
            max_beat_history: Number of beats to track for tempo estimation (default from config)
        """
        self.sample_rate = sample_rate
        self.window_size_ms = window_size_ms
        self.window_size_samples = int(window_size_ms * sample_rate / 1000)
        self.hop_size_samples = self.window_size_samples // 2
        
        # Beat/Tempo analysis (SEPARATE from audio window analysis)
        # beat_analysis_window_ms is much longer (2s) to capture multiple beats
        self.beat_analysis_window_ms = beat_analysis_window_ms
        self.beat_analysis_window_samples = int(beat_analysis_window_ms * sample_rate / 1000)
        
        # Tempo tracking
        self.beat_timestamps = []
        self.max_beat_history = max_beat_history
        
        # Energy history for trend calculation
        self.energy_history = []
        self.max_history = 10
        
        # Aggregate metrics over window (for slow analysis)
        self.amplitude_history = []  # Track amplitudes
        self.rms_history = []        # Track RMS
        self.onset_history = []      # Track onsets
        self.beat_confidence_history = []  # Track beat confidence
        
        # Frequency band tracking for envelopes
        self.bass_envelope = []
        self.mid_envelope = []
        self.high_envelope = []
        self.max_envelope_length = 20
        
        # Spectral history for tonality detection
        self.spectral_history = []
        self.max_spectral_history = 50  # ~500ms at 10 chunks/sec
        
        # Tonality smoothing - keep last N detected keys for voting
        self.key_history = []  # List of (key_name, confidence) tuples
        self.max_key_history = TONALITY_HISTORY_SIZE  # Configurable smoothing window
        
        logger.info(f"[SlowAnalyzer] {window_size_ms:.1f}ms windows ({self.window_size_samples} samples), Beat analysis: {beat_analysis_window_ms:.0f}ms")
        # Musical key templates (major and minor key profiles)
        # Based on pitch class chroma distribution
        self.key_names = [
            "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
        ]
        self.major_key_names = [f"{k}" for k in self.key_names]
        self.minor_key_names = [f"{k}m" for k in self.key_names]
        
        # Krumhansl-Kessler key profiles (tuned for electronic music)
        self.major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        self.minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        
        logger.info(f"[SlowAnalyzer] {window_size_ms:.1f}ms windows ({self.window_size_samples} samples)")
    
    def record_beat(self, timestamp_s: float) -> bool:
        """Record a beat detection for tempo estimation.
        
        Rejects beats that are too close together (violate min BPM limit).
        Supports BPM range: 60-220 BPM
        
        Args:
            timestamp_s: Timestamp of beat
            
        Returns:
            True if beat was accepted and stored, False if rejected
        """
        # Reject beats too close together (< minimum interval for 220 BPM)
        # This filters out spurious double-detections from the same transient
        MIN_BEAT_INTERVAL = 60.0 / 220.0  # 220 BPM max ≈ 0.273s
        
        if len(self.beat_timestamps) > 0:
            last_beat_time = self.beat_timestamps[-1]
            interval_since_last = timestamp_s - last_beat_time
            
            if interval_since_last < MIN_BEAT_INTERVAL:
                logger.debug(
                    f"[SlowAnalyzer] Beat REJECTED: too soon after last beat "
                    f"({interval_since_last:.3f}s < {MIN_BEAT_INTERVAL:.3f}s, min 220 BPM)"
                )
                return False
        
        # Beat is valid, store it
        self.beat_timestamps.append(timestamp_s)
        if len(self.beat_timestamps) > self.max_beat_history:
            self.beat_timestamps.pop(0)
        
        logger.info(f"[SlowAnalyzer] Beat stored @ {timestamp_s:.3f}s. Total beats in history: {len(self.beat_timestamps)}/{self.max_beat_history}")
        return True
    
    def _compute_chromagram(self, audio_mono: np.ndarray) -> np.ndarray:
        """Compute chromagram (energy in each pitch class).
        
        Args:
            audio_mono: Mono audio signal
            
        Returns:
            Chromagram of shape (12,) representing energy in each semitone
        """
        # Compute FFT
        n_fft = min(8192, len(audio_mono) * 2)
        spectrum = np.abs(np.fft.rfft(audio_mono, n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)
        
        # Map frequencies to pitch classes (chromagram)
        # A4 = 440 Hz, C0 = 16.35 Hz
        chroma = np.zeros(12)
        
        if len(freqs) > 0:
            # Convert frequencies to cents relative to C0
            cents = 1200 * np.log2(np.maximum(freqs, 1) / 16.35)
            semitones = (cents / 100) % 12  # Wrap to 0-12
            
            # Distribute energy into 12 pitch classes using Gaussian weighting
            for i, (freq_energy, semitone) in enumerate(zip(spectrum, semitones)):
                # Find nearest semitone and add energy
                lower = int(np.floor(semitone)) % 12
                upper = (lower + 1) % 12
                ratio = semitone - np.floor(semitone)
                
                chroma[lower] += freq_energy * (1 - ratio)
                chroma[upper] += freq_energy * ratio
        
        # Normalize
        if np.sum(chroma) > 0:
            chroma = chroma / np.sum(chroma)
        
        return chroma
    
    def _detect_key(self, audio_mono: np.ndarray) -> tuple[str | None, float]:
        """Detect musical key using chromagram and key profiles.
        
        Args:
            audio_mono: Mono audio signal
            
        Returns:
            Tuple of (key_name, confidence) where key_name is like "C", "F#m", "Bm", etc.
            Returns (None, 0.0) if detection fails
        """
        try:
            chroma = self._compute_chromagram(audio_mono)
            
            # Normalize chroma
            if np.sum(chroma) > 0:
                chroma = chroma / np.sum(chroma)
            else:
                return None, 0.0
            
            # Correlate with major and minor key profiles
            best_key = None
            best_score = -1.0
            best_mode = "major"
            
            for shift in range(12):
                # Rotate chroma to test each key
                shifted_chroma = np.roll(chroma, shift)
                
                # Score against major profile
                major_score = float(np.dot(shifted_chroma, self.major_profile))
                if major_score > best_score:
                    best_score = major_score
                    best_key = self.major_key_names[shift]
                    best_mode = "major"
                
                # Score against minor profile
                minor_score = float(np.dot(shifted_chroma, self.minor_profile))
                if minor_score > best_score:
                    best_score = minor_score
                    best_key = self.minor_key_names[shift]
                    best_mode = "minor"
            
            # Confidence: how much better is the best match than average?
            avg_score = float(np.mean([
                np.dot(np.roll(chroma, i), self.major_profile) for i in range(12)
            ]))
            confidence = max(0.0, min(1.0, (best_score - avg_score) / max(avg_score, 0.1)))
            
            return best_key, confidence
        except Exception as e:
            logger.debug(f"Key detection error: {e}")
            return None, 0.0
    
    def _smooth_tonality(self, detected_key: str | None, confidence: float) -> tuple[str | None, float]:
        """Smooth tonality detection using history voting.
        
        Keep last 10-15 detected keys and return the most common one for stability.
        
        Args:
            detected_key: Newly detected key (or None)
            confidence: Detection confidence (0-1)
            
        Returns:
            Tuple of (smoothed_key, smoothed_confidence)
        """
        # Add to history
        if detected_key is not None:
            self.key_history.append((detected_key, confidence))
        
        # Keep only recent entries
        if len(self.key_history) > self.max_key_history:
            self.key_history.pop(0)
        
        # Not enough data yet
        if len(self.key_history) < 3:
            return detected_key, confidence
        
        # Vote: find most common key in history
        key_counts = {}
        for key, conf in self.key_history:
            key_counts[key] = key_counts.get(key, 0) + 1
        
        # Most common key
        smoothed_key = max(key_counts, key=key_counts.get)
        
        # Average confidence of the smoothed key
        smoothed_confidences = [conf for key, conf in self.key_history if key == smoothed_key]
        smoothed_confidence = float(np.mean(smoothed_confidences)) if smoothed_confidences else 0.0
        
        return smoothed_key, smoothed_confidence
    
    def update_metrics(self, overall_amplitude: float, rms: float, 
                      bass_energy: float, mid_energy: float, high_energy: float,
                      onset_detected: bool = False, beat_confidence: float = 0.0) -> None:
        """Update tracking metrics for aggregation.
        
        Args:
            overall_amplitude: Peak amplitude (0-1)
            rms: RMS energy (0-1)
            bass_energy: Bass band energy (0-1)
            mid_energy: Mid band energy (0-1)
            high_energy: High band energy (0-1)
            onset_detected: Whether onset was detected
            beat_confidence: Beat confidence (0-1)
        """
        self.amplitude_history.append(overall_amplitude)
        self.rms_history.append(rms)
        self.onset_history.append(onset_detected)
        self.beat_confidence_history.append(beat_confidence)
        
        # Update band envelopes
        self.bass_envelope.append(bass_energy)
        self.mid_envelope.append(mid_energy)
        self.high_envelope.append(high_energy)
        
        # Keep only recent history
        max_size = max(20, self.max_history * 3)
        if len(self.amplitude_history) > max_size:
            self.amplitude_history.pop(0)
            self.rms_history.pop(0)
            self.onset_history.pop(0)
            self.beat_confidence_history.pop(0)
        
        if len(self.bass_envelope) > self.max_envelope_length:
            self.bass_envelope.pop(0)
            self.mid_envelope.pop(0)
            self.high_envelope.pop(0)
    
    def analyze(self, audio_chunk: np.ndarray, timestamp_s: float) -> SlowFeatures:
        """Analyze audio chunk for slow features over 100-500ms window.
        
        Aggregates and analyzes:
        - Amplitude metrics (overall, RMS, peak)
        - Frequency band energy (bass, mid, high)
        - Spectral characteristics (centroid, density distribution)
        - Musical tonality (key detection)
        - Transient detection (onsets, beats)
        - Tempo estimation
        - Energy trend for scene changes
        
        Args:
            audio_chunk: Audio samples (n_samples, 2) in float32
            timestamp_s: Timestamp of chunk start
            
        Returns:
            SlowFeatures with comprehensive slow-tier analysis
        """
        # Convert stereo to mono
        if audio_chunk.ndim == 2:
            audio_mono = np.mean(audio_chunk, axis=1)
        else:
            audio_mono = audio_chunk
        
        # ════════════════════════════════════════════════════════════════════
        # AMPLITUDE METRICS - computed on full window
        # ════════════════════════════════════════════════════════════════════
        overall_amplitude = float(np.max(np.abs(audio_mono)))
        rms = float(np.sqrt(np.mean(audio_mono ** 2)))
        peak = float(np.max(np.abs(audio_mono)))
        
        # Clamp to 0-1
        overall_amplitude = min(1.0, overall_amplitude)
        rms = min(1.0, rms)
        peak = min(1.0, peak)
        
        # ════════════════════════════════════════════════════════════════════
        # SPECTRAL ANALYSIS - STFT for bands and tonality
        # ════════════════════════════════════════════════════════════════════
        n_fft = 2048
        window = signal.windows.hann(min(len(audio_mono), n_fft), sym=False)
        
        if len(audio_mono) < n_fft:
            padded = np.pad(audio_mono, (0, n_fft - len(audio_mono)))
        else:
            padded = audio_mono[:n_fft]
        
        stft = np.fft.rfft(padded * window)
        magnitude = np.abs(stft)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)
        
        # Frequency band masks
        bass_mask = freqs < FREQ_BAND_BASS_MAX
        mid_mask = (freqs >= FREQ_BAND_MID_MIN) & (freqs < FREQ_BAND_MID_MAX)
        high_mask = freqs >= FREQ_BAND_HIGH_MIN
        
        # Extract band energy
        total_energy = np.sum(magnitude)
        if total_energy > 0:
            bass_energy = float(np.mean(magnitude[bass_mask])) if np.any(bass_mask) else 0.0
            mid_energy = float(np.mean(magnitude[mid_mask])) if np.any(mid_mask) else 0.0
            high_energy = float(np.mean(magnitude[high_mask])) if np.any(high_mask) else 0.0
            
            # Normalize by max
            max_mag = np.max(magnitude) if np.max(magnitude) > 0 else 1.0
            bass_energy = min(1.0, bass_energy / max_mag)
            mid_energy = min(1.0, mid_energy / max_mag)
            high_energy = min(1.0, high_energy / max_mag)
            
            # Spectral density (proportion in each band)
            spectral_density_low = np.sum(magnitude[bass_mask]) / total_energy
            spectral_density_mid = np.sum(magnitude[mid_mask]) / total_energy
            spectral_density_high = np.sum(magnitude[high_mask]) / total_energy
        else:
            bass_energy = 0.0
            mid_energy = 0.0
            high_energy = 0.0
            spectral_density_low = 0.33
            spectral_density_mid = 0.33
            spectral_density_high = 0.34
        
        # Store spectral for tonality averaging
        self.spectral_history.append(magnitude)
        if len(self.spectral_history) > self.max_spectral_history:
            self.spectral_history.pop(0)
        
        # ════════════════════════════════════════════════════════════════════
        # TONALITY DETECTION - musical key analysis
        # ════════════════════════════════════════════════════════════════════
        # Use average of spectral history for more stable key detection
        if len(self.spectral_history) > 1:
            avg_spectrum = np.mean([s for s in self.spectral_history], axis=0)
            # Create audio from average spectrum (inverse FFT)
            detected_key, key_confidence = self._detect_key(audio_mono)
        else:
            detected_key, key_confidence = self._detect_key(audio_mono)
        
        # Smooth tonality using history voting (keep last 12 detections)
        detected_key, key_confidence = self._smooth_tonality(detected_key, key_confidence)
        
        # ════════════════════════════════════════════════════════════════════
        # ENERGY TRACKING - for trend and variance
        # ════════════════════════════════════════════════════════════════════
        average_energy = rms  # Use RMS as overall energy metric
        
        self.energy_history.append(average_energy)
        if len(self.energy_history) > self.max_history:
            self.energy_history.pop(0)
        
        # Energy statistics
        energy_variance = float(np.var(self.energy_history)) if len(self.energy_history) > 1 else 0.0
        
        # Trend (positive = increasing, negative = decreasing)
        if len(self.energy_history) > 2:
            recent = self.energy_history[-3:]
            trend = float(np.polyfit(range(len(recent)), recent, 1)[0])  # Slope
            trend = max(-1.0, min(1.0, trend))  # Clamp to -1 to 1
        else:
            trend = 0.0
        
        # ════════════════════════════════════════════════════════════════════
        # AGGREGATED TRANSIENT METRICS
        # ════════════════════════════════════════════════════════════════════
        # Check if any onsets in recent history
        onset_detected = any(self.onset_history[-5:]) if len(self.onset_history) > 0 else False
        
        # Average beat confidence
        beat_confidence = float(np.mean(self.beat_confidence_history)) if len(self.beat_confidence_history) > 0 else 0.0
        beat_detected = beat_confidence > 0.5  # Require >50% confidence (was 0.3, filtering noise)
        
        # ════════════════════════════════════════════════════════════════════
        # TEMPO ESTIMATION (with beat interval validation)
        # ════════════════════════════════════════════════════════════════════
        estimated_bpm = None
        beat_stability = 0.0
        
        logger.debug(f"[SlowAnalyzer] Tempo estimation: {len(self.beat_timestamps)} beats in history (need 3+)")
        
        if len(self.beat_timestamps) >= 3:
            intervals = np.diff(self.beat_timestamps)
            
            # VALIDATION: Filter by realistic BPM range (60-220 BPM for electronic music)
            # BPM = 60 / interval_seconds, so:
            # 220 BPM = 0.273s per beat (max fast tempo)
            # 60 BPM = 1.0s per beat (min slow tempo)
            MIN_INTERVAL = 60.0 / 220.0  # 220 BPM max ≈ 0.273s
            MAX_INTERVAL = 60.0 / 60.0   # 60 BPM min = 1.0s
            
            valid_intervals = intervals[
                (intervals >= MIN_INTERVAL) & (intervals <= MAX_INTERVAL)
            ]
            
            if len(valid_intervals) >= 2:
                # Use valid intervals for BPM calculation
                avg_interval = np.mean(valid_intervals)
                interval_std = np.std(valid_intervals)
                
                # Convert to BPM
                if avg_interval > 0:
                    beats_per_second = 1.0 / avg_interval
                    estimated_bpm = beats_per_second * 60.0
                    
                    # Stability: how consistent are the intervals?
                    # High stability = low coefficient of variation
                    cv = interval_std / avg_interval if avg_interval > 0 else 0
                    beat_stability = max(0.0, min(1.0, 1.0 - (cv / 0.2)))
                    
                    logger.info(
                        f"[SlowAnalyzer] BPM CALCULATED: {estimated_bpm:.1f} BPM "
                        f"(stability={beat_stability:.2f}, valid_intervals={len(valid_intervals)}/{len(intervals)}, "
                        f"avg={avg_interval:.3f}s)"
                    )
                else:
                    logger.warning(f"[SlowAnalyzer] BPM calc failed: avg_interval={avg_interval} <= 0")
            else:
                # Not enough valid intervals
                logger.debug(
                    f"[SlowAnalyzer] Too many invalid intervals: {len(intervals) - len(valid_intervals)}/{len(intervals)} "
                    f"outside range [{MIN_INTERVAL}, {MAX_INTERVAL}]. "
                    f"Intervals: {list(np.round(intervals, 3))}"
                )
        else:
            logger.debug(f"[SlowAnalyzer] Not enough beats for BPM: {len(self.beat_timestamps)}/3 (need 3+)")
        
        # ════════════════════════════════════════════════════════════════════
        # FREQUENCY BAND ENVELOPES - for visualization
        # ════════════════════════════════════════════════════════════════════
        band_bass_envelope = tuple(self.bass_envelope[-self.max_envelope_length:]) if self.bass_envelope else None
        band_mid_envelope = tuple(self.mid_envelope[-self.max_envelope_length:]) if self.mid_envelope else None
        band_high_envelope = tuple(self.high_envelope[-self.max_envelope_length:]) if self.high_envelope else None
        
        return SlowFeatures(
            timestamp_s=timestamp_s,
            # Amplitude metrics
            overall_amplitude=overall_amplitude,
            rms=rms,
            peak=peak,
            # Frequency bands
            bass_energy=bass_energy,
            mid_energy=mid_energy,
            high_energy=high_energy,
            # Spectral characteristics
            spectral_density_low=float(spectral_density_low),
            spectral_density_mid=float(spectral_density_mid),
            spectral_density_high=float(spectral_density_high),
            # Tonality
            detected_key=detected_key,
            key_confidence=key_confidence,
            # Transients
            onset_detected=onset_detected,
            beat_detected=beat_detected,
            beat_confidence=beat_confidence,
            # Tempo
            estimated_bpm=estimated_bpm,
            beat_stability=beat_stability,
            # Dynamics
            average_energy=average_energy,
            energy_variance=float(energy_variance),
            energy_trend=trend,
            # Envelopes
            band_bass_envelope=band_bass_envelope,
            band_mid_envelope=band_mid_envelope,
            band_high_envelope=band_high_envelope,
        )
    
    def analyze_beat_tempo(self, long_audio_chunk: np.ndarray, slow_features: SlowFeatures) -> SlowFeatures:
        """Analyze beat/tempo from a LONGER audio window (2+ seconds).
        
        This is called after analyze() with a much longer audio window to provide
        better BPM stability. The longer window lets us detect more beats and
        calculate more stable tempo estimates.
        
        Args:
            long_audio_chunk: Audio samples from longer window (2+ seconds)
            slow_features: Previously calculated SlowFeatures from normal window
            
        Returns:
            Updated SlowFeatures with improved beat_detected, estimated_bpm, beat_stability
        """
        try:
            # Convert stereo to mono if needed
            if long_audio_chunk.ndim == 2:
                audio_mono = np.mean(long_audio_chunk, axis=1)
            else:
                audio_mono = long_audio_chunk
            
            # Only recalculate if we have enough beat data
            if len(self.beat_timestamps) < 2:
                return slow_features
            
            # Calculate BPM from accumulated beat timestamps
            intervals = np.diff(self.beat_timestamps)
            
            # Filter outliers (very short or very long intervals)
            # Reasonable range: 60-240 BPM = 0.25-1.0 seconds
            valid_intervals = intervals[(intervals > 0.25) & (intervals < 1.0)]
            
            if len(valid_intervals) < 2:
                # Not enough valid intervals yet
                return slow_features
            
            avg_interval = np.mean(valid_intervals)
            interval_std = np.std(valid_intervals)
            
            # Convert to BPM
            if avg_interval > 0:
                beats_per_second = 1.0 / avg_interval
                estimated_bpm = beats_per_second * 60.0
                
                # Clamp to reasonable range (60-240 BPM)
                estimated_bpm = max(60.0, min(240.0, estimated_bpm))
                
                # Stability: how consistent are the intervals?
                # Normalized by comparing std to interval (coefficient of variation)
                # Typical variation ~10% = stability 0.8-0.9
                if avg_interval > 1e-10:
                    cv = interval_std / avg_interval  # Coefficient of variation
                    beat_stability = max(0.0, min(1.0, 1.0 - cv))
                else:
                    beat_stability = 0.0
                
                # Update slow_features with better beat analysis
                # Replace the normal analysis with this longer-window version
                return SlowFeatures(
                    timestamp_s=slow_features.timestamp_s,
                    # Keep all metrics from original
                    overall_amplitude=slow_features.overall_amplitude,
                    rms=slow_features.rms,
                    peak=slow_features.peak,
                    bass_energy=slow_features.bass_energy,
                    mid_energy=slow_features.mid_energy,
                    high_energy=slow_features.high_energy,
                    spectral_density_low=slow_features.spectral_density_low,
                    spectral_density_mid=slow_features.spectral_density_mid,
                    spectral_density_high=slow_features.spectral_density_high,
                    detected_key=slow_features.detected_key,
                    key_confidence=slow_features.key_confidence,
                    onset_detected=slow_features.onset_detected,
                    beat_detected=slow_features.beat_detected,
                    beat_confidence=slow_features.beat_confidence,
                    # UPDATED: Better beat/tempo from longer window
                    estimated_bpm=estimated_bpm,
                    beat_stability=beat_stability,
                    # Keep other metrics
                    average_energy=slow_features.average_energy,
                    energy_variance=slow_features.energy_variance,
                    energy_trend=slow_features.energy_trend,
                    band_bass_envelope=slow_features.band_bass_envelope,
                    band_mid_envelope=slow_features.band_mid_envelope,
                    band_high_envelope=slow_features.band_high_envelope,
                )
        except Exception as e:
            logger.debug(f"Beat/tempo analysis error: {e}")
            # Return original features if analysis fails
            return slow_features
