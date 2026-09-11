# Phase 0 — Existing-Software Evaluation

Goal: censor profanity in all PC audio for a kid playing Minecraft. Free, local,
lowest-possible latency. Windows target; Mac dev machine.

## Candidates evaluated (2026-09-10)

| Candidate | Type | English | Latency design | Verdict |
|---|---|---|---|---|
| **locaal-ai/obs-cleanstream** v0.2.0 | OBS plugin (whisper.cpp + silero VAD) | Yes | Adaptive delay (~1s typical), regex word list, beep/silence/custom sound, CPU/CUDA/ROCm builds | **Primary candidate — test first** |
| **Cloud370/obs-profanity-filter** v0.3.0-beta | OBS plugin (sherpa-onnx streaming) | Partial: bilingual zh-en streaming model (357MB); UI is Chinese-only | Delay-and-backtrack, **300–500ms claimed** — best architecture | Test second if cleanstream too slow; tolerable one-time Chinese config |
| **ColeBianchi/realtime-audio-censorship** | Standalone Python | Yes | **~60s delay by design** (30s chunks + 2x buffer) | Reference code only — unusable latency |
| ~~Sylos-Creator/Audio-Censoring-Tool~~ | — | — | — | Repo is 404 (gone/private). Skip |

## Local smoke test result (Mac, CPU-only)

sherpa-onnx streaming zipformer English 20M int8:
- **RTF 0.021** — ~50x realtime on one CPU core. GPU not required.
- Correctly detected "damn" in synthetic speech, with **token-level timestamps**.
- Conclusion: the low-latency architecture is viable even on modest hardware.

## Recommended test order on the Windows PC

### Test 1 — obs-cleanstream (15 min)

1. Install OBS Studio (obsproject.com) — version 32+.
2. Install `obs-cleanstream-0.2.0-windows-x64-nvidia-Installer.exe`
   (or `-generic-` if no NVIDIA GPU).
3. Install **VB-CABLE** (vb-audio.com/Cable, free). Reboot not required but
   restart audio apps after.
4. Windows Settings → Sound → set **output device = "CABLE Input"**.
   All PC audio now flows into the cable.
5. In OBS: add source **Audio Input Capture** → device = **"CABLE Output"**.
6. Right-click source → **Filters** → + → **CleanStream**:
   - Language: English; Model: start with `tiny`/`base` (bigger = more accurate,
     slower)
   - Detection regex, e.g.: `(damn|hell|shit|fuck|crap|bitch|ass)`
   - Replace sound: **Beep**
7. OBS → Settings → Audio → Advanced → **Monitoring Device = real
   headphones/speakers**.
8. Edit → Advanced Audio Properties → set the source's **Audio Monitoring =
   "Monitor and Output"**.
9. Play a YouTube clip / voice line containing a flagged word. Listen for beep.

**Pass criteria**
- Flagged words reliably beeped; normal speech untouched.
- A/V delay ≤ ~1.5s and tolerable during gameplay.
- CPU/GPU overhead acceptable while Minecraft runs.
- OBS can auto-start minimized at boot (it can: `--startreplaybuffer` /
  minimize-to-tray; or Task Scheduler).

### Test 2 — Cloud370 obs-profanity-filter (only if Test 1 fails on latency)

Same wiring (steps 3–5). Then:
- Tools → **语音脏话屏蔽配置** (Profanity Filter config)
- Model: pick **[357MB]标准** (bilingual zh-en streaming, delay preset 500ms)
- Set delay ≥ 300–500ms, word list supports plain words + regex (中英混合),
  beep = 哔声
- Filters → + → **语音脏话屏蔽 (Profanity Filter)** on the source; monitor as above.
- Note: UI strings are hardcoded Chinese (empty en-US locale). One-time setup
  pain, low-latency payoff.

### Decision gate

- Test 1 passes → use it; write a setup doc for the kid's PC; project done at
  zero code.
- Test 1 close but flawed (e.g. OBS too heavy, latency too high) → build our own
  using the sherpa-onnx delay-and-backtrack pattern proven in the smoke test.
- Both fail → Phase 1 (build), sherpa-onnx streaming English + ring buffer.

## Risk notes

- **Feedback loop**: never monitor to the same device being captured. With
  VB-Cable in the middle (default out = CABLE Input, capture = CABLE Output,
  monitor = real device) there is no loop.
- **If the PC should stay usable without the filter**: switching default output
  back to real speakers restores normal audio instantly.
- obs-cleanstream detects via regex on the live transcript — misses will happen
  with music/noise; model size is the main accuracy lever.
