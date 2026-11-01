# Quick start

## Install

Python 3.13 on Windows is the tested setup.

```bash
pip install -r requirements.txt
```

## Run the GUI

```bash
python -m src.gui.main_gui
```

1. Pick a device under **Audio Input**: a mixer or USB interface, Stereo Mix,
   a virtual cable, or a running application.
2. Press **▶ Start Analysis**. Band levels and onsets appear immediately; the
   first BPM and key estimates arrive after about 2.5 s and 3.5 s.
3. Tick **Enable Local API** to let other apps read the data at
   `http://127.0.0.1:8768`.

See [08 GUI guide](08_GUI_GUIDE.md) for details.

## Use the engine from Python

```python
import time
from src.engine import AudioPipeline
from src.sources import AudioInputSource

source = AudioInputSource(device=3, sample_rate=48000)  # python list_devices.py
pipeline = AudioPipeline(
    audio_source=lambda: source,
    sample_rate=48000,                                   # must match the source
    event_callback=lambda kind, data: print(kind, data), # "onset" / "beat"
).start()

last_beats = 0
try:
    while True:
        fast, medium, slow = pipeline.feature_cache.get_all()
        if fast is not None:
            if fast.beat_count != last_beats:            # a beat happened since last poll
                last_beats = fast.beat_count
                print("beat!")
            print(f"bass {medium.bass_energy:.2f}  phase {fast.beat_phase:.2f}  "
                  f"bpm {slow.estimated_bpm if slow else None}")
        time.sleep(1 / 60)
finally:
    pipeline.stop()
    pipeline.wait()
```

Things to know:

- `audio_source` is a callable returning an iterable of `AudioChunk`. It's
  called on the capture thread when the pipeline starts.
- The pipeline's `sample_rate` must equal the source's. A mismatch raises
  `ValueError` from `wait()` rather than silently mis-timing everything.
- `event_callback` runs on the real-time thread, so keep it cheap. GUI code
  must hand the work over to its own thread (the bundled GUI uses a queue
  drained by `after()`).
- Single-hop flags like `beat_detected` are easy to miss when polling; compare
  the `*_count` counters instead (see [03](03_EVENTS_AND_SIGNALS.md)).

## Analyze a file

Any iterable of `AudioChunk` works; see `examples/example.py`:

```python
import soundfile as sf
from src.engine import AudioPipeline
from src.sources import AudioChunk

def file_source(path, block=4096):
    with sf.SoundFile(path) as f:
        while len(samples := f.read(block, dtype="float32", always_2d=True)):
            yield AudioChunk(samples=samples, sample_rate=f.samplerate)

pipeline = AudioPipeline(audio_source=lambda: file_source("song.wav"),
                         sample_rate=sf.info("song.wav").samplerate).start()
pipeline.wait()   # returns when the file is analyzed and the last job results are in
print(pipeline.feature_cache.get_all()[2])  # SlowFeatures: BPM, key, dynamics
```

A file is read much faster than real time. The real-time path still analyzes
every hop in order, but the background jobs run on wall-clock intervals and
only sample the file while it's being read. When the source ends, `wait()`
runs every job once more on the final window. You always get BPM, key and
dynamics, but for the **end** of the file (the last 8 s for BPM and key).
For whole-file values, pace the source or analyze sections separately.
