"""Extract musical and spectral features from chunked PCM audio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import librosa
import numpy as np

from src.config import STFT_FFT_SIZE, STFT_HOP_LENGTH
from src.sources.audio_source import AudioChunk, AudioSource


FrequencyRange = tuple[float, float]


@dataclass(frozen=True)
class FrequencyBandFeatures:
    """Features calculated for the whole track or one frequency range."""

    frequency_range_hz: FrequencyRange | None
    main_tonality: str | None
    bpm: float | None
    spectral_centroid_hz: float | None
    spectral_bandwidth_hz: float | None
    dominant_frequency_hz: float | None
    spectral_concentration: float | None
    main_beat_instant_s: float | None
    bar_beat_instants_s: tuple[float, ...]
    rms_volume: float | None
    peak_volume: float | None


@dataclass(frozen=True)
class AudioAnalysis:
    """Analysis results containing whole-track and optional band features."""

    sample_rate: int
    duration_s: float
    whole_track: FrequencyBandFeatures
    bands: Mapping[str, FrequencyBandFeatures]


class AudioAnalyzer:
    """Analyze finite or externally-stopped audio sources in one pass.

    ``analyze`` consumes the source iterator. A live source therefore remains
    active until its ``close`` method is called or its iterator ends; finite
    sources such as ``TrackAudioSource`` complete automatically.
    """

    def __init__(self, *, n_fft: int = STFT_FFT_SIZE, hop_length: int = STFT_HOP_LENGTH):
        if n_fft <= 0 or hop_length <= 0:
            raise ValueError("n_fft and hop_length must be positive")
        self.n_fft = n_fft
        self.hop_length = hop_length

    def analyze(
        self,
        source: Iterable[AudioChunk],
        *,
        frequency_range: FrequencyRange | None = None,
    ) -> AudioAnalysis:
        """Analyze a source, optionally restricted to ``(low_hz, high_hz)``."""
        return self.analyze_bands(
            source,
            {"requested": frequency_range} if frequency_range else None,
        )

    def analyze_bands(
        self,
        source: Iterable[AudioChunk],
        bands: Mapping[str, FrequencyRange] | None = None,
    ) -> AudioAnalysis:
        """Return whole-track features and features for each requested band."""
        samples: list[np.ndarray] = []
        sample_rate: int | None = None
        for chunk in source:
            if not isinstance(chunk, AudioChunk):
                raise TypeError("Audio sources must yield AudioChunk instances")
            if sample_rate is None:
                sample_rate = int(chunk.sample_rate)
            elif sample_rate != int(chunk.sample_rate):
                raise ValueError("All audio chunks must use the same sample rate")
            values = np.asarray(chunk.samples, dtype=np.float32)
            if values.ndim == 1:
                mono = values
            elif values.ndim == 2:
                mono = values.mean(axis=1)
            else:
                raise ValueError("AudioChunk.samples must be one- or two-dimensional")
            samples.append(mono)

        if not samples or sample_rate is None:
            raise ValueError("The audio source yielded no samples")
        
        waveform = np.concatenate(samples)
        duration_s = len(waveform) / sample_rate
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Processing {len(waveform):,} samples ({duration_s:.1f}s) at {sample_rate}Hz")
        
        logger.debug("Computing whole-track features...")
        whole = self._features(waveform, sample_rate, None)
        logger.debug("Computing band features...")
        result_bands = {
            name: self._features(waveform, sample_rate, band)
            for name, band in (bands or {}).items()
        }
        return AudioAnalysis(
            sample_rate=sample_rate,
            duration_s=len(waveform) / sample_rate,
            whole_track=whole,
            bands=result_bands,
        )

    def _features(
        self,
        waveform: np.ndarray,
        sample_rate: int,
        frequency_range: FrequencyRange | None,
    ) -> FrequencyBandFeatures:
        if frequency_range is not None:
            self._validate_band(frequency_range, sample_rate)
        spectrum = librosa.stft(
            waveform, n_fft=self.n_fft, hop_length=self.hop_length, center=True
        )
        frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=self.n_fft)
        mask = self._band_mask(frequencies, frequency_range)
        band_spectrum = spectrum * mask[:, None]
        band_waveform = librosa.istft(
            band_spectrum, hop_length=self.hop_length, length=len(waveform)
        )
        magnitude = np.abs(band_spectrum)
        frame_energy = magnitude.mean(axis=0)
        total_energy = float(magnitude.sum())
        if total_energy == 0.0:
            return FrequencyBandFeatures(
                frequency_range, None, None, None, None, None, 0.0,
                None, (), 0.0, 0.0
            )

        centroid = librosa.feature.spectral_centroid(
            S=magnitude, sr=sample_rate, n_fft=self.n_fft
        )[0]
        bandwidth = librosa.feature.spectral_bandwidth(
            S=magnitude, sr=sample_rate, n_fft=self.n_fft
        )[0]
        dominant_bin = int(np.argmax(magnitude.sum(axis=1)))
        dominant_frequency = float(frequencies[dominant_bin])
        concentration = float(np.sum(frame_energy**2) / (len(frame_energy) * total_energy**2))
        tonality = self._estimate_tonality(magnitude, frequencies, sample_rate)
        tempo, beat_frames = librosa.beat.beat_track(
            y=band_waveform, sr=sample_rate, hop_length=self.hop_length
        )
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sample_rate, hop_length=self.hop_length
        )
        bar_times = tuple(float(value) for value in beat_times[::4])
        rms = librosa.feature.rms(S=magnitude, frame_length=self.n_fft)[0]
        return FrequencyBandFeatures(
            frequency_range_hz=frequency_range,
            main_tonality=tonality,
            bpm=float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else None,
            spectral_centroid_hz=float(np.mean(centroid)),
            spectral_bandwidth_hz=float(np.mean(bandwidth)),
            dominant_frequency_hz=dominant_frequency,
            spectral_concentration=concentration,
            main_beat_instant_s=float(beat_times[0]) if len(beat_times) else None,
            bar_beat_instants_s=bar_times,
            rms_volume=float(np.sqrt(np.mean(band_waveform**2))),
            peak_volume=float(np.max(np.abs(band_waveform))),
        )

    @staticmethod
    def _validate_band(frequency_range: FrequencyRange, sample_rate: int) -> None:
        low, high = frequency_range
        if low < 0 or high <= low or high > sample_rate / 2:
            raise ValueError(
                f"Frequency range must satisfy 0 <= low < high <= {sample_rate / 2:g} Hz"
            )

    @staticmethod
    def _band_mask(
        frequencies: np.ndarray, frequency_range: FrequencyRange | None
    ) -> np.ndarray:
        if frequency_range is None:
            return np.ones(len(frequencies), dtype=np.float32)
        low, high = frequency_range
        return ((frequencies >= low) & (frequencies <= high)).astype(np.float32)

    @staticmethod
    def _estimate_tonality(
        magnitude: np.ndarray, frequencies: np.ndarray, sample_rate: int
    ) -> str | None:
        chroma = np.zeros((12, magnitude.shape[1]), dtype=np.float64)
        valid = frequencies > 0
        pitch_classes = np.rint(12 * np.log2(frequencies[valid] / 440.0) + 69).astype(int) % 12
        for chroma_index, pitch_class in enumerate(pitch_classes):
            chroma[pitch_class] += magnitude[valid][chroma_index]
        profile = chroma.mean(axis=1)
        if not np.any(profile):
            return None
        major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        profiles = np.vstack([np.roll(major, shift) for shift in range(12)] + [np.roll(minor, shift) for shift in range(12)])
        correlations = np.corrcoef(profiles, profile)[-1, :-1]
        best = int(np.nanargmax(correlations))
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        return f"{names[best % 12]} {'major' if best < 12 else 'minor'}"