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

1. Install Python 3.12+ from python.org (tick **"Add python to PATH"**).
2. Clone this repo: `git clone https://github.com/mj514316/autoclean`
3. Run `build_windows.bat` — downloads the ASR model, creates a venv, and
   builds `dist\AutoClean\AutoClean.exe` (the configurator GUI).
4. Install **VB-CABLE** (vb-audio.com/Cable — free driver, no reboot needed).
5. Windows Sound settings → output device = **CABLE Input**
   (all PC audio now flows through the virtual cable).
6. Launch AutoClean: input device = **CABLE Output**, output = real
   speakers/headphones → **Start** → **Save settings**.

To auto-start at login: put a shortcut to `AutoClean.exe` in `shell:startup`.
To bypass: switch the Windows output device back to real speakers.

## Tuning (all exposed in the configurator)

- **Audio delay**: how far audio lags video. Lower bound = ASR detection lag
  (~0.3–0.5s). 0.6–0.8 is a good start; `MISSED` in the log means raise it.
- **Timing offset**: shifts mute windows earlier — streaming ASR emits token
  timestamps ~150–300ms late. Tune until a flagged word is fully muted without
  clipping neighbors.
- **Pad**: extra mute before each flagged word.
- **Word lists**: checkboxes in the GUI select any combination of lists in
  `wordlists/`, plus an optional custom list (`words.txt`). One word per
  line, `#` comments. **List content never lives in the repo** — the dir is
  gitignored; bootstrap defaults with `./fetch_lists.sh` (pulls the public
  LDNOOBW list) or copy your own `wordlists/*.txt|*.dat` in. Lists are
  stored locally as obfuscated `.dat` blobs (`pack_lists.py` repacks from
  `.txt` sources) — obfuscation, not encryption.
- **Test word(s)**: decoy words censored at runtime for tuning without
  profanity; never written to any list.
- Replace mode: silence or beep.

## Model

`model/` = sherpa-onnx streaming zipformer English, 20M params, int8
(~50x realtime on a single CPU core; downloaded by `fetch_model.sh` /
`build_windows.bat`, not committed). Larger sherpa-onnx streaming models are a
drop-in upgrade via `--model-dir` if accuracy needs improving.

## Status

Working prototype, validated live on macOS (mic → headphones, real-voice
detection with mutes landing on target words at 0.8s delay). Remaining:
Windows end-to-end run, phrase/topic detection, tray icon / auto-start
polish.
