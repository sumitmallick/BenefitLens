/**
 * Monitoring — CloudWatch alarms, SNS alerts, and log groups
 *
 * All alarms feed into the claims-alerts SNS topic. In production, subscribe
 * PagerDuty/OpsGenie/Slack to this topic for on-call alerting.
 */

# ── SNS topic for all infrastructure alerts ───────────────────────────────────

resource "aws_sns_topic" "alerts" {
  name              = "claims-infrastructure-alerts"
  kms_master_key_id = aws_kms_key.phi_key.key_id  # encrypt alert payloads (may contain resource IDs)
  display_name      = "Claims Infrastructure Alerts"

  tags = local.common_tags
}

resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudWatchPublish"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.alerts.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = local.account_id
          }
        }
      }
    ]
  })
}

# ── RDS CPU alarm ─────────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "claims-rds-high-cpu"
  alarm_description   = "RDS PostgreSQL CPU utilisation exceeded 80% for 5 consecutive minutes. Consider upgrading instance class or optimising slow queries."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5       # 5 consecutive 1-minute datapoints
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60      # 1-minute granularity
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.id
  }

  alarm_actions             = [aws_sns_topic.alerts.arn]
  ok_actions                = [aws_sns_topic.alerts.arn]
  insufficient_data_actions = [aws_sns_topic.alerts.arn]

  treat_missing_data = "notBreaching"

  tags = local.common_tags
}

# ── RDS free storage alarm ────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "claims-rds-low-storage"
  alarm_description   = "RDS free storage dropped below 10 GiB. Enable storage autoscaling or provision more capacity."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 10 * 1024 * 1024 * 1024  # 10 GiB in bytes

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  treat_missing_data = "notBreaching"

  tags = local.common_tags
}

# ── Redis memory alarm ────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "claims-redis-high-memory"
  alarm_description   = "Redis database memory usage exceeded 80%. Review cache TTLs or scale the node type."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 60
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.redis.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  treat_missing_data = "notBreaching"

  tags = local.common_tags
}

# ── Redis evictions alarm ─────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "redis_evictions" {
  alarm_name          = "claims-redis-evictions"
  alarm_description   = "Redis is evicting keys. Annual limit cache misses may cause extra DB load."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 60
  statistic           = "Sum"
  threshold           = 100

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.redis.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  treat_missing_data = "notBreaching"

  tags = local.common_tags
}

# ── Kafka under-replicated partitions alarm ───────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "kafka_under_replicated_partitions" {
  alarm_name          = "claims-kafka-under-replicated-partitions"
  alarm_description   = "MSK Kafka has under-replicated partitions. Domain events may be at risk of loss."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnderReplicatedPartitions"
  namespace           = "AWS/Kafka"
  period              = 60
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    Cluster_Name = aws_msk_cluster.kafka.cluster_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  treat_missing_data = "notBreaching"

  tags = local.common_tags
}

# ── CloudWatch Log Group for application logs ─────────────────────────────────

resource "aws_cloudwatch_log_group" "claims_app" {
  name              = "/claims/application"
  retention_in_days = 7     # HIPAA minimum audit log retention (adjust to 90 days for compliance audit)
  kms_key_id        = aws_kms_key.phi_key.arn

  tags = merge(local.common_tags, {
    Name       = "claims-application-logs"
    Compliance = "HIPAA"
  })
}

resource "aws_cloudwatch_log_group" "claims_access" {
  name              = "/claims/access"
  retention_in_days = 7
  kms_key_id        = aws_kms_key.phi_key.arn

  tags = merge(local.common_tags, {
    Name       = "claims-access-logs"
    Compliance = "HIPAA"
  })
}

# ── CloudWatch Dashboard ──────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "claims" {
  dashboard_name = "claims-system"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "RDS CPU Utilisation"
          period = 60
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.postgres.id]
          ]
          view    = "timeSeries"
          stacked = false
          yAxis   = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Redis Memory Usage %"
          period = 60
          metrics = [
            ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "ReplicationGroupId", aws_elasticache_replication_group.redis.id]
          ]
          view  = "timeSeries"
          yAxis = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Kafka Under-Replicated Partitions"
          period = 60
          metrics = [
            ["AWS/Kafka", "UnderReplicatedPartitions", "Cluster_Name", aws_msk_cluster.kafka.cluster_name]
          ]
          view = "timeSeries"
        }
      }
    ]
  })
}
