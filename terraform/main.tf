# ──────────────────────────────────────────────────────────────────────────────
# main.tf — Terraform entry point
#
# Declares the AWS provider and required Terraform version.
# All resources are split across ec2.tf, ecr.tf, iam.tf for clarity.
# All configuration values (region, account ID, AMI, etc.) live in variables.tf.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
