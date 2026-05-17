/**
 * Claims Processing System — AWS Infrastructure
 *
 * Provisions:
 *   - EKS cluster (worker nodes for backend pods)
 *   - RDS PostgreSQL (Multi-AZ for HA, encryption at rest)
 *   - ElastiCache Redis (caching annual limits + policy data)
 *   - MSK Kafka (domain event streaming)
 *   - VPC with private subnets (DB and cache not publicly accessible)
 *   - KMS key for PHI encryption (envelope encryption)
 *   - S3 + CloudWatch for logs
 *
 * CAP theorem stance: CP (Consistency + Partition Tolerance)
 * We prioritise consistency for financial data. Annual limit tracking
 * must not allow double-spend, even under partition.
 * PostgreSQL with synchronous replication satisfies this.
 */

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }
  backend "s3" {
    bucket         = "claims-terraform-state"
    key            = "claims/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "claims-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
}

# ── VPC ────────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "claims-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false  # HA: one per AZ in production
  enable_dns_hostnames = true

  tags = local.common_tags
}

# ── KMS Key for PHI encryption ─────────────────────────────────────────────
resource "aws_kms_key" "phi_key" {
  description             = "KMS key for PHI field encryption (claims system)"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name       = "claims-phi-key"
    Compliance = "HIPAA"
  })
}

resource "aws_kms_alias" "phi_key_alias" {
  name          = "alias/claims-phi-key"
  target_key_id = aws_kms_key.phi_key.key_id
}

# ── EKS Cluster ───────────────────────────────────────────────────────────
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.0.0"

  cluster_name    = "claims-eks"
  cluster_version = "1.30"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    general = {
      instance_types = ["t3.medium"]
      min_size       = 3
      max_size       = 20
      desired_size   = 3

      labels = {
        role = "general"
      }
    }
  }

  tags = local.common_tags
}

# ── RDS PostgreSQL (Multi-AZ) ─────────────────────────────────────────────
resource "aws_db_instance" "postgres" {
  identifier = "claims-postgres"
  engine     = "postgres"
  engine_version = "16.3"
  instance_class = var.db_instance_class
  allocated_storage = 100
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = aws_kms_key.phi_key.arn   # RDS encrypted with PHI key

  db_name  = "claimsdb"
  username = "claims"
  password = random_password.db_password.result

  multi_az               = true   # HA — synchronous standby replica
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 7
  deletion_protection     = true
  skip_final_snapshot     = false

  performance_insights_enabled = true

  tags = merge(local.common_tags, { Compliance = "HIPAA" })
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "claims-db-subnet-group"
  subnet_ids = module.vpc.private_subnets
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "claims-redis"
  description          = "Redis for claims system (annual limit cache)"

  node_type            = "cache.t4g.medium"
  num_cache_clusters   = 2    # primary + one replica for HA
  engine_version       = "7.0"

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  tags = local.common_tags
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "claims-redis-subnet-group"
  subnet_ids = module.vpc.private_subnets
}

# ── MSK Kafka (domain events) ─────────────────────────────────────────────
resource "aws_msk_cluster" "kafka" {
  cluster_name           = "claims-kafka"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    client_subnets  = module.vpc.private_subnets
    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
    }
  }

  tags = local.common_tags
}

# ── Locals ────────────────────────────────────────────────────────────────
locals {
  common_tags = {
    Project     = "claims-processing"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
