#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# import.sh — One-time script to import existing AWS resources into Terraform
#
# Run this ONCE if you have pre-existing AWS resources (EC2, ECR, IAM, etc.)
# that were created manually and you want Terraform to start managing them.
#
# After running this, use "terraform plan" and "terraform apply" for all
# future infrastructure changes — never touch resources manually in the
# AWS console again (Terraform won't know about manual changes).
#
# Usage:
#   cd terraform/
#   bash import.sh
# ──────────────────────────────────────────────────────────────────────────────
set -e

cd "$(dirname "$0")"

echo "==> Initialising Terraform (downloads AWS provider plugin)..."
terraform init

echo "==> Importing ECR repository (Docker image registry)..."
terraform import aws_ecr_repository.stock_portal stock-portal

echo "==> Importing IAM role (permissions the EC2 uses to talk to AWS)..."
terraform import aws_iam_role.stock_portal stock-portal-ec2-role

echo "==> Importing IAM policy attachment (ECR read access)..."
terraform import aws_iam_role_policy_attachment.ecr_readonly \
  stock-portal-ec2-role/arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

echo "==> Importing IAM instance profile (attaches the role to EC2)..."
terraform import aws_iam_instance_profile.stock_portal stock-portal-profile

echo "==> Importing security group (EC2 firewall rules)..."
terraform import aws_security_group.stock_portal sg-0e8c352ee721cbbb6

echo "==> Importing EC2 instance (the virtual machine running the portal)..."
terraform import aws_instance.stock_portal i-0e84f65e1c1b066ef

echo "==> Importing Elastic IP (permanent public IP address)..."
terraform import aws_eip.stock_portal eipalloc-06d7d05e72b9a7976

echo "==> Importing EIP association (link between Elastic IP and EC2)..."
terraform import aws_eip_association.stock_portal eipassoc-0c001594425a8cbc6

echo ""
echo "==> All imports done. Running plan to check for any drift between"
echo "    the Terraform config and the live AWS state..."
terraform plan
