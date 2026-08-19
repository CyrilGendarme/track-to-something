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
        daemon: bool = False,
    ):
        """Initialize audio processing worker.
        
        Args:
            name: Worker thread name
            input_queue: Queue receiving AudioChunkMessage
            output_queue: Queue to send AudioFeaturesMessage to
            n_fft: FFT size for analysis (default from config)
            hop_length: Hop length for STFT (default from config)
            daemon: If True, thread will not prevent program exit
        """
        super().__init__(name=name, input_queue=input_queue, daemon=daemon)
        self.output_queue = output_queue
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.timestamp = 0.0

    def _process_item(self, item: AudioChunkMessage) -> None:
        """Analyze audio chunk and extract comprehensive features."""
        try:
            perf = get_performance_monitor()
            process_start = time.perf_counter()
            
            import librosa
            from scipy import signal
            
            self.sample_rate = item.sample_rate
            
            # Convert stereo to mono
            if item.samples.ndim == 2:
                mono = item.samples.mean(axis=1)
            else:
                mono = item.samples
            
            # 1. Overall amplitude metrics
            with perf.timing_context("process:amplitude_metrics"):
                overall_amplitude = float(np.max(np.abs(mono)))
                rms = float(np.sqrt(np.mean(mono ** 2)))
                peak = float(np.max(np.abs(mono)))
            
            # 2. Spectral analysis
            with perf.timing_context("process:stft"):
                spectrum = librosa.stft(
                    mono, n_fft=self.n_fft, hop_length=self.hop_length, center=True
                )
                magnitude = np.abs(spectrum)
                frequencies = librosa.fft_frequencies(sr=self.sample_rate, n_fft=self.n_fft)
                frame_energy = magnitude.mean(axis=0)
                total_energy = float(magnitude.sum())
            
            # 3. Spectral features
            with perf.timing_context("process:spectral_features"):
                if total_energy > 1e-10:
                    centroid = float(librosa.feature.spectral_centroid(
                        S=magnitude, sr=self.sample_rate, n_fft=self.n_fft
                    )[0].mean())
                    
                    dominant_bin = int(np.argmax(magnitude.sum(axis=1)))
                    dominant_freq = float(frequencies[dominant_bin])
                else:
                    centroid = 0.0
                    dominant_freq = 0.0
            
            # 4. Energy in frequency bands
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
            
            # 5. Beat detection with confidence
            with perf.timing_context("process:beat_detection"):
                frame_rms = np.sqrt(np.mean(frame_energy ** 2))
                beat_threshold = frame_rms * 1.5
                beat_detected = bool(np.any(frame_energy > beat_threshold))
                
                # Beat confidence: how much above threshold
                if frame_rms > 0:
                    beat_strength = np.max(frame_energy) / (beat_threshold + 1e-10)
                    beat_confidence = min(1.0, beat_strength / 3.0)  # Normalize to 0-1
                else:
                    beat_confidence = 0.0
            
            # 6. Onset/attack detection (rapid amplitude rise)
            with perf.timing_context("process:onset_detection"):
                onset_envelope = librosa.onset.onset_strength(y=mono, sr=self.sample_rate)
                onset_detected = bool(np.any(onset_envelope > np.mean(onset_envelope) * 2.0))
            
            # 7. Tempo estimation
            with perf.timing_context("process:tempo_estimation"):
                if len(frame_energy) > 1:
                    bpm = self._estimate_tempo(frame_energy, self.sample_rate)
                else:
                    bpm = None
            
            # 8. Frequency band envelopes (for visualization)
            with perf.timing_context("process:band_envelopes"):
                band_bass_envelope = tuple(magnitude[bass_mask, :].mean(axis=0)[:10])
                band_mid_envelope = tuple(magnitude[mid_mask, :].mean(axis=0)[:10])
                band_high_envelope = tuple(magnitude[high_mask, :].mean(axis=0)[:10])
            
            # Create comprehensive features message
            features = AudioFeaturesMessage(
                timestamp_s=self.timestamp,
                overall_amplitude=overall_amplitude,
                rms=rms,
                peak=peak,
                bass_energy=bass_energy,
                mid_energy=mid_energy,
                high_energy=high_energy,
                spectral_centroid_hz=centroid,
                dominant_frequency_hz=dominant_freq,
                onset_detected=onset_detected,
                beat_detected=beat_detected,
                beat_confidence=beat_confidence,
                bpm=bpm,
                band_bass_envelope=band_bass_envelope,
                band_mid_envelope=band_mid_envelope,
                band_high_envelope=band_high_envelope,
            )
            
            with perf.timing_context("process:queue_put"):
                self.output_queue.put(features)
            
            self.timestamp += len(mono) / self.sample_rate
            
            # Log timing every 50 chunks
            if not hasattr(self, '_chunk_count'):
                self._chunk_count = 0
            self._chunk_count += 1
            if self._chunk_count % 50 == 0:
                process_duration_ms = (time.perf_counter() - process_start) * 1000
                logger.debug(f"[{self.name}] Chunk {self._chunk_count}: {process_duration_ms:.2f}ms")
            
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
