#!/bin/sh
set -e

SUBMISSION_DIR="/app/data/submissions/starter-benchmarktracker"
TEMPLATE_DIR="/app/config/starter-submission"

if [ ! -f "$SUBMISSION_DIR/main.py" ] || [ ! -f "$SUBMISSION_DIR/tracker.py" ]; then
  echo "Bootstrapping local starter submission files into $SUBMISSION_DIR"
  mkdir -p "$SUBMISSION_DIR"
  cp -f "$TEMPLATE_DIR"/* "$SUBMISSION_DIR"/
fi

exec "$@"   # runs the real CMD
