output "instance_id" {
  value = aws_instance.stock_portal.id
}

output "public_ip" {
  value = aws_eip.stock_portal.public_ip
}

output "ecr_repository_url" {
  value = aws_ecr_repository.stock_portal.repository_url
}

output "ssh_command" {
  value = "ssh -i ~/.ssh/stock-portal-key.pem ec2-user@${aws_eip.stock_portal.public_ip}"
}
