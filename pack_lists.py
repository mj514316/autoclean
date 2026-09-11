#!/usr/bin/env python3
"""Pack wordlists/*.txt -> wordlists/*.dat obfuscated blobs for commit.

The .txt sources stay gitignored; only the .dat files are pushed.
Obfuscation only (see autoclean.decode_list) — not encryption."""

import glob
import os

import autoclean

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    for txt in sorted(glob.glob(os.path.join(HERE, "wordlists", "*.txt"))):
        with open(txt, "rb") as f:
            blob = autoclean.encode_list(f.read())
        out = txt[:-4] + ".dat"
        with open(out, "wb") as f:
            f.write(blob)
        print("packed", os.path.basename(out),
              f"({os.path.getsize(txt)}B -> {os.path.getsize(out)}B)")


if __name__ == "__main__":
    main()
