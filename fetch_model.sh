#!/bin/sh
# Download the sherpa-onnx streaming English ASR model (20M, int8).
set -e
cd "$(dirname "$0")"
if [ -f model/tokens.txt ]; then
    echo "model/ already present"
    exit 0
fi
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17.tar.bz2"
curl -L -o model.tar.bz2 "$URL"
mkdir -p model
tar -xjf model.tar.bz2 --strip-components=1 -C model
rm model.tar.bz2
echo "model ready in ./model"
