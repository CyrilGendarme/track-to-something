# Performance Monitoring Guide

This guide explains how to use the performance monitoring system to identify bottlenecks and delays in the audio processing pipeline.

## Overview

The performance monitoring system tracks timing for every important operation in the pipeline and logs:
- **Average latency** (ms)
- **Min/Max latency** (ms)  
- **Operation count**
- **Slow operations** (>30ms logged in real-time to console)
- **Periodic summaries** organized by slowest operations

## Quick Start

### Enable Basic Monitoring

The performance monitor is **automatically enabled** when you run the pipeline. It tracks:

```
✓ capture:buffer_write       - Time to write audio to circular buffer
✓ capture:queue_put          - Time to put message in capture queue
✓ process:amplitude_metrics  - Overall loudness calculation
✓ process:stft               - Spectral analysis (STFT)
✓ process:spectral_features  - Centroid, dominant frequency
✓ process:frequency_bands    - Bass/mid/high energy extraction
✓ process:beat_detection     - Beat confidence calculation
✓ process:onset_detection    - Attack/transient detection  
✓ process:tempo_estimation   - BPM calculation
✓ process:band_envelopes     - Frequency band visualization data
✓ process:queue_put          - Time to put features message
✓ analysis:beat_detection    - Beat event detection
✓ analysis:onset_detection   - Onset event detection
✓ analysis:transient_detection - Transient event detection
✓ analysis:beat_prediction   - Predictive beat calculation
✓ analysis:render_message_creation - Rendering message assembly
✓ analysis:queue_put         - Time to put rendering message
✓ buffer:write               - Circular buffer write operation
✓ buffer:read_latest         - Reading latest audio samples
✓ render:logging             - Display/console output
```

### View Performance Report

```python
from src.engine import get_performance_monitor

# ... run your audio pipeline ...

perf = get_performance_monitor()
perf.log_summary(limit=10)  # Show top 10 slowest operations
```

### Console Output Examples

#### Real-Time Slow Operation Warnings
```
WARNING [SLOW] process:stft: 45.23ms
WARNING [SLOW] process:onset_detection: 32.51ms
```

These are logged whenever an operation exceeds 30ms, helping you spot slowdowns immediately.

#### Periodic Summary Log
```
======================================================================
[PERFORMANCE SUMMARY]
======================================================================
 1. process:stft                 | avg=22.45ms | min=15.32ms | max=48.93ms | n=1523
 2. process:onset_detection      | avg=8.34ms  | min=5.12ms  | max=15.67ms | n=1523
 3. process:frequency_bands      | avg=6.78ms  | min=4.21ms  | max=12.45ms | n=1523
 4. process:beat_detection       | avg=5.23ms  | min=3.15ms  | max=9.87ms  | n=1523
 5. processing_worker_total      | avg=48.12ms | min=42.15ms | max=156.34ms| n=1523
... and 15 more operations
======================================================================
```

### Advanced Analysis

Use the monitoring utility for deeper insights:

```python
from src.engine.monitoring import show_bottleneck_insights, get_bottleneck_analysis

# Show detailed bottleneck report with recommendations
show_bottleneck_insights()

# Get analysis as dictionary for programmatic use
analysis = get_bottleneck_analysis()
for op in analysis["operations_above_30ms"]:
    print(f"Bottleneck: {op['name']} - {op['avg_ms']}ms average")
```

### Programmatic Access

```python
from src.engine import get_performance_monitor

perf = get_performance_monitor()

# Get stats for specific operation
stft_stats = perf.get_stats("process:stft")
if stft_stats:
    print(f"STFT: {stft_stats.avg_ms:.2f}ms avg, {stft_stats.max_ms:.2f}ms max")

# Get all operations as dict
all_ops = perf.stats  # dict[str, TimingStats]

# Reset statistics
perf.reset()

# Disable monitoring (reduces overhead)
perf.disable()
perf.enable()

# Check if enabled
if perf.enabled:
    print("Performance monitoring is active")
```

## Performance Targets

### Expected Latencies (Baseline)
These are approximate values on a modern machine:

| Operation | Target | Notes |
|-----------|--------|-------|
| capture:buffer_write | <1ms | Simple array copy |
| process:stft | 15-30ms | Most expensive operation |
| process:onset_detection | 5-15ms | Librosa computation |
| process:frequency_bands | 5-10ms | NumPy operations |
| process:beat_detection | 3-8ms | Energy threshold check |
| analysis:beat_detection | <1ms | Simple comparison |
| buffer:write | <1ms | Lock + array write |
| buffer:read_latest | 2-5ms | Copy with potential wrap |

### Total Pipeline Latency

**Full processing latency per chunk:**
- Input → Output: ~80-120ms under normal load
- Capture: 1ms
- Processing (4 workers avg): 50-60ms  
- Analysis: 8-12ms
- Rendering: <1ms

## Identifying Bottlenecks

### Common Issues and Solutions

#### 1. **STFT is Slow (>40ms)**
**Symptoms:** `process:stft` consistently above 40ms

**Causes:**
- Large FFT size (STFT_FFT_SIZE in config)
- Hop length too small (creates more frames)
- Synchronous librosa call blocking thread

**Solutions:**
```python
# In src/config/settings.py, try:
STFT_FFT_SIZE = 1024  # Reduce from 2048
STFT_HOP_LENGTH = 256  # Reduce from 512
```

#### 2. **Onset Detection is Slow (>15ms)**
**Symptoms:** `process:onset_detection` spike

**Causes:**
- `librosa.onset.onset_strength()` is expensive for long signals
- Recomputing same signal multiple times

**Solutions:**
```python
# Cache onset envelope if it's called repeatedly
# Move to separate worker thread if possible
```

#### 3. **Queue Operations Slow (>5ms)**
**Symptoms:** `*:queue_put` operations exceed 5ms

**Causes:**
- Queue is full (blocking on put)
- System under memory pressure
- Garbage collection pause

**Solutions:**
```python
# In src/config/settings.py
OUTPUT_QUEUE_MAXSIZE = 20  # Increase from 10
NUM_PROCESSING_WORKERS = 6  # Add more parallel workers
```

#### 4. **Entire Processing Worker Slow (>100ms)**
**Symptoms:** Periodic spikes in processing time

**Causes:**
- Garbage collection
- Other system processes
- Lock contention

**Solutions:**
```python
# Enable real-time priority on Windows:
import os
os.nice(-10)  # Increase process priority (Linux)

# Or configure threading:
NUM_PROCESSING_WORKERS = 2  # Reduce contention
```

## Example: Complete Monitoring Script

```python
#!/usr/bin/env python3
"""Monitor audio pipeline performance."""

import logging
from pathlib import Path
import sys

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.engine import AudioPipeline, get_performance_monitor
from src.sources import LiveAudioInput
from src.engine.monitoring import show_bottleneck_insights

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

def main():
    # Create pipeline
    perf = get_performance_monitor()
    
    # Run for limited time
    print("Starting performance monitoring...")
    print("Recording for 10 seconds...\n")
    
    pipeline = AudioPipeline(
        audio_source=LiveAudioInput(duration_s=10.0),
        n_processing_workers=4,
    )
    
    pipeline.start()
    pipeline.wait()
    
    # Analyze results
    print("\n" + "=" * 70)
    show_bottleneck_insights()
    
    # Also show full summary
    perf.log_summary(limit=20)

if __name__ == "__main__":
    main()
```

Run it:
```bash
python performance_monitor.py
```

## Configuration Constants

### Performance-Related Config (src/config/settings.py)

```python
# Audio processing
STFT_FFT_SIZE = 2048              # Increase for frequency resolution, decrease for speed
STFT_HOP_LENGTH = 512             # Decrease for more frequent updates
STFT_WINDOW = "hann"              # Window function

# Threading
NUM_PROCESSING_WORKERS = 4        # More workers = better parallelism
OUTPUT_QUEUE_MAXSIZE = 10         # Increase if queue_put blocks

# Analysis windows
FAST_WINDOW_MS = 10.0             # Decrease for faster response
MEDIUM_WINDOW_MS = 32.0           # Balance latency vs. smoothness
SLOW_WINDOW_MS = 250.0            # Longer = more stable stats
```

## Performance Tips

### 1. **Baseline Measurement**
Always measure before optimizing:
```python
perf = get_performance_monitor()
perf.reset()
# ... run pipeline ...
perf.log_summary()
```

### 2. **Monitor Specific Operations**
```python
# Check if a specific operation is the bottleneck
stft_stats = perf.get_stats("process:stft")
if stft_stats and stft_stats.avg_ms > 25:
    print("STFT is likely bottleneck")
```

### 3. **Use Conditional Logging**
For production, disable performance logging:
```python
from src.engine import get_performance_monitor

perf = get_performance_monitor()
perf.disable()  # Reduce overhead
```

### 4. **Profile with Python Profiler**
For detailed analysis, use cProfile:
```bash
python -m cProfile -s cumtime -m pytest tests/test_performance.py
```

## Troubleshooting

### "No performance data available"
**Cause:** Pipeline hasn't run yet or was very short
**Solution:** Run the pipeline for at least a few seconds

### Performance reports show inconsistent values
**Cause:** First run includes cold cache and initialization overhead
**Solution:** Run multiple times, ignore first ~1-2 seconds of data

### Very high max_ms but low avg_ms
**Cause:** Occasional GC pauses or context switches
**Solution:** This is normal; focus on average latency

## See Also

- [Config Guide](../../config/README.md) - Configuration tuning
- [Architecture Guide](../README.md) - Pipeline design
- [Profiling Guide](../../profiling.md) - CPU/memory profiling
