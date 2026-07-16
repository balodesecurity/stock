# ──────────────────────────────────────────────────────────────────────────────
# ecr.tf — Elastic Container Registry (ECR)
#
# ECR is AWS's private Docker image registry. The GitHub Actions deploy
# pipeline builds the stock-portal Docker image and pushes it here.
# The EC2 instance then pulls from here to run the portal.
#
# Think of ECR as a private Docker Hub, hosted inside your AWS account.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "stock_portal" {
  name = var.ecr_repository_name

  # MUTABLE means the "latest" tag can be overwritten on each deploy.
  # This is intentional — we always pull the newest "latest" image on EC2.
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    # Vulnerability scanning on every push. Disabled to keep deploys fast;
    # enable this if you want AWS to flag known CVEs in the image layers.
    scan_on_push = false
  }
}

resource "aws_ecr_lifecycle_policy" "stock_portal" {
  repository = aws_ecr_repository.stock_portal.name

  # Automatically delete old images, keeping only the 10 most recent.
  # Each deploy pushes one image — this prevents unbounded storage growth.
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain only the last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
