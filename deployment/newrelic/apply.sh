#!/bin/sh
set -e

if [ -z "$TF_VAR_newrelic_account_id" ]; then
  echo "Skipping NewRelic alerts (NEW_RELIC_ACCOUNT_ID not set)"
  exit 0
fi

terraform init -upgrade -input=false
terraform plan -detailed-exitcode -out=tfplan 2>/dev/null
PLAN_EXIT_CODE=$?

if [ $PLAN_EXIT_CODE -eq 0 ]; then
  echo "No changes needed - NewRelic alerts are up to date"
elif [ $PLAN_EXIT_CODE -eq 2 ]; then
  echo "Applying changes..."
  terraform apply tfplan
else
  echo "Error during planning"
  exit 1
fi

rm -f tfplan