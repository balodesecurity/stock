#!/bin/bash
# Run this ONCE to import existing AWS resources into Terraform state.
# After this, use terraform plan / apply for all future changes.
set -e

cd "$(dirname "$0")"

echo "==> Initialising Terraform..."
terraform init

echo "==> Importing ECR repository..."
terraform import aws_ecr_repository.stock_portal stock-portal

echo "==> Importing IAM role..."
terraform import aws_iam_role.stock_portal stock-portal-ec2-role

echo "==> Importing IAM policy attachment..."
terraform import aws_iam_role_policy_attachment.ecr_readonly \
  stock-portal-ec2-role/arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

echo "==> Importing IAM instance profile..."
terraform import aws_iam_instance_profile.stock_portal stock-portal-profile

echo "==> Importing security group..."
terraform import aws_security_group.stock_portal sg-0e8c352ee721cbbb6

echo "==> Importing EC2 instance..."
terraform import aws_instance.stock_portal i-0e84f65e1c1b066ef

echo "==> Importing Elastic IP..."
terraform import aws_eip.stock_portal eipalloc-06d7d05e72b9a7976

echo "==> Importing EIP association..."
terraform import aws_eip_association.stock_portal eipassoc-0c001594425a8cbc6

echo ""
echo "==> All imports done. Running plan to check for drift..."
terraform plan
