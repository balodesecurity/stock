resource "aws_security_group" "stock_portal" {
  name        = "stock-portal-sg"
  description = "Stock portal access"
  vpc_id      = "vpc-0eb73af5cc8c2c196"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Streamlit"
    from_port   = 8501
    to_port     = 8501
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

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

resource "aws_instance" "stock_portal" {
  ami                    = "ami-0f9235932f10668d4"
  instance_type          = "t3.micro"
  key_name               = "stock-portal-key"
  subnet_id              = "subnet-096c527e723807074"
  vpc_security_group_ids = [aws_security_group.stock_portal.id]
  iam_instance_profile   = aws_iam_instance_profile.stock_portal.name

  # Runs on first boot only when launching a fresh instance.
  # Does not affect the currently running instance.
  user_data = file("${path.module}/user_data.sh")

  root_block_device {
    volume_size           = 8
    volume_type           = "gp3"
    delete_on_termination = true
  }

  # user_data only runs on first boot — ignore config changes so Terraform
  # doesn't try to replace the running instance when user_data is updated.
  lifecycle {
    ignore_changes = [user_data]
  }

  tags = {
    Name = "stock-portal"
  }
}

resource "aws_eip" "stock_portal" {
  domain = "vpc"

  tags = {
    Name = "stock-portal-eip"
  }
}

resource "aws_eip_association" "stock_portal" {
  instance_id   = aws_instance.stock_portal.id
  allocation_id = aws_eip.stock_portal.id
}
