#!/bin/bash
set -e

# ── Packages ──────────────────────────────────────────────────────────────────
yum install -y docker nginx cronie
systemctl enable docker nginx crond
systemctl start docker nginx crond
usermod -aG docker ec2-user

# ── Nginx config ──────────────────────────────────────────────────────────────
cat > /etc/nginx/conf.d/stock-portal.conf << 'NGINX'
server {
    listen 80;
    server_name alphavest.in www.alphavest.in;

    root /usr/share/nginx/html;

    location = /og-preview.html {
        default_type text/html;
    }

    location / {
        if ($http_user_agent ~* "(WhatsApp|facebookexternalhit|Twitterbot|LinkedInBot|Slackbot|TelegramBot|Discordbot)") {
            rewrite ^ /og-preview.html last;
        }

        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
NGINX

rm -f /etc/nginx/conf.d/default.conf
systemctl reload nginx

# ── OG preview page ───────────────────────────────────────────────────────────
cat > /usr/share/nginx/html/og-preview.html << 'OGHTML'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AlphaVest — Indian Stock Analysis</title>
  <meta property="og:title" content="AlphaVest — Indian Stock Analysis">
  <meta property="og:description" content="Deep-dive analysis on 670+ Indian equities — 10-year financials, SSGR, FCF &amp; live market data in one place. Private platform for long-term investors.">
  <meta property="og:url" content="https://alphavest.in">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="AlphaVest">
  <meta name="description" content="Deep-dive analysis on 670+ Indian equities — 10-year financials, SSGR, FCF &amp; live market data in one place.">
</head>
<body>
  <script>window.location.href = 'https://alphavest.in';</script>
</body>
</html>
OGHTML

# ── Cron scripts ──────────────────────────────────────────────────────────────
mkdir -p /home/ec2-user/crons /home/ec2-user/logs

cat > /home/ec2-user/crons/cron_sync_companies.sh << 'CRON'
#!/bin/bash
docker exec stock-portal python /app/stock/discover_new_companies.py >> /home/ec2-user/logs/discover_new_companies_cron.log 2>&1
CRON

cat > /home/ec2-user/crons/cron_update_prices.sh << 'CRON'
#!/bin/bash
docker exec stock-portal python /app/stock/fetch_market_data.py -i yahoo-daily-change >> /home/ec2-user/logs/update_prices_cron.log 2>&1
CRON

cat > /home/ec2-user/crons/cron_update_fundamentals.sh << 'CRON'
#!/bin/bash
docker exec stock-portal python /app/stock/fetch_market_data.py -i yahoo-price-and-recent-quarter >> /home/ec2-user/logs/update_fundamentals_cron.log 2>&1
docker exec stock-portal python /app/stock/compute_growth_metrics.py >> /home/ec2-user/logs/update_fundamentals_cron.log 2>&1
CRON

chmod +x /home/ec2-user/crons/*.sh
chown -R ec2-user:ec2-user /home/ec2-user/crons /home/ec2-user/logs

# ── Crontab for ec2-user ──────────────────────────────────────────────────────
crontab -u ec2-user - << 'CRONTAB'
# AlphaVest cron jobs (all times UTC; IST = UTC+5:30)

# Sync new companies — 11:00 AM IST = 05:30 UTC, daily
30 5 * * * /home/ec2-user/crons/cron_sync_companies.sh

# Hourly price update — 9 AM–3 PM IST = 03:30–09:30 UTC, Mon–Fri
30 3,4,5,6,7,8,9 * * 1-5 /home/ec2-user/crons/cron_update_prices.sh

# Fundamentals + derived metrics — 12:00 PM IST = 06:30 UTC, Mon–Fri
30 6 * * 1-5 /home/ec2-user/crons/cron_update_fundamentals.sh
CRONTAB

# ── Secrets from SSM ──────────────────────────────────────────────────────────
mkdir -p /home/ec2-user/.streamlit
aws ssm get-parameter \
  --name "/stock-portal/secrets-toml" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text \
  --region ap-south-1 > /home/ec2-user/.streamlit/secrets.toml
chown -R ec2-user:ec2-user /home/ec2-user/.streamlit

# ── Pull image and start container ────────────────────────────────────────────
aws ecr get-login-password --region ap-south-1 \
  | docker login --username AWS --password-stdin \
      782818417773.dkr.ecr.ap-south-1.amazonaws.com

docker pull 782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal:latest

docker run -d \
  --name stock-portal \
  --restart unless-stopped \
  -p 8501:8501 \
  -v /home/ec2-user/derived_metrics_analysis.db:/app/derived_metrics_analysis.db \
  -v /home/ec2-user/.streamlit/secrets.toml:/root/.streamlit/secrets.toml \
  782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal:latest
