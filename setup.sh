#!/bin/bash
set -e

# =============================================================================
# CONFIGURATION
# Customize these variables or export them in your environment before running:
#   DOMAIN="example.com" USER_NAME="myuser" ./setup.sh
# =============================================================================
DOMAIN="${DOMAIN:-localhost}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
USER_NAME="${USER_NAME:-$SUDO_USER}"
USER_NAME="${USER_NAME:-$USER}"
PORT="${PORT:-8000}"
APP_NAME="${APP_NAME:-open-samsho}"

echo "========================================================"
echo "   OPEN-SAMSHO - SETUP & DEPLOYMENT SCRIPT"
echo "========================================================"
echo "App Name:  $APP_NAME"
echo "Domain:    $DOMAIN"
echo "Directory: $APP_DIR"
echo "User:      $USER_NAME"
echo "Port:      $PORT"
echo "========================================================"

# Check if running as root (required for apt/systemd)
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (or use sudo)"
  exit 1
fi


# =============================================================================
# 1. SYSTEM UPDATES & PACKAGES
# =============================================================================
echo "[1/6] Updating system..."
apt-get update
# Install Python, Nginx, Certbot
apt-get install -y python3-pip python3-venv nginx certbot python3-certbot-nginx

# =============================================================================
# 2. PYTHON ENVIRONMENT
# =============================================================================
echo "[2/6] Setting up Python environment..."
# Fix ownership of app directory first
chown -R $USER_NAME:www-data $APP_DIR

# Create venv if not exists (as the app user)
if [ ! -d "$VENV_DIR" ]; then
    sudo -u $USER_NAME python3 -m venv "$VENV_DIR"
    echo "Created virtual environment."
fi

# Install dependencies
echo "Installing Python dependencies..."
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install gunicorn vidyut chanda sandhi fpdf2 uharfbuzz
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install sanskrit-parser --no-deps

# Extract Rigveda database if missing or newer archive exists
if [ -f "$APP_DIR/apps/rigveda/rigveda.db.gz" ]; then
    if [ ! -f "$APP_DIR/apps/rigveda/rigveda.db" ] || [ "$APP_DIR/apps/rigveda/rigveda.db.gz" -nt "$APP_DIR/apps/rigveda/rigveda.db" ]; then
        echo "Extracting updated Rigveda archive database..."
        sudo -u $USER_NAME gzip -d -k -f "$APP_DIR/apps/rigveda/rigveda.db.gz"
    fi
fi


# =============================================================================
# 3. CONFIGURE GUNICORN (TCP)
# =============================================================================
echo "[3/6] Configuring Gunicorn (TCP Port $PORT)..."
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

cat > $SERVICE_FILE <<EOF
[Unit]
Description=Gunicorn instance to serve Open-Samsho Platform
After=network.target

[Service]
User=$USER_NAME
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
# Bind to localhost:$PORT to avoid file permission issues
# --workers 4 --threads 4: uses multiple processes to bypass the GIL for CPU-bound OCR searches.
# State (ZIP_TASKS and BROWSE_CACHE) is handled via JSON files to allow multi-worker safety
ExecStart=$VENV_DIR/bin/gunicorn --workers 4 --threads 4 --bind 127.0.0.1:$PORT --timeout 600 -m 007 server:application

[Install]
WantedBy=multi-user.target
EOF

# Reload and start
systemctl daemon-reload
systemctl enable $APP_NAME
systemctl restart $APP_NAME

# =============================================================================
# 4. CONFIGURE NGINX
# =============================================================================
echo "[4/6] Configuring Nginx..."

# 1. Cleanup Old Domain (optional migration helper)
OLD_DOMAIN="${OLD_DOMAIN:-}"
if [ -n "$OLD_DOMAIN" ] && [ "$DOMAIN" != "$OLD_DOMAIN" ]; then
    echo "Cleaning up old domain configurations for $OLD_DOMAIN..."
    for conf in /etc/nginx/sites-enabled/* /etc/nginx/sites-available/*; do
        if [ -f "$conf" ] && grep -q "$OLD_DOMAIN" "$conf"; then
            echo "Removing old config file: $conf"
            rm -f "$conf"
        fi
    done
    rm -f /etc/nginx/sites-enabled/$OLD_DOMAIN 2>/dev/null || true
    rm -f /etc/nginx/sites-available/$OLD_DOMAIN 2>/dev/null || true
    
    # Remove old Certbot certificates
    if certbot certificates 2>/dev/null | grep -q "$OLD_DOMAIN"; then
        echo "Deleting SSL certificate for $OLD_DOMAIN..."
        certbot delete --cert-name "$OLD_DOMAIN" --non-interactive 2>/dev/null || true
    fi
fi

NGINX_CONF="/etc/nginx/sites-available/${APP_NAME}"

# Write GLOBAL upload limits into conf.d — this file is NOT touched by Certbot,
# so client_max_body_size and timeouts survive SSL certificate renewals.
cat > /etc/nginx/conf.d/upload_limits.conf <<EOF
# Large file upload support (survives Certbot rewrites)
client_max_body_size 4G;
proxy_read_timeout   600s;
proxy_send_timeout   600s;
proxy_connect_timeout 75s;
EOF

# Write the site config (Certbot will update this with SSL, that's fine)
cat > $NGINX_CONF <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Direct static assets (prevents 502 Bad Gateway and speeds up CSS/JS)
    location /static/ {
        alias $APP_DIR/static/;
        expires 7d;
    }

    location /admin/static/ {
        alias $APP_DIR/static/;
        expires 7d;
    }

    # Main app proxy
    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:$PORT;
    }

    # Samshodhana STT WebSocket proxy (routes wss://domain/ws/stt/ → ws://127.0.0.1:8091)
    location /ws/stt/ {
        proxy_pass http://127.0.0.1:8091/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
EOF

# Enable site
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and restart
nginx -t
systemctl restart nginx

# =============================================================================
# 5. FIREWALL (UFW & IPTABLES)
# =============================================================================
echo "[5/6] Configuring Firewall..."
# Ensure ports are open
ufw allow 'Nginx Full' 2>/dev/null || true
ufw allow 80 2>/dev/null || true
ufw allow 443 2>/dev/null || true
# Oracle Cloud iptables fix
iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
netfilter-persistent save 2>/dev/null || true

# =============================================================================
# 6. SSL CERTIFICATE (CERTBOT)
# =============================================================================
if [ "$DOMAIN" != "localhost" ] && [ "$DOMAIN" != "127.0.0.1" ]; then
    echo "[6/6] Configuring SSL with Certbot for $DOMAIN..."
    certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect --keep-until-expiring || echo "⚠️ SSL configuration skipped or failed. Continuing..."
else
    echo "[6/6] Skipping SSL configuration for local domain ($DOMAIN)."
fi

echo "========================================================"
echo "DEPLOYMENT COMPLETE!"
echo "App URL: https://$DOMAIN"
echo "Admin : https://$DOMAIN/admin"
echo "========================================================"
