#!/bin/sh
set -e

if [ ! -f /app/data/orchestrator.dev.db ]; then
  echo "Downloading the notebook for local example execution. You can modify it later via the UI at http://localhost:3000/models."
  model-orchestrator dev \
    --configuration-file /app/config/orchestrator.dev.yml \
    import https://github.com/crunchdao/crunch-synth/blob/0.3.0/condorgame/examples/benchmarktracker.ipynb \
    --import-choice 1 \
    --import-name condorgame-benchmarktracker
fi

exec "$@"   # runs the real CMD