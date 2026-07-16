# ──────────────────────────────────────────────────────────────────────────────
# main.tf — Terraform entry point
#
# Declares the AWS provider and required Terraform version.
# All resources are split across ec2.tf, ecr.tf, iam.tf for clarity.
#
# Region: ap-south-1 (Mumbai) — closest to Indian stock market users.
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
  region = "ap-south-1"
}
