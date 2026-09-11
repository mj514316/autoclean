#!/bin/sh
# Bootstrap a default word list WITHOUT storing list content in this repo.
# Downloads the public LDNOOBW English list, then packs it to wordlists/*.dat
# (obfuscated at rest). Stdlib python only — no venv needed.
set -e
cd "$(dirname "$0")"
mkdir -p wordlists
if [ ! -f wordlists/profanity.txt ] && [ ! -f wordlists/profanity.dat ]; then
    echo "Fetching LDNOOBW english list..."
    curl -sL -o wordlists/profanity.txt \
        "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en"
fi
python3 pack_lists.py
echo "wordlists ready (local-only, gitignored)"
