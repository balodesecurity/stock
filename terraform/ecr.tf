resource "aws_ecr_repository" "stock_portal" {
  name                 = "stock-portal"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_ecr_lifecycle_policy" "stock_portal" {
  repository = aws_ecr_repository.stock_portal.name

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
