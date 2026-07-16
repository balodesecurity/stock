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

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  role       = aws_iam_role.stock_portal.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy" "ssm_secrets" {
  name = "stock-portal-ssm-secrets"
  role = aws_iam_role.stock_portal.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = "arn:aws:ssm:ap-south-1:782818417773:parameter/stock-portal/*"
    }]
  })
}

resource "aws_iam_instance_profile" "stock_portal" {
  name = "stock-portal-profile"
  role = aws_iam_role.stock_portal.name
}
