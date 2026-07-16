# ──────────────────────────────────────────────────────────────────────────────
# ec2.tf — Compute, networking, and storage
#
# Resources defined here:
#   - Security Group  : firewall rules for the EC2 instance
#   - EC2 Instance    : the virtual machine running the portal
#   - Elastic IP      : permanent public IP (survives stop/start)
#   - EIP Association : binds the Elastic IP to the EC2 instance
#
# Traffic flow:
#   Internet → Cloudflare (SSL) → Elastic IP → Nginx (port 80)
#                                             → Docker container (port 8501)
# ──────────────────────────────────────────────────────────────────────────────

# Security Group — EC2 firewall.
# Controls which ports accept inbound traffic and what outbound traffic is allowed.
resource "aws_security_group" "stock_portal" {
  name        = "stock-portal-sg"
  description = "Stock portal access"

  # The default VPC in ap-south-1. We use the default to keep networking simple.
  vpc_id = "vpc-0eb73af5cc8c2c196"

  ingress {
    description = "SSH - for manual access and debugging"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP - Cloudflare terminates SSL and forwards plain HTTP here"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS - kept open for direct HTTPS access if needed"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Streamlit - direct access to the app, bypassing Nginx"
    from_port   = 8501
    to_port     = 8501
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow all outbound traffic — needed for yum installs, ECR pulls, Yahoo Finance API calls, etc.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "stock-portal-sg"
  }
}

# EC2 Instance — the virtual machine that runs the portal.
resource "aws_instance" "stock_portal" {
  # Amazon Linux 2023 AMI (ap-south-1). If you ever need to replace this
  # instance, use the same AMI or find the latest AL2023 AMI for ap-south-1.
  ami = "ami-0f9235932f10668d4"

  # t3.micro = 2 vCPUs, 1 GB RAM. Enough for the portal + cron jobs.
  # Upgrade to t3.small (2 GB) if the portal feels slow under load.
  instance_type = "t3.micro"

  # SSH key pair name (created manually in AWS). The private key is at
  # ~/.ssh/stock-portal-key.pem — keep it safe, it can't be recovered.
  key_name = "stock-portal-key"

  # Subnet inside the default VPC. ap-south-1a availability zone.
  subnet_id = "subnet-096c527e723807074"

  vpc_security_group_ids = [aws_security_group.stock_portal.id]

  # Attaches the IAM role so the instance can pull from ECR and read SSM secrets.
  iam_instance_profile = aws_iam_instance_profile.stock_portal.name

  # Bootstrap script — runs automatically on the very first boot of a new instance.
  # Installs Docker, Nginx, cronie; configures everything; starts the portal container.
  # See user_data.sh for the full script and inline comments.
  # NOTE: This does NOT run on the currently live instance — only on a fresh launch.
  user_data = file("${path.module}/user_data.sh")

  root_block_device {
    volume_size           = 8    # GB — enough for OS + Docker images
    volume_type           = "gp3"
    delete_on_termination = true # disk is deleted if the instance is terminated
  }

  # user_data only executes on first boot. If we update user_data.sh, Terraform
  # would normally try to replace the instance. ignore_changes prevents that —
  # the updated script will apply naturally the next time a fresh instance is launched.
  lifecycle {
    ignore_changes = [user_data]
  }

  tags = {
    Name = "stock-portal"
  }
}

# Elastic IP — a permanent public IP address that stays the same even if the
# EC2 instance is stopped, started, or replaced. alphavest.in's DNS points here.
resource "aws_eip" "stock_portal" {
  domain = "vpc"

  tags = {
    Name = "stock-portal-eip"
  }
}

# Binds the Elastic IP to the EC2 instance.
# If you ever replace the instance, re-apply to re-attach the same IP.
resource "aws_eip_association" "stock_portal" {
  instance_id   = aws_instance.stock_portal.id
  allocation_id = aws_eip.stock_portal.id
}
