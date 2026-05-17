# ── EKS ───────────────────────────────────────────────────────────────────────

output "eks_cluster_endpoint" {
  description = "API server endpoint for the EKS cluster. Used by kubectl and Helm."
  value       = module.eks.cluster_endpoint
  sensitive   = false
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster. Required by aws eks update-kubeconfig."
  value       = module.eks.cluster_name
}

output "eks_cluster_certificate_authority_data" {
  description = "Base64-encoded certificate authority data for TLS verification."
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "eks_oidc_provider_arn" {
  description = "ARN of the EKS OIDC provider. Required for IRSA trust policies."
  value       = module.eks.oidc_provider_arn
}

# ── RDS ───────────────────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "Writer endpoint for the RDS PostgreSQL instance (host:port)."
  value       = aws_db_instance.postgres.endpoint
  sensitive   = false
}

output "rds_db_name" {
  description = "Name of the initial database created on the RDS instance."
  value       = aws_db_instance.postgres.db_name
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────

output "redis_endpoint" {
  description = "Primary endpoint for the ElastiCache Redis replication group."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "redis_port" {
  description = "Port that Redis listens on."
  value       = 6379
}

# ── MSK Kafka ─────────────────────────────────────────────────────────────────

output "kafka_bootstrap_brokers" {
  description = "TLS bootstrap broker connection string for MSK Kafka clients."
  value       = aws_msk_cluster.kafka.bootstrap_brokers_tls
  sensitive   = false
}

output "kafka_zookeeper_connect_string" {
  description = "ZooKeeper connection string (Kafka admin tools, legacy clients)."
  value       = aws_msk_cluster.kafka.zookeeper_connect_string
}

# ── VPC ───────────────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "ID of the VPC that hosts all private resources."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs used by EKS nodes, RDS, Redis, and Kafka."
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "List of public subnet IDs used by the Application Load Balancer."
  value       = module.vpc.public_subnets
}

# ── KMS ───────────────────────────────────────────────────────────────────────

output "phi_kms_key_arn" {
  description = "ARN of the KMS key used for PHI field-level encryption and RDS at-rest encryption."
  value       = aws_kms_key.phi_key.arn
}

output "phi_kms_key_id" {
  description = "Key ID of the PHI KMS key. Use this when the ARN is not required."
  value       = aws_kms_key.phi_key.key_id
}

# ── ECR ───────────────────────────────────────────────────────────────────────

output "ecr_repository_url_backend" {
  description = "ECR repository URL for the backend container image."
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_url_frontend" {
  description = "ECR repository URL for the frontend container image."
  value       = aws_ecr_repository.frontend.repository_url
}

# ── Secrets Manager ───────────────────────────────────────────────────────────

output "db_password_secret_arn" {
  description = "ARN of the Secrets Manager secret that holds the RDS password. Used by ESO."
  value       = aws_secretsmanager_secret.db_password.arn
}

# ── IAM ───────────────────────────────────────────────────────────────────────

output "eks_pod_role_arn" {
  description = "IAM role ARN to set as eks.amazonaws.com/role-arn on the backend ServiceAccount (IRSA)."
  value       = aws_iam_role.eks_pod_role.arn
}

output "external_secrets_role_arn" {
  description = "IAM role ARN for the External Secrets Operator ServiceAccount (IRSA)."
  value       = aws_iam_role.external_secrets.arn
}
