# Audio Analysis GUI - User Guide

## Overview

The **Audio Analysis Monitor** is a real-time graphical interface for the audio analysis pipeline. It provides:

- 🎵 **Audio Input Selection** - Choose from available audio devices
- 🎚️ **Frequency Range Control** - Select custom min/max frequency ranges to analyze
- 📊 **Live Analysis Logging** - View analysis results and timing latency in real-time
- 🚀 **Pipeline Control** - Start/stop the streaming audio analysis pipeline
- ⚡ **Performance Monitoring** - Track chunks processed, latency, and uptime

---

## Features

### 1. Audio Input Selection

The GUI automatically discovers and lists all available audio input devices on your system.

**Available device types:**
- **Input**: Microphone, line-in, or USB audio devices
- **Loopback**: Stereo Mix (Windows) or similar system audio capture

**How to select:**
1. Click the dropdown menu under "Audio Input"
2. Choose your desired device
3. Device info (channels, sample rate, type) appears automatically
4. Click 🔄 **Refresh** to re-scan for devices

**Example devices:**
```
Microphone (input, 2ch, 44100Hz)
Stereo Mix (loopback, 2ch, 44100Hz)
USB Audio Device (input, 2ch, 48000Hz)
```

---

### 2. Frequency Range Control

Select custom frequency ranges for analysis. The GUI provides two sliders for min/max values.

**How to use:**
1. Adjust the **Min (Hz)** slider to set lower frequency bound
2. Adjust the **Max (Hz)** slider to set upper frequency bound
3. The range updates in real-time and shows current values
4. Constraints:
   - Min must be < Max (automatically enforced)
   - Min range: 20 Hz (sub-bass)
   - Max range: 20,000 Hz (ultra-high)

**Common frequency ranges:**
| Range | Frequencies | Use Case |
|-------|-------------|----------|
| Bass | 20-250 Hz | Kick detection, sub-bass |
| Mid | 250-4000 Hz | Vocals, guitars, presence |
| High | 4000-20000 Hz | Sibilance, air, brightness |
| Full | 20-20000 Hz | Complete audio spectrum |
| Treble | 6000-20000 Hz | High-frequency content |

**Example:**
```
Min (Hz):  [████░░░░░░] 150 Hz
Max (Hz):  [██████████] 5000 Hz
Range: 150 - 5000 Hz
```

---

### 3. Analysis Results & Latency Log

The large text area displays real-time analysis results as they're processed by the pipeline.

**Columns:**
- **Time**: HH:MM:SS.milliseconds
- **Operation**: Name of analysis operation (e.g., "STFT", "Beat Detection")
- **Value**: The analyzed result value (0-1 normalized)
- **Latency**: Time taken in milliseconds (color-coded)
- **Frequency Range**: Which frequency band was analyzed

**Color Coding:**
- 🟢 **Green** (0-15ms): Fast, good performance
- 🟡 **Amber** (15-30ms): Acceptable, typical performance
- 🔴 **Red** (>30ms): Slow, potential bottleneck

**Example log output:**
```
Time             | Operation                      | Value      | Latency  | Frequency Range
─────────────────────────────────────────────────────────────────────────────────
[14:23:15.234]   | Device Changed                 |      0.0000 |    0.00ms | --
[14:23:15.312]   | Pipeline Started               |      1.0000 |    0.00ms | --
[14:23:15.402]   | extract_amplitude              |      0.4521 |   12.34ms | all
[14:23:15.523]   | extract_stft                   |      0.6789 |   24.56ms | bass
[14:23:15.645]   | beat_detection                 |      0.8921 |    8.92ms | all
>>> EVENT: beat_detected | {'timestamp': 0.234, 'confidence': 0.95}
[14:23:15.768]   | spectral_centroid              |      2345.2 |    3.45ms | mid
```

**Log Controls:**
- **Clear Log**: Delete all entries (resets display, keeps current analysis running)
- **Pause**: Pause/Resume logging to examine results without new updates

---

### 4. Pipeline Control

Start and stop the real-time audio analysis pipeline.

**Status Indicator:**
- 🟢 **Running** (green): Pipeline is actively processing audio
- 🟠 **Idle** (amber): Pipeline is stopped, ready to start

**Start Analysis:**
1. Select an audio input device
2. (Optional) Set custom frequency range
3. Click **▶ Start Analysis**
4. Audio processing begins immediately
5. Results appear in the log area
6. **Start** button disables, **Stop** button enables

**Stop Analysis:**
1. Click **⏹ Stop Analysis**
2. Pipeline processes remaining audio and stops
3. Final performance summary appears in log
4. **Start** button enables, **Stop** button disables

---

### 5. Performance Monitoring

The **Performance** section shows real-time pipeline metrics.

**Metrics:**
- **Chunks Processed**: Total audio chunks analyzed
- **Avg Latency**: Average time per chunk (milliseconds)
- **Uptime**: How long pipeline has been running (seconds)

**Example:**
```
Chunks Processed: 352
Avg Latency: 24.5ms
Uptime: 30.2s
```

**Interpretation:**
- **Low latency** (<25ms): Good real-time performance
- **High latency** (>50ms): Potential CPU bottleneck
- **Chunks increase**: Pipeline is actively processing

---

## Workflow Examples

### Example 1: Monitor Microphone Input

**Goal**: Real-time analysis of microphone audio

1. **Select Device**: Choose your microphone from dropdown
   - Shows: "Microphone (input, 2ch, 44100Hz)"
2. **Set Frequency Range**: Keep full range (20Hz - 20kHz)
3. **Start Analysis**: Click ▶ Start Analysis
4. **Watch Results**: Log shows beat detection, onset events in real-time
5. **Stop**: Click ⏹ Stop Analysis when done

---

### Example 2: Analyze System Audio (Stereo Mix)

**Goal**: Analyze music playing through speakers/headphones

1. **Select Device**: Choose "Stereo Mix (loopback, 2ch, 44100Hz)"
   - Windows: Stereo Mix or Loopback
   - Mac/Linux: Loopback device or similar
2. **Custom Range**: Adjust to bass range (20-250Hz) for kick detection
3. **Start Analysis**: Click ▶ Start Analysis
4. **Play Music**: Start music in another app
5. **Monitor**: Watch bass energy in real-time log
6. **Stop**: Click ⏹ Stop Analysis

**Expected in log:**
```
[14:25:32.123]   | extract_energy (bass)          |      0.8534 |   15.23ms | bass
[14:25:32.234]   | beat_detection (bass)          |      0.9123 |    8.45ms | bass
>>> EVENT: beat_detected | {'confidence': 0.92}
```

---

### Example 3: Frequency Analysis Comparison

**Goal**: Compare energy across different frequency ranges

**Run 1 - Bass Analysis:**
1. Set range: 20-250 Hz
2. Start analysis, play music
3. Note typical bass energy values
4. Stop

**Run 2 - Mid Analysis:**
1. Set range: 250-4000 Hz
2. Start analysis, play same music
3. Compare mid-range values to bass
4. Stop

**Run 3 - Treble Analysis:**
1. Set range: 6000-20000 Hz
2. Start analysis, play same music
3. Compare treble values
4. Stop

**Result**: You can see which frequency range is dominant in the audio.

---

## Troubleshooting

### No Audio Devices Showing
**Problem**: Dropdown is empty or only shows one generic device

**Solution**:
1. Install `sounddevice` Python package:
   ```bash
   pip install sounddevice
   ```
2. Click 🔄 **Refresh** to re-scan
3. On Windows, enable Stereo Mix:
   - Right-click speaker icon → Sound settings
   - Recording devices → Enable "Stereo Mix"

### GUI Freezes When Starting
**Problem**: Click ▶ Start Analysis but GUI becomes unresponsive

**Solution**:
- Audio device is unavailable or disconnected
- Check that device is still connected
- Try selecting a different device
- Click **Refresh** to update device list

### No Results in Log
**Problem**: Started pipeline but no analysis results appear

**Solutions**:
1. Check audio is playing/sound is available
   - For microphone: speak/make noise
   - For loopback: start playing music elsewhere
2. Check Pause button isn't active
   - If log shows "Resume", click to resume logging
3. Check frequency range is reasonable
   - Min should be much less than Max
4. Try clicking Stop then Start again

### High Latency (>50ms)
**Problem**: Latency column shows values above 50ms

**Causes & Solutions**:
1. **CPU overloaded**: Close other apps, reduce NUM_PROCESSING_WORKERS
2. **Slow disk**: Audio analysis depends on CPU, not disk, but could indicate system strain
3. **Complex analysis**: Large FFT sizes cause slower STFT
   - Reduce STFT_FFT_SIZE in config
4. **Buffer full**: Too many chunks queued
   - Increase OUTPUT_QUEUE_MAXSIZE or reduce AUDIO_CHUNK_SIZE

---

## Configuration

### Environment Variables

Customize pipeline behavior via environment variables:

```powershell
# Windows PowerShell
$env:MOSHPRO_SAMPLE_RATE=48000
$env:MOSHPRO_CHUNK_SIZE=4096
python -m src.gui.main_gui
```

**Common variables:**
```
MOSHPRO_SAMPLE_RATE=44100        # Audio sample rate (Hz)
MOSHPRO_CHUNK_SIZE=2048          # Samples per chunk (lower = lower latency)
MOSHPRO_BUFFER_CAPACITY_SECONDS=5.0
MOSHPRO_NUM_PROCESSING_WORKERS=4 # Parallel processing workers
MOSHPRO_STFT_FFT_SIZE=2048       # FFT size (larger = more frequency resolution)
```

### Configuration File

Edit `src/config/settings.py` for permanent changes:

```python
DEFAULT_SAMPLE_RATE: Final[int] = 44100
AUDIO_CHUNK_SIZE: Final[int] = 2048
NUM_PROCESSING_WORKERS: Final[int] = 4
```

---

## Performance Tips

### For Real-Time Performance (Low Latency)

1. **Reduce chunk size**:
   ```
   MOSHPRO_CHUNK_SIZE=1024  # Smaller chunks = lower latency
   ```

2. **Reduce FFT size**:
   ```
   MOSHPRO_STFT_FFT_SIZE=512  # Trades frequency resolution for speed
   ```

3. **Increase workers**:
   ```
   MOSHPRO_NUM_PROCESSING_WORKERS=8  # More parallel processing
   ```

4. **Close other apps** to free up CPU

### For Better Frequency Resolution (Higher Quality)

1. **Increase FFT size**:
   ```
   MOSHPRO_STFT_FFT_SIZE=4096  # More detailed frequency info
   ```

2. **Increase chunk size**:
   ```
   MOSHPRO_CHUNK_SIZE=4096  # More samples per chunk
   ```

3. **Increase buffer**:
   ```
   MOSHPRO_BUFFER_CAPACITY_SECONDS=10.0  # Longer history
   ```

---

## Keyboard Shortcuts

Coming in future version - Use GUI buttons for now.

---

## File Structure

```
src/gui/
├── main_gui.py           # Main application window
├── audio_devices.py      # Audio device management
├── analysis_logger.py    # Analysis results display
├── theme.py              # Dark theme definitions
└── __init__.py           # Package exports
```

---

## Starting the GUI

### Via VS Code Launch Config

1. Press `F5` or go to Run → Start Debugging
2. Select "GUI: Audio Analysis Monitor"
3. GUI window opens

### Via Command Line

```bash
python src/gui/main_gui.py
```

### Via Python Script

```python
from src.gui import launch_gui

launch_gui()  # Blocks until window is closed
```

---

## API Integration

Use the GUI components in your own code:

```python
from src.gui import AudioAnalysisGUI, AnalysisLogger

# Direct GUI access
app = AudioAnalysisGUI()
app.mainloop()

# Use analysis logger independently
logger = AnalysisLogger(parent_widget)
logger.log_result(
    operation="Custom Analysis",
    value=0.75,
    latency_ms=12.3,
    frequency_range="custom"
)
```

---

## Support

For issues or feature requests:
1. Check Troubleshooting section above
2. Review log output for error messages
3. Check console for Python exceptions
4. Verify all audio devices are working (test with system audio first)

---

## Version

Audio Analysis Monitor v1.0
- Real-time pipeline integration
- Custom frequency ranges
- Performance monitoring
- Dark theme UI
- Multi-device support
