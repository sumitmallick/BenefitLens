/**
 * IAM — IRSA roles, ECR repositories, and Secrets Manager
 *
 * IRSA (IAM Roles for Service Accounts) lets Kubernetes pods assume IAM roles
 * without node-level credentials. Each pod gets a projected OIDC token that AWS
 * STS exchanges for temporary credentials scoped to the pod's IAM role.
 */

data "aws_caller_identity" "current" {}

# ── IRSA helper: OIDC provider URL without https:// prefix ────────────────────

locals {
  oidc_provider_url = replace(module.eks.cluster_oidc_issuer_url, "https://", "")
  account_id        = data.aws_caller_identity.current.account_id
}

# ── Claims service pod role (KMS decrypt for PHI) ─────────────────────────────

data "aws_iam_policy_document" "eks_pod_role_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:claims:claims-system"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_pod_role" {
  name               = "claims-eks-pod-role"
  assume_role_policy = data.aws_iam_policy_document.eks_pod_role_assume.json
  description        = "IRSA role for the claims backend pods. Grants KMS access for PHI encryption."

  tags = merge(local.common_tags, {
    Name = "claims-eks-pod-role"
  })
}

data "aws_iam_policy_document" "kms_decrypt" {
  statement {
    sid    = "AllowPHIKeyUsage"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.phi_key.arn]
  }
}

resource "aws_iam_role_policy" "kms_decrypt" {
  name   = "claims-kms-decrypt"
  role   = aws_iam_role.eks_pod_role.id
  policy = data.aws_iam_policy_document.kms_decrypt.json
}

# ── External Secrets Operator role (reads from Secrets Manager) ───────────────

data "aws_iam_policy_document" "external_secrets_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      # ESO controller runs in the external-secrets namespace by default
      values = ["system:serviceaccount:external-secrets:external-secrets"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  name               = "claims-external-secrets-role"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume.json
  description        = "IRSA role for External Secrets Operator. Grants read access to Secrets Manager."

  tags = merge(local.common_tags, {
    Name = "claims-external-secrets-role"
  })
}

data "aws_iam_policy_document" "external_secrets_sm" {
  statement {
    sid    = "AllowSecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
      "secretsmanager:ListSecretVersionIds",
    ]
    # Scope to secrets prefixed with "claims/" to follow least-privilege
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:claims/*",
    ]
  }

  # ESO also needs KMS decrypt if the secret is encrypted with a customer-managed key
  statement {
    sid    = "AllowKMSDecryptForSecrets"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.phi_key.arn]
  }
}

resource "aws_iam_role_policy" "external_secrets_sm" {
  name   = "claims-external-secrets-sm-policy"
  role   = aws_iam_role.external_secrets.id
  policy = data.aws_iam_policy_document.external_secrets_sm.json
}

# ── Secrets Manager — RDS password ────────────────────────────────────────────

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "claims/db-password"
  description             = "RDS PostgreSQL master password for the claims database"
  kms_key_id              = aws_kms_key.phi_key.arn
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name       = "claims-db-password"
    Compliance = "HIPAA"
  })
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

# ── ECR — container image repositories ────────────────────────────────────────

resource "aws_ecr_repository" "backend" {
  name                 = "claims-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    # Scan every image pushed — catches known CVEs at build time
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.phi_key.arn
  }

  tags = merge(local.common_tags, {
    Name      = "claims-backend"
    Component = "backend"
  })
}

resource "aws_ecr_repository" "frontend" {
  name                 = "claims-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.phi_key.arn
  }

  tags = merge(local.common_tags, {
    Name      = "claims-frontend"
    Component = "frontend"
  })
}

# ── ECR lifecycle policies — keep last 10 images ──────────────────────────────

locals {
  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha-"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images older than 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name
  policy     = local.ecr_lifecycle_policy
}
