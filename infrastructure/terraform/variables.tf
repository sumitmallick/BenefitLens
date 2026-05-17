variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for all resources"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Deployment environment"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t3.medium"
  description = "RDS instance class. Upgrade to db.r6g.large for production workloads."
}
