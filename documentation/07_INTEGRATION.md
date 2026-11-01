# Integration

## Option 1: the local API (any language, any process)

Enable it in the GUI, or start it in code:

```python
from src.api import AnalysisAPIServer
server = AnalysisAPIServer(pipeline.feature_cache)  # 127.0.0.1:8768
server.start()
```

### OBS browser source / web page (WebSocket)

```html
<canvas id="c" width="800" height="450"></canvas>
<script>
const ctx = document.getElementById("c").getContext("2d");
let data = null, lastBeatCount = 0, flash = 0;

function connect() {
  const ws = new WebSocket("ws://127.0.0.1:8768/ws");
  ws.onmessage = (msg) => {
    data = JSON.parse(msg.data);
    const fast = data.fast;
    if (!fast) return;
    // Schedule the flash for the predicted beat instead of reacting late
    if (fast.predicted_next_beat_unix_s && fast.beat_confidence > 0.5) {
      const delayMs = fast.predicted_next_beat_unix_s * 1000 - Date.now();
      if (delayMs > 0 && delayMs < 1000) scheduleBeat(fast.predicted_next_beat_unix_s);
    } else if (fast.beat_count !== lastBeatCount) {
      flash = 1;  // fallback: react to the counter
    }
    lastBeatCount = fast.beat_count;
  };
  ws.onclose = () => setTimeout(connect, 1000);  // survive restarts
}

let scheduled = 0;
function scheduleBeat(t) {
  if (t === scheduled) return;  // one timer per beat
  scheduled = t;
  setTimeout(() => { flash = 1; }, t * 1000 - Date.now());
}

function draw() {
  const bass = data?.medium?.bass_energy ?? 0;
  ctx.fillStyle = `rgba(0,0,0,0.25)`;
  ctx.fillRect(0, 0, 800, 450);
  ctx.fillStyle = `hsl(${200 + 120 * bass}, 90%, ${30 + 50 * flash}%)`;
  const r = 60 + 120 * bass;
  ctx.beginPath(); ctx.arc(400, 225, r, 0, 2 * Math.PI); ctx.fill();
  flash *= 0.85;
  requestAnimationFrame(draw);
}
connect(); draw();
</script>
```

In OBS, add a **Browser** source pointing at the local HTML file.
`Date.now()` and `predicted_next_beat_unix_s` share the machine's clock.

### Polling (HTTP)

```bash
curl http://127.0.0.1:8768/features/bpm
```

```python
import json, time, urllib.request
last = 0
while True:
    with urllib.request.urlopen("http://127.0.0.1:8768/features/fast", timeout=1) as resp:
        fast = json.load(resp)
    if fast and fast["beat_count"] != last:
        last = fast["beat_count"]
        print("beat", fast["tempo_bpm"])
    time.sleep(0.02)
```

### Python WebSocket client

```python
import asyncio, json, aiohttp

async def main():
    async with aiohttp.ClientSession() as s, s.ws_connect("http://127.0.0.1:8768/ws") as ws:
        async for msg in ws:
            data = json.loads(msg.data)
            slow = data["slow"]
            if slow:
                print(slow["estimated_bpm"], slow["detected_key"])

asyncio.run(main())
```

## Option 2: in process (Python)

Run the pipeline yourself and read `pipeline.feature_cache` from your render
loop (see [01 Quick start](01_QUICK_START.md)). For events, use
`event_callback`. It runs on the real-time thread, so hand the work to your
loop through a queue:

```python
import queue
events = queue.SimpleQueue()
pipeline = AudioPipeline(..., event_callback=lambda kind, data: events.put((kind, data)))

# in your render loop:
while not events.empty():
    kind, data = events.get_nowait()
```

### Tkinter, Qt and other GUI toolkits

Never touch widgets from the callback. Put events in a queue and drain it
from the toolkit's own timer (`after()` in Tk, `QTimer` in Qt). The bundled
GUI does exactly that.

## Picking an input

| Situation | Device |
|---|---|
| DJ mixer / audio interface | its input (`AudioInputSource`) |
| Music playing on this PC | Stereo Mix / "What U Hear", or route the player to a virtual cable and pick the cable's output |
| One specific app | the GUI's application entry (note: it captures system loopback, not the app alone) |
| Rekordbox | `TrackAudioSource` with the DataBridge submodule (file-based) |
