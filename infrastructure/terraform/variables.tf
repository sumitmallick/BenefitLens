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

variable "cluster_name" {
  type        = string
  default     = "claims-eks"
  description = "Name of the EKS cluster. Used in IAM OIDC trust policies and resource tags."
}

variable "ecr_image_tag" {
  type        = string
  default     = "latest"
  description = "Docker image tag to deploy. Overridden in CI with the Git commit SHA."
}
