#!/bin/sh
set -e

bootstrap_submission() {
  submission_id="$1"
  template_dir="$2"
  submission_dir="/app/data/submissions/${submission_id}"

  if [ ! -f "${submission_dir}/main.py" ] || [ ! -f "${submission_dir}/tracker.py" ]; then
    echo "Bootstrapping local starter submission files into ${submission_dir}"
    mkdir -p "${submission_dir}"
    cp -f "${template_dir}"/* "${submission_dir}"/
  fi
}

bootstrap_submission "starter-submission" "/app/config/starter-submission"

# ── Patch model-orchestrator to group model containers in Docker Desktop ──
# The LocalModelRunner creates containers without Compose labels, so they
# appear ungrouped in Docker Desktop.  This monkey-patch adds
# com.docker.compose.project so model containers appear under the same
# group as the node services.
RUNNER="/usr/local/lib/python3.13/site-packages/model_orchestrator/infrastructure/local/_runner.py"
if [ -f "$RUNNER" ] && [ -n "${DOCKER_COMPOSE_PROJECT:-}" ]; then
  if ! grep -q "com.docker.compose.project" "$RUNNER"; then
    echo "Patching LocalModelRunner to add compose project label..."
    sed -i "s|detach=True,|detach=True,\n            labels={\n                'com.docker.compose.project': '${DOCKER_COMPOSE_PROJECT}',\n                'com.docker.compose.service': 'model',\n            },|" "$RUNNER"
  fi
fi

exec "$@"
