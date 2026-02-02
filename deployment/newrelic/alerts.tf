# ---------------------------------------------------------------------------
# NewRelic Alert Configuration
# ---------------------------------------------------------------------------
# This Terraform configuration sets up alerts for:
# - High CPU usage
# - High Memory usage
# - Docker container crashes/restarts
# - Application errors
#
# Usage:
#   1. Set environment variables:
#      export TF_VAR_newrelic_api_key="your-api-key"
#      export TF_VAR_newrelic_account_id="your-account-id"
#      export TF_VAR_project_name="condorgame-backend"  # or use COMPOSE_PROJECT_NAME
#   2. Run: terraform init && terraform apply
# ---------------------------------------------------------------------------

terraform {
  required_providers {
    newrelic = {
      source  = "newrelic/newrelic"
      version = "~> 3.0"
    }
  }
}

provider "newrelic" {
  account_id = var.newrelic_account_id
  api_key    = var.newrelic_api_key
  region     = var.newrelic_region
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "project_name" {
  description = "Project name (matches COMPOSE_PROJECT_NAME)"
  type        = string
}

variable "newrelic_account_id" {
  description = "NewRelic Account ID"
  type        = string
}

variable "newrelic_api_key" {
  description = "NewRelic User API Key"
  type        = string
  sensitive   = true
}

variable "newrelic_region" {
  description = "NewRelic region (US or EU)"
  type        = string
  default     = "EU"
}

variable "notification_email" {
  description = "Email address for alert notifications (optional)"
  type        = string
  default     = ""
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for alert notifications (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "slack_channel" {
  description = "Slack channel name for notifications (e.g. #alerts)"
  type        = string
  default     = "#alerts"
}

variable "infra_host_name" {
  description = "Infrastructure host display name (defaults to project_name-host)"
  type        = string
  default     = ""
}

# CPU/Memory thresholds
variable "cpu_critical_threshold" {
  description = "CPU usage percentage to trigger critical alert"
  type        = number
  default     = 90
}

variable "cpu_warning_threshold" {
  description = "CPU usage percentage to trigger warning alert"
  type        = number
  default     = 80
}

variable "memory_critical_threshold" {
  description = "Memory usage percentage to trigger critical alert"
  type        = number
  default     = 90
}

variable "memory_warning_threshold" {
  description = "Memory usage percentage to trigger warning alert"
  type        = number
  default     = 80
}

# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  infra_host_name = var.infra_host_name != "" ? var.infra_host_name : "${var.project_name}-host"
}

# ---------------------------------------------------------------------------
# Alert Policy
# ---------------------------------------------------------------------------

resource "newrelic_alert_policy" "main" {
  name                = "${var.project_name} Alerts"
  incident_preference = "PER_CONDITION"
}

# ---------------------------------------------------------------------------
# Notification Channel (Email) - Optional
# ---------------------------------------------------------------------------

resource "newrelic_notification_destination" "email" {
  count = var.notification_email != "" ? 1 : 0
  name  = "${var.project_name} Email Destination"
  type  = "EMAIL"

  property {
    key   = "email"
    value = var.notification_email
  }
}

resource "newrelic_notification_channel" "email_channel" {
  count          = var.notification_email != "" ? 1 : 0
  name           = "${var.project_name} Email Channel"
  type           = "EMAIL"
  destination_id = newrelic_notification_destination.email[0].id
  product        = "IINT"

  property {
    key   = "subject"
    value = "${var.project_name} Alert: {{issueTitle}}"
  }
}

resource "newrelic_workflow" "main" {
  name                  = "${var.project_name} Alert Workflow"
  muting_rules_handling = "NOTIFY_ALL_ISSUES"

  issues_filter {
    name = "${var.project_name}-filter"
    type = "FILTER"

    predicate {
      attribute = "labels.policyIds"
      operator  = "EXACTLY_MATCHES"
      values    = [newrelic_alert_policy.main.id]
    }
  }

  dynamic "destination" {
    for_each = var.notification_email != "" ? [1] : []
    content {
      channel_id = newrelic_notification_channel.email_channel[0].id
    }
  }

  dynamic "destination" {
    for_each = var.slack_webhook_url != "" ? [1] : []
    content {
      channel_id = newrelic_notification_channel.slack_channel[0].id
    }
  }
}

# ---------------------------------------------------------------------------
# Notification Channel (Slack) - Optional
# ---------------------------------------------------------------------------

resource "newrelic_notification_destination" "slack" {
  count = var.slack_webhook_url != "" ? 1 : 0
  name  = "${var.project_name} Slack Destination"
  type  = "WEBHOOK"

  property {
    key   = "url"
    value = var.slack_webhook_url
  }
}

resource "newrelic_notification_channel" "slack_channel" {
  count          = var.slack_webhook_url != "" ? 1 : 0
  name           = "${var.project_name} Slack Channel"
  type           = "WEBHOOK"
  destination_id = newrelic_notification_destination.slack[0].id
  product        = "IINT"

  property {
    key   = "payload"
    value = jsonencode({
      channel = var.slack_channel
      text    = "🚨 *$${var.project_name} Alert*"
      attachments = [
        {
          color = "danger"
          fields = [
            {
              title = "Issue"
              value = "{{issueTitle}}"
              short = false
            },
            {
              title = "Priority"
              value = "{{priority}}"
              short = true
            },
            {
              title = "State"
              value = "{{state}}"
              short = true
            }
          ]
          actions = [
            {
              type = "button"
              text = "View in NewRelic"
              url  = "{{issuePageUrl}}"
            }
          ]
        }
      ]
    })
  }
}

# ---------------------------------------------------------------------------
# CPU Alert Condition
# ---------------------------------------------------------------------------

resource "newrelic_nrql_alert_condition" "high_cpu" {
  account_id                   = var.newrelic_account_id
  policy_id                    = newrelic_alert_policy.main.id
  name                         = "High CPU Usage"
  description                  = "Alert when CPU usage exceeds threshold"
  enabled                      = true
  violation_time_limit_seconds = 259200

  nrql {
    query = "SELECT average(cpuPercent) FROM SystemSample WHERE displayName = '${local.infra_host_name}'"
  }

  critical {
    operator              = "above"
    threshold             = var.cpu_critical_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }

  warning {
    operator              = "above"
    threshold             = var.cpu_warning_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }

  fill_option        = "none"
  aggregation_window = 60
  aggregation_method = "event_flow"
  aggregation_delay  = 120
}

# ---------------------------------------------------------------------------
# Memory Alert Condition
# ---------------------------------------------------------------------------

resource "newrelic_nrql_alert_condition" "high_memory" {
  account_id                   = var.newrelic_account_id
  policy_id                    = newrelic_alert_policy.main.id
  name                         = "High Memory Usage"
  description                  = "Alert when memory usage exceeds threshold"
  enabled                      = true
  violation_time_limit_seconds = 259200

  nrql {
    query = "SELECT average(memoryUsedPercent) FROM SystemSample WHERE displayName = '${local.infra_host_name}'"
  }

  critical {
    operator              = "above"
    threshold             = var.memory_critical_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }

  warning {
    operator              = "above"
    threshold             = var.memory_warning_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }

  fill_option        = "none"
  aggregation_window = 60
  aggregation_method = "event_flow"
  aggregation_delay  = 120
}

# ---------------------------------------------------------------------------
# Docker Container Restart Alert
# ---------------------------------------------------------------------------

resource "newrelic_nrql_alert_condition" "container_restart" {
  account_id                   = var.newrelic_account_id
  policy_id                    = newrelic_alert_policy.main.id
  name                         = "Docker Container Restarted"
  description                  = "Alert when a Docker container restarts (possible crash)"
  enabled                      = true
  violation_time_limit_seconds = 259200

  nrql {
    query = "SELECT count(*) FROM ContainerSample WHERE restartCount > 0 AND name LIKE '${var.project_name}%'"
  }

  critical {
    operator              = "above"
    threshold             = 0
    threshold_duration    = 60
    threshold_occurrences = "at_least_once"
  }

  fill_option        = "none"
  aggregation_window = 60
  aggregation_method = "event_flow"
  aggregation_delay  = 120
}

# ---------------------------------------------------------------------------
# Docker Container Not Running Alert
# ---------------------------------------------------------------------------

resource "newrelic_nrql_alert_condition" "container_not_running" {
  account_id                   = var.newrelic_account_id
  policy_id                    = newrelic_alert_policy.main.id
  name                         = "Docker Container Not Running"
  description                  = "Alert when expected Docker containers are not running"
  enabled                      = true
  violation_time_limit_seconds = 259200

  nrql {
    query = "SELECT uniqueCount(name) FROM ContainerSample WHERE status = 'running' AND name LIKE '${var.project_name}%'"
  }

  critical {
    operator              = "below"
    threshold             = 3
    threshold_duration    = 300
    threshold_occurrences = "all"
  }

  fill_option        = "none"
  aggregation_window = 60
  aggregation_method = "event_flow"
  aggregation_delay  = 120
}

# ---------------------------------------------------------------------------
# Log Error Alert (for catching error logs)
# ---------------------------------------------------------------------------

resource "newrelic_nrql_alert_condition" "log_errors" {
  account_id                   = var.newrelic_account_id
  policy_id                    = newrelic_alert_policy.main.id
  name                         = "Error Logs Detected"
  description                  = "Alert when ERROR level logs are detected"
  enabled                      = true
  violation_time_limit_seconds = 259200

  nrql {
    query = "SELECT count(*) FROM Log WHERE level = 'ERROR' AND container_name LIKE '${var.project_name}%'"
  }

  critical {
    operator              = "above"
    threshold             = 5
    threshold_duration    = 300
    threshold_occurrences = "all"
  }

  warning {
    operator              = "above"
    threshold             = 1
    threshold_duration    = 300
    threshold_occurrences = "at_least_once"
  }

  fill_option        = "none"
  aggregation_window = 60
  aggregation_method = "event_flow"
  aggregation_delay  = 120
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "alert_policy_id" {
  value       = newrelic_alert_policy.main.id
  description = "The ID of the created alert policy"
}

output "workflow_id" {
  value       = newrelic_workflow.main.id
  description = "The ID of the created workflow"
}
