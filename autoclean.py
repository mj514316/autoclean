#!/usr/bin/env python3
"""
autoclean — real-time audio profanity censor.

Pipeline (delay-and-backtrack):
  input device --+--> ring buffer (delay D)
                 +--> streaming ASR (sherpa-onnx) --> flagged word timestamps
  output device <-- ring buffer, with 1kHz beep spliced over flagged ranges

ASR runs ~50x realtime on CPU, so it detects words while they are still
inside the delayed buffer. D only needs to exceed detection lag.

Mac dev test:    --simulate test.wav --out out.wav   (no audio devices)
Live (Mac):      default mic -> headphones, or BlackHole for system audio
Windows target:  input = "CABLE Output" (VB-Cable), output = real speakers
"""

import argparse
import os
import queue
import re
import string
import sys
import threading
import time
import wave

import numpy as np
import sherpa_onnx
import sounddevice as sd

SR = 16000


def respath(rel):
    """Resolve bundled-resource paths inside a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


MODEL_DIR_DEFAULT = respath("model")


class RingBuffer:
    """Absolute-positioned circular buffer. Writes advance write_pos;
    reads happen at an explicit absolute position (the delayed playhead)."""

    def __init__(self, capacity):
        self.buf = np.zeros(capacity, dtype=np.float32)
        self.cap = capacity
        self.write_pos = 0  # absolute samples written

    def write(self, data: np.ndarray):
        n = len(data)
        idx = np.arange(self.write_pos, self.write_pos + n) % self.cap
        self.buf[idx] = data
        self.write_pos += n

    def read(self, pos: int, n: int) -> np.ndarray:
        if pos + n <= 0:
            return np.zeros(n, dtype=np.float32)
        if pos < 0:
            out = np.zeros(n, dtype=np.float32)
            out[pos:] = self.read(0, n + pos)
            return out
        idx = (pos + np.arange(n)) % self.cap
        return self.buf[idx].copy()


class Censor:
    def __init__(self, args, banned: set):
        self.delay_samples = int(args.delay * SR)
        self.pad = int(args.pad_ms * SR / 1000)
        # streaming models emit tokens ~0.2-0.4s late (they need right context);
        # shift flagged windows earlier to compensate
        self.ts_offset = int(args.ts_offset_ms * SR / 1000)
        self.rb = RingBuffer(self.delay_samples * 4 + SR * 4)
        self.asr_q = queue.Queue()
        self.beep_intervals = []  # list of (start_sample, end_sample)
        self.lock = threading.Lock()
        self.play_pos = -self.delay_samples  # negative = still priming
        self.beep_freq = args.beep_freq
        self.beep_gain = args.beep_gain
        self.replace = args.replace
        self.banned = banned
        self.running = True
        self.missed = 0
        self.log = print  # overridable, e.g. by the configurator GUI

        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=f"{args.model_dir}/tokens.txt",
            encoder=f"{args.model_dir}/encoder-epoch-99-avg-1.int8.onnx",
            decoder=f"{args.model_dir}/decoder-epoch-99-avg-1.int8.onnx",
            joiner=f"{args.model_dir}/joiner-epoch-99-avg-1.int8.onnx",
            num_threads=args.threads,
            sample_rate=SR,
            feature_dim=80,
            enable_endpoint_detection=True,
            provider=args.provider,
        )
        self.stream = self.recognizer.create_stream()
        self.seg_origin = 0       # absolute sample count when stream last reset
        self.fed = 0              # absolute samples fed to ASR
        self.words_done = 0       # words already evaluated (closed)
        self.punct = str.maketrans("", "", string.punctuation)

    # ---------- ASR side ----------
    def feed(self, block: np.ndarray):
        self.stream.accept_waveform(SR, block.astype(np.float32))
        self.fed += len(block)
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)
        self._scan_tokens(final=self.recognizer.is_endpoint(self.stream))
        if self.recognizer.is_endpoint(self.stream):
            self.recognizer.reset(self.stream)
            self.seg_origin = self.fed

    def _scan_tokens(self, final: bool):
        tokens = self.recognizer.tokens(self.stream)
        ts = self.recognizer.timestamps(self.stream)
        # group tokens into words: a token starting with ' ' begins a new word
        words = []  # (text, i_first, i_last_excl)
        for i, tok in enumerate(tokens):
            if i == 0 or tok.startswith(" ") or tok in string.punctuation:
                words.append([tok.strip(), i, i + 1])
            else:
                words[-1][1:] = words[-1][1], i + 1
                words[-1][0] += tok.strip()
        # evaluate all words except the last (still being decoded) unless final
        limit = len(words) if final else max(0, len(words) - 1)
        for k in range(self.words_done, limit):
            text, i0, i1 = (words[k][0].translate(self.punct).lower(),
                            words[k][1], words[k][2])
            if text and text in self.banned:
                start = self.seg_origin + int(ts[i0] * SR) - self.ts_offset \
                    - self.pad
                # end at the next word's start (same late bias) so the mute
                # covers the word's tail without eating the next word;
                # fall back to the word's own last token if utterance-final
                if k + 1 < len(words):
                    end = self.seg_origin + int(ts[words[k + 1][1]] * SR) \
                        - self.ts_offset
                else:
                    end = self.seg_origin + int(ts[i1 - 1] * SR) \
                        - self.ts_offset + int(0.04 * SR) + self.pad
                end = max(end, start + int(0.15 * SR))
                self.flag(text, start, end)
        self.words_done = max(self.words_done, limit)
        if final:
            self.words_done = 0

    def flag(self, word, start, end):
        headroom = (end - max(self.play_pos, 0)) / SR
        with self.lock:
            self.beep_intervals.append((start, end))
        if end <= self.play_pos:
            self.missed += 1
            self.log(f"  !! MISSED '{word}' (arrived after playhead)")
        else:
            self.log(f"  >> muted '{word}'  [{start/SR:.2f}s-{end/SR:.2f}s]  "
                     f"headroom {headroom:.2f}s")

    # ---------- playback side ----------
    def pull(self, n: int) -> np.ndarray:
        out = self.rb.read(self.play_pos, n)
        pos0, pos1 = self.play_pos, self.play_pos + n
        with self.lock:
            ivs = [iv for iv in self.beep_intervals if iv[1] > pos0]
            self.beep_intervals = [iv for iv in self.beep_intervals
                                   if iv[1] > pos0 - SR * 30]
        for (s, e) in ivs:
            a, b = max(s, pos0), min(e, pos1)
            if a < b:
                i0, i1 = a - pos0, b - pos0
                if self.replace == "beep":
                    t = np.arange(a, b) / SR
                    fill = self.beep_gain * np.sin(2 * np.pi * self.beep_freq * t)
                else:
                    fill = np.zeros(i1 - i0, dtype=np.float32)
                fade = min(64, (i1 - i0) // 2)
                env = np.ones(i1 - i0, dtype=np.float32)
                if fade > 0:
                    ramp = np.linspace(0, 1, fade, dtype=np.float32)
                    env[:fade] = ramp
                    env[-fade:] = ramp[::-1]
                seg = out[i0:i1]
                out[i0:i1] = seg * (1 - env) + fill * env
        self.play_pos += n
        return out

    def asr_loop(self):
        while self.running:
            try:
                block = self.asr_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.feed(block)
            self.asr_q.task_done()


def load_banned(path):
    with open(path) as f:
        return {ln.strip().lower() for ln in f
                if ln.strip() and not ln.startswith("#")}


def start_streams(args, cz):
    """Open input/output streams (non-blocking). Returns (istream, ostream)."""
    def in_cb(indata, frames, t, status):
        b = indata[:, 0].copy()
        cz.rb.write(b)
        cz.asr_q.put(b)

    def out_cb(outdata, frames, t, status):
        outdata[:, 0] = cz.pull(frames)
        for c in range(1, outdata.shape[1]):
            outdata[:, c] = outdata[:, 0]

    istream = sd.InputStream(device=args.input_device, samplerate=SR,
                             channels=1, blocksize=1024, callback=in_cb)
    ostream = sd.OutputStream(device=args.output_device, samplerate=SR,
                              channels=1, blocksize=512, callback=out_cb)
    istream.start()
    ostream.start()
    return istream, ostream


def stop_streams(streams):
    for s in streams:
        try:
            s.abort()
        except Exception:
            pass


class Engine:
    """Owns the Censor + ASR thread + audio streams. Used by CLI and GUI."""

    def __init__(self, args, log=print):
        self.args = args
        self.cz = Censor(args, load_banned(args.wordlist))
        self.cz.log = log
        self.streams = None
        self.asr_thread = threading.Thread(target=self.cz.asr_loop,
                                           daemon=True)

    def start(self):
        self.asr_thread.start()
        self.streams = start_streams(self.args, self.cz)

    def stop(self):
        self.cz.running = False
        if self.streams:
            stop_streams(self.streams)
            self.streams = None


def run_live(args, cz):
    streams = start_streams(args, cz)
    print(f"live: delay={args.delay}s  Ctrl+C to stop")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    stop_streams(streams)
    cz.running = False


def run_sim(args, cz):
    with wave.open(args.simulate, "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    # trailing silence flushes the last tokens through the endpoint detector
    audio = np.concatenate([audio, np.zeros(int(1.5 * SR), dtype=np.float32)])
    chunk = int(0.1 * SR)
    out = np.zeros(len(audio) + cz.delay_samples, dtype=np.float32)

    t0 = time.time()
    for off in range(0, len(audio), chunk):
        block = audio[off:off + chunk]
        cz.rb.write(block)
        cz.asr_q.put(block)
        # pace input at realtime
        dt = (off + len(block)) / SR - (time.time() - t0)
        if dt > 0:
            time.sleep(dt)
        # prime playhead once the delay has elapsed in wall-clock time
        if cz.play_pos < 0 and time.time() - t0 >= args.delay:
            cz.play_pos = 0
        # playhead may only read what a delayed listener would have heard
        limit_pos = int((time.time() - t0) * SR) - cz.delay_samples
        while cz.play_pos >= 0 and cz.play_pos < min(limit_pos, len(out)):
            p = cz.play_pos
            n = min(chunk, len(out) - p)
            out[p:p + n] = cz.pull(n)
    cz.asr_q.join()  # let ASR finish flagging before the fast drain
    # drain remainder at full speed
    while cz.play_pos < len(out):
        p = cz.play_pos
        n = min(chunk, len(out) - p)
        out[p:p + n] = cz.pull(n)
    cz.running = False
    print(f"sim done in {time.time()-t0:.1f}s, missed={cz.missed}")
    if args.out:
        with wave.open(args.out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((out * 32767).astype(np.int16).tobytes())
        print(f"wrote {args.out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-device", default=None)
    ap.add_argument("--output-device", default=None)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--wordlist", default="words.txt")
    ap.add_argument("--model-dir", default=MODEL_DIR_DEFAULT)
    ap.add_argument("--provider", default="cpu")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--pad-ms", type=int, default=60)
    ap.add_argument("--replace", choices=["silence", "beep"], default="silence")
    ap.add_argument("--ts-offset-ms", type=int, default=260,
                    help="shift beep windows earlier by this many ms")
    ap.add_argument("--beep-freq", type=float, default=1000)
    ap.add_argument("--beep-gain", type=float, default=0.4)
    ap.add_argument("--simulate", default=None, help="wav file input (16k mono)")
    ap.add_argument("--out", default=None, help="wav output for --simulate")
    ap.add_argument("--list-devices", action="store_true")
    args = ap.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    for attr in ("input_device", "output_device"):
        v = getattr(args, attr)
        if isinstance(v, str) and v.isdigit():
            setattr(args, attr, int(v))

    cz = Censor(args, load_banned(args.wordlist))
    th = threading.Thread(target=cz.asr_loop, daemon=True)
    th.start()

    if args.simulate:
        run_sim(args, cz)
    else:
        run_live(args, cz)


if __name__ == "__main__":
    main()
