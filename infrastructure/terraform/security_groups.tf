/**
 * Security Groups — claims processing system
 *
 * Principle of least privilege:
 *   - Database and cache ports are only reachable from EKS worker nodes.
 *   - The ALB is the only resource with inbound internet access (443/80).
 *   - All outbound traffic is allowed by default (AWS default egress rule).
 */

# ── RDS PostgreSQL ─────────────────────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "claims-rds-sg"
  description = "Allow PostgreSQL (5432) only from EKS worker nodes"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "PostgreSQL from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  # Restrict egress to VPC CIDR — RDS should not initiate outbound connections
  egress {
    description = "Allow all egress within VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  tags = merge(local.common_tags, {
    Name = "claims-rds-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ── ElastiCache Redis ──────────────────────────────────────────────────────────

resource "aws_security_group" "redis" {
  name        = "claims-redis-sg"
  description = "Allow Redis (6379) only from EKS worker nodes"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "Redis from EKS nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  egress {
    description = "Allow all egress within VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  tags = merge(local.common_tags, {
    Name = "claims-redis-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ── MSK Kafka ──────────────────────────────────────────────────────────────────

resource "aws_security_group" "kafka" {
  name        = "claims-kafka-sg"
  description = "Allow Kafka broker ports (9092 PLAINTEXT, 9094 TLS) from EKS worker nodes only"
  vpc_id      = module.vpc.vpc_id

  # Plaintext — disabled in production (TLS enforced at MSK cluster level)
  ingress {
    description     = "Kafka PLAINTEXT from EKS nodes"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  # TLS broker port
  ingress {
    description     = "Kafka TLS from EKS nodes"
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  # ZooKeeper — only needed for MSK admin, not application pods
  ingress {
    description     = "ZooKeeper from EKS nodes (admin only)"
    from_port       = 2181
    to_port         = 2181
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  egress {
    description = "Allow all egress within VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  tags = merge(local.common_tags, {
    Name = "claims-kafka-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ── Application Load Balancer ──────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "claims-alb-sg"
  description = "Allow HTTPS (443) and HTTP (80) from the internet"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTP is accepted so NGINX can redirect it to HTTPS (301)
  ingress {
    description = "HTTP redirect from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # ALB must be able to forward traffic to EKS nodes on the NodePort range
  egress {
    description     = "Forward to EKS nodes"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [module.eks.node_security_group_id]
  }

  tags = merge(local.common_tags, {
    Name = "claims-alb-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ── Allow ALB → EKS nodes ──────────────────────────────────────────────────────
# Added as a separate rule to avoid circular dependency between alb and node SGs.

resource "aws_security_group_rule" "eks_nodes_from_alb" {
  description              = "Allow ALB to reach EKS node ports"
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = module.eks.node_security_group_id
  source_security_group_id = aws_security_group.alb.id
}
