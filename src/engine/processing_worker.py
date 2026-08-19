"""Audio processing worker - analyzes chunks and extracts features."""

from __future__ import annotations

import logging
import time
from collections import deque
from queue import Queue

import numpy as np

from src.config import (
    DEFAULT_SAMPLE_RATE,
    STFT_FFT_SIZE,
    STFT_HOP_LENGTH,
)
from src.engine.base import QueuedWorker
from src.engine.messages import AudioChunkMessage, AudioFeaturesMessage
from src.engine.performance import get_performance_monitor

logger = logging.getLogger(__name__)


class BeatPredictor:
    """Predictive beat synchronization.
    
    Instead of reacting to detected beats (which has inherent latency),
    this predictor estimates the next beat based on tempo stability.
    
    For music with stable tempo, this enables anticipatory animations
    and low-latency game synchronization.
    """

    def __init__(self, max_history: int = 10):
        """Initialize beat predictor.
        
        Args:
            max_history: Number of recent beats to use for prediction (default 10)
        """
        self.beat_timestamps: deque[float] = deque(maxlen=max_history)
        self.beat_intervals: deque[float] = deque(maxlen=max_history - 1)
        self.last_beat_timestamp: float | None = None
        self.last_predicted_beat: float | None = None

    def record_beat(self, timestamp_s: float) -> None:
        """Record a detected beat.
        
        Args:
            timestamp_s: Beat detection timestamp in seconds
        """
        if self.last_beat_timestamp is not None:
            interval = timestamp_s - self.last_beat_timestamp
            # Only accept intervals in reasonable range (60-240 BPM)
            if 0.25 < interval < 1.0:  # 60-240 BPM
                self.beat_intervals.append(interval)
        
        self.beat_timestamps.append(timestamp_s)
        self.last_beat_timestamp = timestamp_s

    def predict_next_beat(self, current_timestamp_s: float) -> tuple[float | None, float]:
        """Predict when the next beat will occur.
        
        Returns:
            (predicted_timestamp_s, prediction_confidence_0to1)
            - predicted_timestamp_s: When next beat is expected (None if not enough data)
            - prediction_confidence_0to1: How stable the tempo is (0=high variance, 1=stable)
        """
        if len(self.beat_intervals) < 2:
            return None, 0.0

        # Use average interval as base prediction
        avg_interval = np.mean(list(self.beat_intervals))
        
        # Calculate tempo stability (low variance = high confidence)
        interval_variance = np.var(list(self.beat_intervals))
        interval_std = np.sqrt(interval_variance)
        
        # Normalize std to confidence (max std of 0.2s gives confidence 0)
        tempo_confidence = max(0.0, 1.0 - (interval_std / 0.2))
        
        if self.last_beat_timestamp is None:
            return None, tempo_confidence

        # Predict next beat as last_beat + average_interval
        predicted_next = self.last_beat_timestamp + avg_interval
        
        return predicted_next, tempo_confidence

    def get_beat_phase(self, current_timestamp_s: float) -> float:
        """Get phase in current beat cycle (0=just beat, 1=next beat arriving).
        
        Args:
            current_timestamp_s: Current time in seconds
            
        Returns:
            Phase 0.0-1.0 (0=just after beat, 1=about to beat again)
        """
        if len(self.beat_intervals) < 1 or self.last_beat_timestamp is None:
            return 0.0

        avg_interval = np.mean(list(self.beat_intervals))
        time_since_beat = current_timestamp_s - self.last_beat_timestamp
        
        # Clamp to 0-1 range (wraps around at next beat)
        phase = (time_since_beat / avg_interval) % 1.0
        return phase

    def get_estimated_bpm(self) -> float | None:
        """Get estimated BPM based on recent beat intervals.
        
        Returns:
            BPM or None if not enough data
        """
        if len(self.beat_intervals) < 1:
            return None

        avg_interval = np.mean(list(self.beat_intervals))
        return 60.0 / avg_interval


class AudioProcessingWorker(QueuedWorker):
    """Processes audio chunks with DSP analysis."""

    def __init__(
        self,
        name: str,
        input_queue: Queue,
        output_queue: Queue,
        n_fft: int = STFT_FFT_SIZE,
        hop_length: int = STFT_HOP_LENGTH,
        feature_cache: "FeatureCache | None" = None,
        multi_analyzer: "MultiWindowAudioAnalyzer | None" = None,
        daemon: bool = False,
    ):
        """Initialize audio processing worker.
        
        Args:
            name: Worker thread name
            input_queue: Queue receiving AudioChunkMessage
            output_queue: Queue to send AudioFeaturesMessage to
            n_fft: FFT size for analysis (default from config)
            hop_length: Hop length for STFT (default from config)
            feature_cache: Optional FeatureCache for storing tiered features for GUI
            multi_analyzer: SHARED MultiWindowAudioAnalyzer (passed from pipeline)
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, input_queue=input_queue, daemon=daemon)
        self.output_queue = output_queue
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.feature_cache = feature_cache
        
        # TIERED ANALYSIS: Track which analyses to skip on this chunk
        self._chunk_counter = 0
        from src.config import SPECTRAL_ANALYSIS_DECIMATION, TEMPO_ANALYSIS_DECIMATION
        self.spectral_decimation = SPECTRAL_ANALYSIS_DECIMATION
        self.tempo_decimation = TEMPO_ANALYSIS_DECIMATION
        
        # Cache spectral data between chunks for stability
        self._prev_magnitude: np.ndarray | None = None
        self._prev_frame_energy: np.ndarray | None = None
        
        # Use SHARED multi-window analyzer (passed from pipeline)
        # This ensures all parallel workers feed beats into the SAME tempo tracker
        if multi_analyzer is None:
            # Fallback if not provided (backward compatibility)
            from src.analysis import MultiWindowAudioAnalyzer
            self.multi_analyzer = MultiWindowAudioAnalyzer(sample_rate=DEFAULT_SAMPLE_RATE)
            logger.warning(f"[{name}] No shared multi_analyzer provided, creating own (beats won't be shared)")
        else:
            self.multi_analyzer = multi_analyzer
            logger.debug(f"[{name}] Using shared MultiWindowAnalyzer with stream timestamps for beat aggregation")

    def _process_item(self, item: AudioChunkMessage) -> None:
        """Analyze audio chunk with TIERED ANALYSIS strategy.
        
        ═══════════════════════════════════════════════════════════════════════
        TIERED ANALYSIS: Different features at different refresh rates
        ═══════════════════════════════════════════════════════════════════════
        
        FAST TIER (Every chunk, ~5-10ms):
        - Overall amplitude (RMS, peak, max)
        - Beat detection (simple envelope)
        - Onset detection (spectral flux - not librosa)
        - Use: Kick flash, snare burst, immediate effects
        
        MEDIUM TIER (Every 2-3 chunks, ~20-50ms):
        - Full STFT spectral analysis
        - Spectral centroid (brightness)
        - Frequency band energy (bass, mid, high)
        - Band envelopes
        - Use: Smooth animations, energy tracking
        
        SLOW TIER (Every 8+ chunks, ~300-700ms):
        - Tempo/BPM estimation
        - Use: Scene changes, animation speed
        """
        try:
            perf = get_performance_monitor()
            process_start = time.perf_counter()
            
            from scipy import signal as scipy_signal
            
            self.sample_rate = item.sample_rate
            self._chunk_counter += 1
            
            # Determine which analyses to run on this chunk
            do_spectral = (self._chunk_counter % self.spectral_decimation) == 0
            do_tempo = (self._chunk_counter % self.tempo_decimation) == 0
            
            # Convert stereo to mono
            if item.samples.ndim == 2:
                mono = item.samples.mean(axis=1)
            else:
                mono = item.samples
            
            # ════════════════════════════════════════════════════════════════════
            # FAST TIER: ALWAYS RUN (< 10ms) - Amplitude, Beat, Onset
            # ════════════════════════════════════════════════════════════════════
            
            # 1. Overall amplitude metrics (FAST)
            with perf.timing_context("process:amplitude_metrics"):
                overall_amplitude = float(np.max(np.abs(mono)))
                rms = float(np.sqrt(np.mean(mono ** 2)))
                peak = float(np.max(np.abs(mono)))
            
            # 3. STFT: Always compute for onset detection and optional spectral analysis
            with perf.timing_context("process:stft"):
                # Replace librosa.stft with scipy.signal.stft (faster, no librosa dependency)
                # scipy.signal.stft returns (f, t, Zxx) where Zxx is STFT matrix
                frequencies, frame_times, spectrum = scipy_signal.stft(
                    mono,
                    fs=self.sample_rate,
                    nperseg=self.n_fft,
                    noverlap=self.n_fft - self.hop_length,
                    window='hann',
                    return_onesided=True,
                )
                magnitude = np.abs(spectrum)
                frame_energy = magnitude.mean(axis=0)
                total_energy = float(magnitude.sum())
            
            # 2+4. Beat & Onset detection using spectral flux (more reliable than amplitude)
            with perf.timing_context("process:beat_onset_detection"):
                beat_detected = False
                beat_confidence = 0.0
                onset_detected = False
                
                if magnitude.shape[1] > 1 and self._prev_magnitude is not None:
                    # Spectral flux: changes in magnitude spectrum frame-to-frame
                    # This is more reliable than simple amplitude thresholding
                    mag_diff = magnitude - self._prev_magnitude
                    flux = np.sqrt(np.sum(mag_diff ** 2, axis=0))
                    
                    if len(flux) > 1:
                        flux_mean = np.mean(flux)
                        flux_std = np.std(flux)
                        
                        # Onset threshold: 2.5x std above mean
                        onset_threshold = flux_mean + (flux_std * 2.5)
                        onset_detected = bool(np.any(flux > onset_threshold))
                        
                        # Beat detection: strong spectral flux (onset) + energy above baseline
                        # Peaks in flux with high energy = percussive beat
                        if np.any(flux > onset_threshold) and overall_amplitude > rms * 1.3:
                            max_flux = float(np.max(flux))
                            beat_confidence = min(1.0, (max_flux / flux_mean - 1.0) / 5.0)
                            beat_detected = beat_confidence > 0.3  # Only beats with >30% confidence
                            logger.info(f"[{self.name}] BEAT DETECTED @ {item.timestamp_s:.3f}s: confidence={beat_confidence:.2f}, amp={overall_amplitude:.3f}, rms={rms:.3f}, flux_max={max_flux:.3f}")
                    else:
                        onset_detected = False
                else:
                    # Fallback to amplitude-based beat detection if STFT unavailable
                    mono_env = np.abs(mono)
                    env_rms = np.sqrt(np.mean(mono_env ** 2))
                    beat_threshold = env_rms * 1.5
                    beat_detected = overall_amplitude > beat_threshold
                    
                    if beat_threshold > 1e-10:
                        beat_confidence = min(1.0, (overall_amplitude / beat_threshold) / 3.0)
                    else:
                        beat_confidence = 0.0
                    
                    if beat_detected:
                        logger.info(f"[{self.name}] BEAT (FALLBACK) @ {item.timestamp_s:.3f}s: confidence={beat_confidence:.2f}, amp={overall_amplitude:.3f}")
            
            # Cache magnitude for next frame's beat/onset detection
            self._prev_magnitude = magnitude.copy()
            self._prev_frame_energy = frame_energy.copy() if frame_energy is not None else None
            
            # ════════════════════════════════════════════════════════════════════
            # MEDIUM TIER: EVERY 2-3 CHUNKS (~20-50ms) - Spectral Features
            # ════════════════════════════════════════════════════════════════════
            
            dominant_freq = 0.0
            bass_energy = 0.0
            mid_energy = 0.0
            high_energy = 0.0
            band_bass_envelope = None
            band_mid_envelope = None
            band_high_envelope = None
            
            if do_spectral:
                # 5. Spectral features (MEDIUM)
                with perf.timing_context("process:spectral_features"):
                    # REMOVED: Spectral centroid calculation (2-4ms saved per decimated chunk)
                    # Centroid was only used for logging, not for visualization effects
                    # If needed in future, can be re-added:
                    # power = magnitude.sum(axis=1)
                    # centroid = np.sum(frequencies * power) / np.sum(power)
                    
                    if total_energy > 1e-10:
                        # Dominant frequency
                        power = magnitude.sum(axis=1)
                        dominant_bin = int(np.argmax(power))
                        dominant_freq = float(frequencies[dominant_bin])
                    else:
                        dominant_freq = 0.0
                
                # 6. Energy in frequency bands (MEDIUM)
                with perf.timing_context("process:frequency_bands"):
                    bass_mask = frequencies < 250
                    mid_mask = (frequencies >= 250) & (frequencies < 4000)
                    high_mask = frequencies >= 4000
                    
                    bass_energy = float(np.mean(magnitude[bass_mask, :]))
                    mid_energy = float(np.mean(magnitude[mid_mask, :]))
                    high_energy = float(np.mean(magnitude[high_mask, :]))
                    
                    # Normalize to 0-1 range
                    max_band_energy = max(bass_energy, mid_energy, high_energy, 1e-10)
                    bass_energy = bass_energy / max_band_energy
                    mid_energy = mid_energy / max_band_energy
                    high_energy = high_energy / max_band_energy
                
                # 7. Frequency band envelopes (MEDIUM)
                with perf.timing_context("process:band_envelopes"):
                    band_bass_envelope = tuple(magnitude[bass_mask, :].mean(axis=0)[:10])
                    band_mid_envelope = tuple(magnitude[mid_mask, :].mean(axis=0)[:10])
                    band_high_envelope = tuple(magnitude[high_mask, :].mean(axis=0)[:10])
            
            # ════════════════════════════════════════════════════════════════════
            # SLOW TIER: EVERY 8+ CHUNKS (~300-700ms) - Tempo Estimation
            # ════════════════════════════════════════════════════════════════════
            
            bpm = None
            if do_tempo and frame_energy is not None and len(frame_energy) > 1:
                with perf.timing_context("process:tempo_estimation"):
                    bpm = self._estimate_tempo(frame_energy, self.sample_rate)
            
            # Create comprehensive features message
            features = AudioFeaturesMessage(
                timestamp_s=self.timestamp,
                overall_amplitude=overall_amplitude,
                rms=rms,
                peak=peak,
                bass_energy=bass_energy,
                mid_energy=mid_energy,
                high_energy=high_energy,
                spectral_centroid_hz=None,  # REMOVED for performance (2-4ms saved)
                dominant_frequency_hz=dominant_freq,
                onset_detected=onset_detected,
                beat_detected=beat_detected,
                beat_confidence=beat_confidence,
                bpm=bpm,
                band_bass_envelope=band_bass_envelope,
                band_mid_envelope=band_mid_envelope,
                band_high_envelope=band_high_envelope,
            )
            
            # Update multi-window analyzer with current audio and store tiered features for GUI
            if self.feature_cache and self.multi_analyzer:
                with perf.timing_context("process:tiered_analysis"):
                    try:
                        # Feed audio to the analyzer
                        if item.samples.ndim == 2:
                            self.multi_analyzer.add_audio_chunk(item.samples.astype(np.float32))
                        else:
                            # Mono input needs to be duplicated to match expected 2-channel format
                            stereo_chunk = np.column_stack([item.samples, item.samples])
                            self.multi_analyzer.add_audio_chunk(stereo_chunk.astype(np.float32))
                        
                        # Record beat detection for tempo tracking
                        # This feeds beat_detected events into slow_analyzer.beat_timestamps
                        # which is used for BPM estimation
                        if beat_detected:
                            self.multi_analyzer.record_beat_detection(item.timestamp_s, beat_confidence)
                        
                        # Analyze all tiers periodically (every few chunks)
                        if self._chunk_counter % 4 == 0:  # Every ~4 chunks (~46ms)
                            fast_f, medium_f, slow_f = self.multi_analyzer.analyze_all(item.timestamp_s)
                            self.feature_cache.update(fast=fast_f, medium=medium_f, slow=slow_f)
                    except Exception as e:
                        logger.debug(f"[{self.name}] Error in tiered analysis: {e}")
            
            with perf.timing_context("process:queue_put"):
                self.output_queue.put(features)
            
            # Log timing every 100 chunks
            if not hasattr(self, '_chunk_count'):
                self._chunk_count = 0
            self._chunk_count += 1
            if self._chunk_count % 100 == 0:
                process_duration_ms = (time.perf_counter() - process_start) * 1000
                tier_msg = f"[FAST] {process_duration_ms:.2f}ms"
                if do_spectral:
                    tier_msg = f"[FAST+MEDIUM] {process_duration_ms:.2f}ms"
                if do_tempo:
                    tier_msg = f"[FAST+MEDIUM+SLOW] {process_duration_ms:.2f}ms"
                logger.debug(f"[{self.name}] Chunk {self._chunk_count}: {tier_msg}")
            
        except Exception as e:
            logger.exception(f"[{self.name}] Processing error")
            raise

    def _estimate_tempo(self, frame_energy: np.ndarray, sample_rate: int) -> float | None:
        """Estimate tempo from energy frames."""
        try:
            # Simple autocorrelation-based tempo estimation
            if len(frame_energy) < 10:
                return None
            
            # Find peaks in energy
            peaks = []
            for i in range(1, len(frame_energy) - 1):
                if frame_energy[i] > frame_energy[i-1] and frame_energy[i] > frame_energy[i+1]:
                    peaks.append(i)
            
            if len(peaks) < 2:
                return None
            
            # Compute inter-peak intervals
            intervals = np.diff(peaks)
            avg_interval = np.mean(intervals)
            
            # Convert to BPM (assuming hop_length of 512 samples)
            time_per_frame = self.hop_length / sample_rate
            beats_per_second = 1.0 / (avg_interval * time_per_frame)
            bpm = beats_per_second * 60.0
            
            # Clamp to reasonable tempo range
            if 60 <= bpm <= 240:
                return bpm
            return None
        except Exception:
            return None
