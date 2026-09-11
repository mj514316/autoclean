#!/usr/bin/env python3
"""
autoclean configurator — tkinter GUI.

Pick audio devices, tune timing offsets, start/stop the censor, and watch
detections land in the log pane. Settings persist to autoclean.json.

On Windows: input device = "CABLE Output" (VB-Cable), output = real speakers.
On Mac dev: input = mic or BlackHole, output = headphones.
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

import sounddevice as sd

import autoclean

APP_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
           else os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(APP_DIR, "autoclean.json")
WORDLIST_PATH = os.path.join(APP_DIR, "words.txt")

DEFAULTS = {
    "input_device": None,
    "output_device": None,
    "delay": 0.8,
    "ts_offset_ms": 260,
    "pad_ms": 60,
    "replace": "silence",
    "threads": 2,
    "wordlist": WORDLIST_PATH,
}


def ensure_wordlist():
    if not os.path.exists(WORDLIST_PATH):
        bundled = autoclean.respath("words.txt")
        if os.path.exists(bundled):
            import shutil
            shutil.copy(bundled, WORDLIST_PATH)
        else:
            with open(WORDLIST_PATH, "w") as f:
                f.write("# one banned word per line\n")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("autoclean")
        self.cfg = self.load_config()
        self.engine = None
        self.log_q = queue.Queue()

        ensure_wordlist()
        self.build_ui()
        self.after(200, self.poll_log)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- config ----------
    def load_config(self):
        try:
            with open(CONFIG_PATH) as f:
                return {**DEFAULTS, **json.load(f)}
        except Exception:
            return dict(DEFAULTS)

    def save_config(self):
        cfg = {k: self.vars[k].get() for k in self.vars}
        cfg["input_device"] = self.dev_index(self.in_dev, "in")
        cfg["output_device"] = self.dev_index(self.out_dev, "out")
        cfg["wordlist"] = self.vars["wordlist"].get()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)

    # ---------- devices ----------
    def devices(self, kind):
        out = []
        for i, d in enumerate(sd.query_devices()):
            if kind == "in" and d["max_input_channels"] > 0:
                out.append((i, d["name"]))
            if kind == "out" and d["max_output_channels"] > 0:
                out.append((i, d["name"]))
        return out

    def dev_index(self, combo, kind):
        sel = combo.current()
        devs = self.devices(kind)
        return devs[sel][0] if 0 <= sel < len(devs) else None

    def build_ui(self):
        self.vars = {k: tk.Variable(value=v) for k, v in self.cfg.items()}
        pad = {"padx": 8, "pady": 4, "sticky": "w"}

        ttk.Label(self, text="Input (capture)").grid(row=0, column=0, **pad)
        self.in_dev = ttk.Combobox(self, width=38, state="readonly")
        self.in_dev["values"] = [f"{i}: {n}" for i, n in self.devices("in")]
        self.in_dev.grid(row=0, column=1, **pad)

        ttk.Label(self, text="Output (to speakers)").grid(row=1, column=0, **pad)
        self.out_dev = ttk.Combobox(self, width=38, state="readonly")
        self.out_dev["values"] = [f"{i}: {n}" for i, n in self.devices("out")]
        self.out_dev.grid(row=1, column=1, **pad)

        # preselect saved devices
        for combo, key, kind in ((self.in_dev, "input_device", "in"),
                                 (self.out_dev, "output_device", "out")):
            idx = self.cfg.get(key)
            names = [i for i, _ in self.devices(kind)]
            if idx in names:
                combo.current(names.index(idx))
            elif names:
                combo.current(0)

        def slider(row, label, var, lo, hi, fmt="{:.2f}"):
            ttk.Label(self, text=label).grid(row=row, column=0, **pad)
            val = ttk.Label(self, text="")
            s = ttk.Scale(self, from_=lo, to=hi, variable=self.vars[var])
            s.grid(row=row, column=1, **pad)
            def upd(*_):
                v = self.vars[var].get()
                val.config(text=fmt.format(v))
            self.vars[var].trace_add("write", upd)
            upd()
            val.grid(row=row, column=2, **pad)
            return s

        slider(2, "Audio delay (s)", "delay", 0.3, 3.0)
        slider(3, "Timing offset (ms)", "ts_offset_ms", 0, 600, "{:.0f}")
        slider(4, "Pad before word (ms)", "pad_ms", 0, 200, "{:.0f}")

        ttk.Label(self, text="On flagged word").grid(row=5, column=0, **pad)
        rf = ttk.Frame(self)
        ttk.Radiobutton(rf, text="Mute (silence)", value="silence",
                        variable=self.vars["replace"]).pack(side="left")
        ttk.Radiobutton(rf, text="Beep", value="beep",
                        variable=self.vars["replace"]).pack(side="left")
        rf.grid(row=5, column=1, **pad)

        ttk.Label(self, text="Word list").grid(row=6, column=0, **pad)
        wf = ttk.Frame(self)
        ttk.Entry(wf, textvariable=self.vars["wordlist"],
                  width=28).pack(side="left")
        ttk.Button(wf, text="…", width=3, command=self.browse).pack(side="left")
        ttk.Button(wf, text="Edit", command=self.edit_words).pack(side="left")
        wf.grid(row=6, column=1, **pad)

        bf = ttk.Frame(self)
        self.start_btn = ttk.Button(bf, text="Start", command=self.toggle)
        self.start_btn.pack(side="left")
        ttk.Button(bf, text="Save settings",
                   command=self.save_config).pack(side="left", padx=6)
        self.status = ttk.Label(bf, text="stopped")
        self.status.pack(side="left", padx=8)
        bf.grid(row=7, column=0, columnspan=3, **pad)

        self.logbox = scrolledtext.ScrolledText(self, width=62, height=12,
                                              state="disabled")
        self.logbox.grid(row=8, column=0, columnspan=3, padx=8, pady=(0, 8))

    def browse(self):
        p = filedialog.askopenfilename(initialdir=APP_DIR,
                                     filetypes=[("Text", "*.txt")])
        if p:
            self.vars["wordlist"].set(p)

    def edit_words(self):
        path = self.vars["wordlist"].get()
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", path])
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    # ---------- engine ----------
    def gui_log(self, msg):
        self.log_q.put(msg)

    def poll_log(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.logbox.config(state="normal")
                self.logbox.insert("end", msg + "\n")
                self.logbox.see("end")
                self.logbox.config(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self.poll_log)

    def toggle(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
            self.start_btn.config(text="Start")
            self.status.config(text="stopped")
            return
        try:
            self.save_config()
            args = argparse.Namespace(
                input_device=self.dev_index(self.in_dev, "in"),
                output_device=self.dev_index(self.out_dev, "out"),
                delay=float(self.vars["delay"].get()),
                ts_offset_ms=int(float(self.vars["ts_offset_ms"].get())),
                pad_ms=int(float(self.vars["pad_ms"].get())),
                replace=self.vars["replace"].get(),
                threads=int(self.cfg.get("threads", 2)),
                wordlist=self.vars["wordlist"].get(),
                model_dir=autoclean.MODEL_DIR_DEFAULT,
                provider="cpu", beep_freq=1000, beep_gain=0.4,
                simulate=None, out=None,
            )
            self.engine = autoclean.Engine(args, log=self.gui_log)
            self.engine.start()
            self.start_btn.config(text="Stop")
            self.status.config(text="running")
            self.gui_log(f"started: delay={args.delay}s "
                         f"offset={args.ts_offset_ms}ms pad={args.pad_ms}ms")
        except Exception as e:
            self.engine = None
            self.status.config(text=f"error: {e}")

    def on_close(self):
        if self.engine:
            self.engine.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
