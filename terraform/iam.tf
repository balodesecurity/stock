# ──────────────────────────────────────────────────────────────────────────────
# iam.tf — Identity and Access Management (IAM)
#
# IAM controls what the EC2 instance is allowed to do within AWS.
# Without this, the EC2 can't pull Docker images from ECR or read secrets.
#
# Structure:
#   IAM Role -> trusted by EC2 service
#     +-- Policy: ECR read-only        (pull Docker images)
#     +-- Policy: SSM get-parameter    (read secrets.toml at boot)
#   IAM Instance Profile -> attaches the role to the EC2 instance
# ──────────────────────────────────────────────────────────────────────────────

# The role itself — declares that EC2 instances can assume it.
resource "aws_iam_role" "stock_portal" {
  name = "stock-portal-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Grants read-only access to ECR so the EC2 can pull the stock-portal image.
# AWS-managed policy — covers ecr:GetAuthorizationToken, ecr:BatchGetImage, etc.
resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  role       = aws_iam_role.stock_portal.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Grants access to read the secrets.toml stored in SSM Parameter Store.
# Scoped to the app's SSM path so this role can't read any other app's secrets.
# The secrets.toml holds Google OAuth credentials for the portal login.
resource "aws_iam_role_policy" "ssm_secrets" {
  name = "stock-portal-ssm-secrets"
  role = aws_iam_role.stock_portal.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = "arn:aws:ssm:${var.aws_region}:${var.aws_account_id}:parameter${var.ssm_secrets_path}/*"
    }]
  })
}

# Instance profile is the "wrapper" that lets an EC2 instance carry the role.
# You attach a profile to EC2, not a role directly — this is an AWS requirement.
resource "aws_iam_instance_profile" "stock_portal" {
  name = "stock-portal-profile"
  role = aws_iam_role.stock_portal.name
}
