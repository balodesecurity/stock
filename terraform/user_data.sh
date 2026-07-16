#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# user_data.sh — EC2 first-boot bootstrap script
#
# Runs automatically once when a brand-new EC2 instance starts for the first time.
# Sets up everything needed to serve alphavest.in: Docker, Nginx, cron jobs,
# secrets, and the stock-portal container.
#
# To change any paths or config, edit the variables section below — nowhere else.
# ──────────────────────────────────────────────────────────────────────────────
set -e

# ── Configuration (edit here if anything changes) ─────────────────────────────
EC2_USER="ec2-user"
EC2_HOME="/home/${EC2_USER}"
DOMAIN="alphavest.in"
AWS_REGION="ap-south-1"
ECR_ACCOUNT="782818417773"
ECR_IMAGE="${ECR_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/stock-portal:latest"
SSM_PARAM="/stock-portal/secrets-toml"
CONTAINER_NAME="stock-portal"
STREAMLIT_PORT=8501

# Paths on the EC2 host
CRONS_DIR="${EC2_HOME}/crons"
LOGS_DIR="${EC2_HOME}/logs"
STREAMLIT_DIR="${EC2_HOME}/.streamlit"
DB_HOST_PATH="${EC2_HOME}/derived_metrics_analysis.db"
SECRETS_HOST_PATH="${STREAMLIT_DIR}/secrets.toml"

# Paths inside the Docker container (defined by the Dockerfile)
APP_CONTAINER_DIR="/app/stock"
DB_CONTAINER_PATH="/app/derived_metrics_analysis.db"
SECRETS_CONTAINER_PATH="/root/.streamlit/secrets.toml"

# ── Packages ──────────────────────────────────────────────────────────────────
yum install -y docker nginx cronie
systemctl enable docker nginx crond
systemctl start docker nginx crond
usermod -aG docker "${EC2_USER}"

# ── Nginx config ──────────────────────────────────────────────────────────────
# Proxy all traffic to Streamlit. Social media crawlers (WhatsApp, Twitter, etc.)
# get a lightweight OG preview page instead of the full Streamlit app.
cat > /etc/nginx/conf.d/stock-portal.conf << 'NGINX'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER www.DOMAIN_PLACEHOLDER;

    root /usr/share/nginx/html;

    location = /og-preview.html {
        default_type text/html;
    }

    location / {
        if ($http_user_agent ~* "(WhatsApp|facebookexternalhit|Twitterbot|LinkedInBot|Slackbot|TelegramBot|Discordbot)") {
            rewrite ^ /og-preview.html last;
        }

        proxy_pass http://localhost:STREAMLIT_PORT_PLACEHOLDER;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
NGINX

# Replace placeholders with actual values from variables above
sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" /etc/nginx/conf.d/stock-portal.conf
sed -i "s/STREAMLIT_PORT_PLACEHOLDER/${STREAMLIT_PORT}/g" /etc/nginx/conf.d/stock-portal.conf

rm -f /etc/nginx/conf.d/default.conf
systemctl reload nginx

# ── OG preview page ───────────────────────────────────────────────────────────
# Served to social media crawlers so link previews show meaningful metadata.
cat > /usr/share/nginx/html/og-preview.html << 'OGHTML'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AlphaVest - Indian Stock Analysis</title>
  <meta property="og:title" content="AlphaVest - Indian Stock Analysis">
  <meta property="og:description" content="Deep-dive analysis on 670+ Indian equities - 10-year financials, SSGR, FCF &amp; live market data in one place. Private platform for long-term investors.">
  <meta property="og:url" content="DOMAIN_URL_PLACEHOLDER">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="AlphaVest">
  <meta name="description" content="Deep-dive analysis on 670+ Indian equities - 10-year financials, SSGR, FCF &amp; live market data in one place.">
</head>
<body>
  <script>window.location.href = 'DOMAIN_URL_PLACEHOLDER';</script>
</body>
</html>
OGHTML

sed -i "s|DOMAIN_URL_PLACEHOLDER|https://${DOMAIN}|g" /usr/share/nginx/html/og-preview.html

# ── Cron scripts ──────────────────────────────────────────────────────────────
# These scripts run inside the Docker container via "docker exec".
# All output is logged to $LOGS_DIR for debugging.
mkdir -p "${CRONS_DIR}" "${LOGS_DIR}"

cat > "${CRONS_DIR}/cron_sync_companies.sh" << CRON
#!/bin/bash
docker exec ${CONTAINER_NAME} python ${APP_CONTAINER_DIR}/discover_new_companies.py >> ${LOGS_DIR}/discover_new_companies_cron.log 2>&1
CRON

cat > "${CRONS_DIR}/cron_update_prices.sh" << CRON
#!/bin/bash
docker exec ${CONTAINER_NAME} python ${APP_CONTAINER_DIR}/fetch_market_data.py -i yahoo-daily-change >> ${LOGS_DIR}/update_prices_cron.log 2>&1
CRON

cat > "${CRONS_DIR}/cron_update_fundamentals.sh" << CRON
#!/bin/bash
docker exec ${CONTAINER_NAME} python ${APP_CONTAINER_DIR}/fetch_market_data.py -i yahoo-price-and-recent-quarter >> ${LOGS_DIR}/update_fundamentals_cron.log 2>&1
docker exec ${CONTAINER_NAME} python ${APP_CONTAINER_DIR}/compute_growth_metrics.py >> ${LOGS_DIR}/update_fundamentals_cron.log 2>&1
CRON

chmod +x "${CRONS_DIR}"/*.sh
chown -R "${EC2_USER}:${EC2_USER}" "${CRONS_DIR}" "${LOGS_DIR}"

# ── Crontab for ec2-user ──────────────────────────────────────────────────────
# All times are UTC. IST = UTC+5:30.
crontab -u "${EC2_USER}" - << CRONTAB
# AlphaVest cron jobs (all times UTC; IST = UTC+5:30)

# Sync new companies - 11:00 AM IST = 05:30 UTC, daily
30 5 * * * ${CRONS_DIR}/cron_sync_companies.sh

# Hourly price update - 9 AM-3 PM IST = 03:30-09:30 UTC, Mon-Fri
30 3,4,5,6,7,8,9 * * 1-5 ${CRONS_DIR}/cron_update_prices.sh

# Fundamentals + derived metrics - 12:00 PM IST = 06:30 UTC, Mon-Fri
30 6 * * 1-5 ${CRONS_DIR}/cron_update_fundamentals.sh
CRONTAB

# ── Secrets from SSM ──────────────────────────────────────────────────────────
# secrets.toml holds Google OAuth credentials for portal login.
# Stored encrypted in AWS SSM Parameter Store — never in git.
mkdir -p "${STREAMLIT_DIR}"
aws ssm get-parameter \
  --name "${SSM_PARAM}" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text \
  --region "${AWS_REGION}" > "${SECRETS_HOST_PATH}"
chown -R "${EC2_USER}:${EC2_USER}" "${STREAMLIT_DIR}"

# ── Pull image and start container ────────────────────────────────────────────
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
      "${ECR_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker pull "${ECR_IMAGE}"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "${STREAMLIT_PORT}:${STREAMLIT_PORT}" \
  -v "${DB_HOST_PATH}:${DB_CONTAINER_PATH}" \
  -v "${SECRETS_HOST_PATH}:${SECRETS_CONTAINER_PATH}" \
  "${ECR_IMAGE}"
