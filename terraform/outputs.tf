# ──────────────────────────────────────────────────────────────────────────────
# outputs.tf — Values printed after every terraform apply
#
# These are read-only — changing them has no effect on infrastructure.
# Useful for quickly grabbing connection details without going to the AWS console.
# ──────────────────────────────────────────────────────────────────────────────

output "instance_id" {
  description = "EC2 instance ID — use this to find the instance in the AWS console"
  value       = aws_instance.stock_portal.id
}

output "public_ip" {
  description = "Elastic IP address — this is what alphavest.in's DNS points to"
  value       = aws_eip.stock_portal.public_ip
}

output "ecr_repository_url" {
  description = "ECR URL — used in docker push/pull commands and the GitHub Actions workflow"
  value       = aws_ecr_repository.stock_portal.repository_url
}

output "ssh_command" {
  description = "Ready-to-use SSH command to connect to the EC2 instance"
  value       = "ssh -i ~/.ssh/stock-portal-key.pem ec2-user@${aws_eip.stock_portal.public_ip}"
}
