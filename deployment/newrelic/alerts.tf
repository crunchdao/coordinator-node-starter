# ---------------------------------------------------------------------------
# NewRelic Alert Configuration (2026 Generic Standard)
# ---------------------------------------------------------------------------
# This implementation covers the 6 Golden Rules:
# 1. APM Errors (Static > 0)
# 2. APM Latency (Anomaly 3.0 SD)
# 3. Service Heartbeat (Static < 1 - Loss of Signal Heartbeat)
# 4. Host CPU Saturation (Static 90%)
# 5. Host Memory Saturation (Static 90%)
# 6. Host Disk Saturation (Static 85%)
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
variable "project_name" { type = string }
variable "newrelic_account_id" { type = string }
variable "newrelic_api_key" {
  type      = string
  sensitive = true
}
variable "newrelic_region" {
  type    = string
  default = "EU"
}
variable "notification_email" {
  type    = string
  default = ""
}
variable "slack_webhook_url" {
  type      = string
  default   = ""
  sensitive = true
}
variable "slack_channel" {
  type    = string
  default = "#alerts"
}
variable "infra_host_name" {
  type    = string
  default = ""
}

# Smart Sensitivity & Saturation thresholds
variable "latency_std_dev" {
  type    = number
  default = 3.0
}
variable "cpu_critical_threshold" {
  type    = number
  default = 90
}
variable "memory_critical_threshold" {
  type    = number
  default = 90
}
variable "disk_critical_threshold" {
  type    = number
  default = 85
}

locals {
  infra_host_name = var.infra_host_name != "" ? var.infra_host_name : "${var.project_name}-host"
}

# ---------------------------------------------------------------------------
# Alert Policy
# ---------------------------------------------------------------------------
resource "newrelic_alert_policy" "main" {
  name                = "${var.project_name} Standard Alerts"
  incident_preference = "PER_CONDITION"
}

# ---------------------------------------------------------------------------
# Notification Destinations & Workflows
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
      text    = "🚨 *${var.project_name} Alert* - {{state}}"
      attachments = [{
        color = "{{#eq state 'CLOSED'}}good{{else}}danger{{/eq}}"
        title = "{{issueTitle}}"
        text  = "{{#each accumulations.conditionDescription}}{{this}}\n{{/each}}"
        fields = [
          { title = "Condition", value = "{{#each accumulations.conditionName}}{{this}}{{#unless @last}}, {{/unless}}{{/each}}", short = false },
          { title = "Priority", value = "{{priority}}", short = true },
          { title = "State", value = "{{state}}", short = true }
        ]
        actions = [{ type = "button", text = "View in NewRelic", url = "{{issuePageUrl}}" }]
      }]
    })
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
    content { channel_id = newrelic_notification_channel.email_channel[0].id }
  }
  dynamic "destination" {
    for_each = var.slack_webhook_url != "" ? [1] : []
    content { channel_id = newrelic_notification_channel.slack_channel[0].id }
  }
}

# ---------------------------------------------------------------------------
# 1. ERROR RATE: Dimensional Metric (Static > 0%)
# ---------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "apm_errors" {
  account_id = var.newrelic_account_id
  policy_id  = newrelic_alert_policy.main.id
  type       = "static"
  name       = "APM Error Rate Spike"
  enabled    = true
  nrql {
    query = "SELECT (count(apm.service.error.count) / count(apm.service.transaction.duration)) * 100 FROM Metric WHERE appName LIKE '${var.project_name}%' FACET appName"
  }
  critical {
    operator              = "above"
    threshold             = 0
    threshold_duration    = 60
    threshold_occurrences = "at_least_once"
  }
  fill_option = "last_value"
}

# ---------------------------------------------------------------------------
# 2. RESPONSE TIME: Dimensional Metric (Anomaly 3.0 SD)
# ---------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "smart_latency" {
  account_id         = var.newrelic_account_id
  policy_id          = newrelic_alert_policy.main.id
  type               = "baseline"
  name               = "APM Response Time Anomaly"
  baseline_direction = "upper_only"
  enabled            = true
  nrql {
    query = "SELECT average(apm.service.transaction.duration) * 1000 FROM Metric WHERE appName LIKE '${var.project_name}%' FACET appName"
  }
  critical {
    operator              = "above"
    threshold             = var.latency_std_dev
    threshold_duration    = 300
    threshold_occurrences = "all"
  }
}

# ---------------------------------------------------------------------------
# 3. SERVICE HEARTBEAT: The "Dead Process" Alert
# ---------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "service_heartbeat" {
  account_id  = var.newrelic_account_id
  policy_id   = newrelic_alert_policy.main.id
  type        = "static"
  name        = "Service Heartbeat Missing"
  description = "Alerts if the internal pulse or transaction stream stops"
  enabled     = true
  nrql {
    # Watches for your custom HeartbeatPulse transaction
    query = "SELECT count(*) FROM Transaction WHERE appName LIKE '${var.project_name}%' AND name LIKE '%HeartbeatPulse%' FACET appName"
  }
  critical {
    operator              = "below"
    threshold             = 1
    threshold_duration    = 180 # 3 minutes
    threshold_occurrences = "all"
  }
  # Ensures the alert fires even if data vanishes completely
  expiration_duration            = 600
  open_violation_on_expiration   = true
  close_violations_on_expiration = true
}

# ---------------------------------------------------------------------------
# 4. HOST CPU: System Sample (Static 90%)
# ---------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "host_cpu" {
  account_id = var.newrelic_account_id
  policy_id  = newrelic_alert_policy.main.id
  type       = "static"
  name       = "Host CPU Saturation"
  nrql {
    query = "SELECT average(cpuPercent) FROM SystemSample WHERE displayName = '${local.infra_host_name}'"
  }
  critical {
    operator              = "above"
    threshold             = var.cpu_critical_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }
}

# ---------------------------------------------------------------------------
# 5. HOST MEMORY: System Sample (Static 90%)
# ---------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "host_memory" {
  account_id = var.newrelic_account_id
  policy_id  = newrelic_alert_policy.main.id
  type       = "static"
  name       = "Host Memory Saturation"
  nrql {
    query = "SELECT average(memoryUsedPercent) FROM SystemSample WHERE displayName = '${local.infra_host_name}'"
  }
  critical {
    operator              = "above"
    threshold             = var.memory_critical_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }
}

# ---------------------------------------------------------------------------
# 6. HOST DISK: Storage Sample (Static 85%)
# ---------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "host_disk" {
  account_id = var.newrelic_account_id
  policy_id  = newrelic_alert_policy.main.id
  type       = "static"
  name       = "Host Disk Space Saturation"
  nrql {
    query = "SELECT max(diskUsedPercent) FROM StorageSample WHERE displayName = '${local.infra_host_name}'"
  }
  critical {
    operator              = "above"
    threshold             = var.disk_critical_threshold
    threshold_duration    = 300
    threshold_occurrences = "all"
  }
}

output "alert_policy_id" { value = newrelic_alert_policy.main.id }
output "workflow_id" { value = newrelic_workflow.main.id }