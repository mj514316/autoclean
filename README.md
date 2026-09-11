# autoclean

Real-time local profanity censor for all PC audio. Free, offline, low latency.

```
audio in ──► ring buffer (delay ~0.6s) ──► audio out
                │                              ▲
                └──► sherpa-onnx streaming ASR ┘
                     flags banned words while they
                     are still buffered → 1kHz beep
                     spliced in before playback
```

## Run (Mac dev)

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python configurator.py    # GUI: devices, offsets, start/stop
.venv/bin/python autoclean.py       # or headless CLI
```

Note: macOS 15 needs a Homebrew python (system python3's Tk is broken):
`brew install python@3.12 python-tk@3.12`.

Offline test (no audio hardware needed):

```sh
python autoclean.py --simulate phase0/test.wav --out out.wav
```

For system-wide audio on Mac, install BlackHole (`brew install blackhole-2ch`),
create a Multi-Output Device in Audio MIDI Setup, and pass `--input-device`.

## Run / build (Windows target)

1. Install VB-CABLE (vb-audio.com/Cable — free).
2. Windows Sound settings → output device = **CABLE Input**.
3. `build_windows.bat` — downloads the ASR model, creates the venv, builds
   `dist\AutoClean\AutoClean.exe` (the configurator GUI, PyInstaller onedir).
4. In the app: input device = **CABLE Output**, output = real
   speakers/headphones. Save settings once; they persist in `autoclean.json`.

## Tuning (all exposed in the configurator)

- **Audio delay**: how far audio lags video. Lower bound = ASR detection lag
  (~0.3–0.5s). 0.6–0.8 is a good start; `MISSED` in the log means raise it.
- **Timing offset**: shifts mute windows earlier — streaming ASR emits token
  timestamps ~150–300ms late. Tune until a flagged word is fully muted without
  clipping neighbors.
- **Pad**: extra mute before each flagged word.
- `words.txt`: banned word list, one per line, `#` comments. Edit from the GUI.
- Replace mode: silence or beep.

## Model

`phase0/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17` (20M params, int8,
~50x realtime on a single CPU core). Larger sherpa-onnx streaming models are a
drop-in upgrade via `--model-dir` if accuracy needs improving.

## Status

Working prototype. Validated: sim beeps "damn" with 0.26–0.86s headroom across
delays 0.4–1.0s. Remaining: live-device soak test, Windows run, phrase/topic
detection (Phase 4), tray packaging (Phase 5).
