# ──────────────────────────────────────────────────────────────────────────────
# variables.tf — All configuration values in one place
#
# This is the only file you should need to edit when:
#   - Moving to a new AWS account
#   - Changing the region
#   - Upgrading the EC2 instance type or AMI
#   - Replacing the SSH key
#
# Usage: values are referenced in other .tf files as var.<name>
# ──────────────────────────────────────────────────────────────────────────────

variable "aws_account_id" {
  description = "AWS account ID. Found in the top-right of the AWS console."
  type        = string
  default     = "782818417773"
}

variable "aws_region" {
  description = "AWS region where all resources are deployed. ap-south-1 = Mumbai."
  type        = string
  default     = "ap-south-1"
}

variable "vpc_id" {
  description = "VPC (Virtual Private Cloud) to deploy into. Using the default VPC in ap-south-1."
  type        = string
  default     = "vpc-0eb73af5cc8c2c196"
}

variable "subnet_id" {
  description = "Subnet inside the VPC. ap-south-1a availability zone."
  type        = string
  default     = "subnet-096c527e723807074"
}

variable "ami_id" {
  description = "Amazon Machine Image for the EC2 instance. This is Amazon Linux 2023 in ap-south-1. To find the latest AL2023 AMI: AWS console → EC2 → AMIs → search 'al2023-ami-2023'."
  type        = string
  default     = "ami-0f9235932f10668d4"
}

variable "instance_type" {
  description = "EC2 instance size. t3.micro = 2 vCPU, 1 GB RAM. Upgrade to t3.small (2 GB) if portal feels slow."
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "Name of the SSH key pair in AWS. Private key file is at ~/.ssh/stock-portal-key.pem."
  type        = string
  default     = "stock-portal-key"
}

variable "ecr_repository_name" {
  description = "Name of the ECR repository that stores the stock-portal Docker image."
  type        = string
  default     = "stock-portal"
}

variable "ssm_secrets_path" {
  description = "SSM Parameter Store path prefix for this app's secrets. The secrets.toml is stored at <path>/secrets-toml."
  type        = string
  default     = "/stock-portal"
}
