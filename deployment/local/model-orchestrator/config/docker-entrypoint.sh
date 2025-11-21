#!/bin/sh
set -e

echo "Downloading notebooks"
model-orchestrator dev \
  --configuration-file /app/config/orchestrator.dev.yml \
  import https://github.com/crunchdao/condorgame/blob/master/condorgame/examples/benchmarktracker.ipynb \
  --import-choice 12311 \
  --import-name condorgame-benchmarktracker

exec "$@"   # runs the real CMD