#!/usr/bin/env python3
"""Pack wordlists/*.txt -> wordlists/*.dat obfuscated blobs for commit.

The .txt sources stay gitignored; only the .dat files are pushed.
Obfuscation only (see autoclean.decode_list) — not encryption."""

import glob
import os
import sys

from listcodec import decode_list, encode_list

HERE = os.path.dirname(os.path.abspath(__file__))


def pack():
    for txt in sorted(glob.glob(os.path.join(HERE, "wordlists", "*.txt"))):
        with open(txt, "rb") as f:
            blob = encode_list(f.read())
        out = txt[:-4] + ".dat"
        with open(out, "wb") as f:
            f.write(blob)
        print("packed", os.path.basename(out),
              f"({os.path.getsize(txt)}B -> {os.path.getsize(out)}B)")


def unpack():
    for dat in sorted(glob.glob(os.path.join(HERE, "wordlists", "*.dat"))):
        with open(dat, "rb") as f:
            text = decode_list(f.read())
        out = dat[:-4] + ".txt"
        with open(out, "w") as f:
            f.write(text)
        print("unpacked", os.path.basename(out))


if __name__ == "__main__":
    unpack() if "--unpack" in sys.argv else pack()
