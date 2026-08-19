"""Example: Audio Rendering Format Output

This example demonstrates exactly what the rendering thread produces.
"""

from dataclasses import dataclass


@dataclass
class RenderingFormatExample:
    """Example showing the rendering message format at different moments."""

    @staticmethod
    def example_quiet_moment():
        """Output during quiet moment in music."""
        return {
            "timestamp_s": 12.345,
            "bass": 0.12,           # Little bass energy
            "energy": 0.18,         # Low overall energy
            "brightness": 0.45,     # Mid-range brightness
            "impact": 0.08,         # Very low peak
            "beat": False,          # No beat
            "beat_confidence": 0.0,
            "onset": False,
            "tempo_bpm": 120.0,
            "dynamics": 0.95,       # High dynamics (quiet, no compression)
        }

    @staticmethod
    def example_beat_moment():
        """Output when drum kick happens (beat detected)."""
        return {
            "timestamp_s": 13.567,
            "bass": 0.92,           # STRONG bass energy (kick drum)
            "energy": 0.76,         # High overall energy
            "brightness": 0.35,     # Darker (sub-bass dominant)
            "impact": 0.88,         # Strong peak amplitude
            "beat": True,           # ♪ BEAT DETECTED
            "beat_confidence": 0.94,  # Very confident
            "onset": False,         # Gradual (not percussive onset)
            "tempo_bpm": 120.0,
            "dynamics": 0.72,       # Medium dynamics
        }

    @staticmethod
    def example_percussion_onset():
        """Output when cymbal or snare strikes (onset detected)."""
        return {
            "timestamp_s": 14.123,
            "bass": 0.25,           # Minimal bass
            "energy": 0.82,         # High energy from cymbals
            "brightness": 0.92,     # VERY bright (high frequencies)
            "impact": 0.95,         # Peak is high
            "beat": False,          # No beat, just attack
            "beat_confidence": 0.0,
            "onset": True,          # ▲ ONSET DETECTED (rapid attack)
            "tempo_bpm": 120.0,
            "dynamics": 0.15,       # Very low dynamics (sharp peak)
        }

    @staticmethod
    def example_melody_moment():
        """Output during melodic/vocal moment."""
        return {
            "timestamp_s": 15.789,
            "bass": 0.35,           # Supporting bass
            "energy": 0.64,         # Moderate energy
            "brightness": 0.68,     # Presence (vocal/midrange)
            "impact": 0.42,         # Moderate peaks
            "beat": False,
            "beat_confidence": 0.1,
            "onset": False,
            "tempo_bpm": 120.0,
            "dynamics": 0.80,       # High dynamics (singing variation)
        }

    @staticmethod
    def example_dense_chorus():
        """Output during dense/compressed section."""
        return {
            "timestamp_s": 17.234,
            "bass": 0.85,           # Strong bass
            "energy": 0.91,         # Very high energy
            "brightness": 0.75,     # Bright but not extreme
            "impact": 0.72,         # Constant high level
            "beat": True,           # Tight beat
            "beat_confidence": 0.82,
            "onset": False,
            "tempo_bpm": 120.0,
            "dynamics": 0.45,       # Low dynamics (heavy compression)
        }


def print_rendering_examples():
    """Print all rendering format examples."""
    examples = [
        ("Quiet Moment", RenderingFormatExample.example_quiet_moment()),
        ("Beat (Drum Kick)", RenderingFormatExample.example_beat_moment()),
        ("Percussion Onset (Cymbal/Snare)", RenderingFormatExample.example_percussion_onset()),
        ("Melody Moment (Vocal)", RenderingFormatExample.example_melody_moment()),
        ("Dense Chorus", RenderingFormatExample.example_dense_chorus()),
    ]

    print("\n" + "=" * 100)
    print("AUDIO RENDERING FORMAT EXAMPLES")
    print("=" * 100)

    for name, example in examples:
        print(f"\n{name}:")
        print("-" * 100)
        for key, value in example.items():
            if isinstance(value, bool):
                icon = "✓" if value else "✗"
                print(f"  {key:<20} = {icon} {value!s:<10}")
            elif isinstance(value, float):
                if key == "tempo_bpm":
                    print(f"  {key:<20} = {value:>6.1f} BPM")
                else:
                    # Visual bar for numeric values 0-1
                    bar_length = int(value * 20)
                    bar = "█" * bar_length + "░" * (20 - bar_length)
                    print(f"  {key:<20} = {value:.2f} [{bar}]")
            else:
                print(f"  {key:<20} = {value}")

    print("\n" + "=" * 100)
    print("INTEGRATION PATTERNS")
    print("=" * 100)

    print("\n1. Game Engine (Check beat and energy):")
    print("   if render_msg.beat:")
    print("       game.trigger_animation('beat')")
    print("       particle.intensity = render_msg.energy * 2.0")

    print("\n2. Shader Parameters (All values 0-1, ready for GPU):")
    print("   shader.uniform('u_bass', render_msg.bass)")
    print("   shader.uniform('u_brightness', render_msg.brightness)")
    print("   shader.uniform('u_impact', render_msg.impact)")

    print("\n3. Audio Effects (Sidechain compression):")
    print("   compressor.threshold = -40 + (render_msg.impact * 10)  # DB")
    print("   reverb.wet = 0.3 + render_msg.brightness * 0.4")

    print("\n4. Network (Stream to clients):")
    print("   osc_send('/audio', [render_msg.bass, render_msg.energy, render_msg.beat])")

    print("\n5. UI Visualization:")
    print("   ui.bass_meter.value = render_msg.bass")
    print("   ui.energy_bar.width = render_msg.energy * 500")
    print("   if render_msg.onset:")
    print("       ui.flash_screen(0.2)  # 200ms flash")

    print("\n" + "=" * 100 + "\n")


if __name__ == "__main__":
    print_rendering_examples()
