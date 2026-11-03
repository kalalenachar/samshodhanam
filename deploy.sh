#!/bin/bash
set -e

# =============================================================================
# CONFIGURATION
# Customize these variables or export them in your environment before running:
#   DOMAIN="example.com" USER_NAME="myuser" ./deploy.sh
# =============================================================================
DOMAIN="${DOMAIN:-localhost}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
USER_NAME="${USER_NAME:-$SUDO_USER}"
USER_NAME="${USER_NAME:-$USER}"
APP_NAME="${APP_NAME:-open-samsho}"
STT_BACKEND="$APP_DIR/apps/sanskrit_stt/backend"
STT_SERVICE="${APP_NAME}-stt"

echo "========================================================"
echo "   OPEN-SAMSHO - QUICK DEPLOY"
echo "========================================================"
echo "App Name:  $APP_NAME"
echo "Domain:    $DOMAIN"
echo "Directory: $APP_DIR"
echo "User:      $USER_NAME"
echo "========================================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (or use sudo)"
  exit 1
fi

# 1. Update System & Python Dependencies
echo "[1/5] Updating system audio libraries & Python dependencies..."
apt-get update -qq && apt-get install -y ffmpeg libsndfile1
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install gunicorn vidyut chanda sandhi
sudo -u $USER_NAME "$VENV_DIR/bin/pip" install sanskrit-parser --no-deps

# 1b. Install STT Client & Bot Dependencies
if [ -f "$STT_BACKEND/requirements.txt" ]; then
    echo "[1b] Installing Sanskrit STT client dependencies..."
    sudo -u $USER_NAME "$VENV_DIR/bin/pip" install --no-cache-dir -r "$STT_BACKEND/requirements.txt"
fi

# 1c. Compile Database if missing
if [ ! -f "$APP_DIR/db/vyakarana_kosha.db" ]; then
  if [ -f "$APP_DIR/data-master.zip" ]; then
    echo "Database file missing. Compiling Vyakarana & Kosha database..."
    sudo -u $USER_NAME "$VENV_DIR/bin/python" "$APP_DIR/db/compile_vyakarana_kosha.py"
  else
    echo "========================================================"
    echo "WARNING: db/vyakarana_kosha.db is missing and data-master.zip was not found!"
    echo "Please upload 'data-master.zip' to the project root: $APP_DIR"
    echo "Then run compilation manually:"
    echo "  sudo -u $USER_NAME venv/bin/python db/compile_vyakarana_kosha.py"
    echo "========================================================"
  fi
fi

# 1d. Extract Rigveda Database if missing or newer archive exists
if [ -f "$APP_DIR/apps/rigveda/rigveda.db.gz" ]; then
    if [ ! -f "$APP_DIR/apps/rigveda/rigveda.db" ] || [ "$APP_DIR/apps/rigveda/rigveda.db.gz" -nt "$APP_DIR/apps/rigveda/rigveda.db" ]; then
        echo "Extracting updated Rigveda archive database..."
        sudo -u $USER_NAME gzip -d -k -f "$APP_DIR/apps/rigveda/rigveda.db.gz"
    fi
fi


# 2. Set up Samshodhana STT Systemd Service
echo "[2/5] Setting up Samshodhana STT systemd service..."
SERVICE_FILE="$STT_BACKEND/samshodhana-stt.service"

# Update template paths in service file dynamically
sed -e "s|{{APP_DIR}}|$APP_DIR|g" -e "s|{{USER_NAME}}|$USER_NAME|g" -e "s|{{VENV_DIR}}|$VENV_DIR|g" -e "s|/home/ubuntu/Samshodhanam|$APP_DIR|g" "$SERVICE_FILE" > /etc/systemd/system/${STT_SERVICE}.service
chmod 644 /etc/systemd/system/${STT_SERVICE}.service

systemctl daemon-reload
systemctl enable $STT_SERVICE
systemctl restart $STT_SERVICE

echo "Samshodhana STT service status:"
systemctl is-active $STT_SERVICE && echo "✅ Running on port 8091 (internal)" || echo "❌ Failed to start — check: journalctl -u $STT_SERVICE -n 30"

# 2b. Set up Samshodhana Telegram Bot Systemd Service & Auto-Start
echo "[2b] Setting up Samshodhana Telegram Bot service & auto-start..."
BOT_SERVICE="${APP_NAME}-telegram-bot"
BOT_SERVICE_FILE="$STT_BACKEND/samshodhana-telegram-bot.service"

pkill -f "telegram_bot.py" || true
sleep 1

if [ -f "$BOT_SERVICE_FILE" ]; then
    sed -e "s|{{APP_DIR}}|$APP_DIR|g" -e "s|{{USER_NAME}}|$USER_NAME|g" -e "s|{{VENV_DIR}}|$VENV_DIR|g" -e "s|/home/ubuntu/Samshodhanam|$APP_DIR|g" "$BOT_SERVICE_FILE" > /etc/systemd/system/${BOT_SERVICE}.service
    chmod 644 /etc/systemd/system/${BOT_SERVICE}.service
    systemctl daemon-reload
    systemctl enable $BOT_SERVICE
    systemctl restart $BOT_SERVICE || true
    echo "Samshodhana Telegram Bot service status:"
    systemctl is-active $BOT_SERVICE && echo "✅ Telegram Bot running as service" || echo "⚠️ Bot service failed — check: journalctl -u $BOT_SERVICE -n 30"
else
    sudo -u $USER_NAME "$VENV_DIR/bin/python" "$STT_BACKEND/bot_manager.py" --ensure-running || true
fi

# 2c. Set up Samshodhana Telegram OCR Bot Systemd Service & Auto-Start
echo "[2c] Setting up Samshodhana Telegram OCR Bot service & auto-start..."
OCR_BOT_SERVICE="${APP_NAME}-ocr-bot"
OCR_BOT_SERVICE_FILE="$APP_DIR/apps/ocr_bot/samshodhana-ocr-bot.service"

pkill -f "apps/ocr_bot/run_bot.py" || true
sleep 1

if [ -f "$OCR_BOT_SERVICE_FILE" ]; then
    sed -e "s|{{APP_DIR}}|$APP_DIR|g" -e "s|{{USER_NAME}}|$USER_NAME|g" -e "s|{{VENV_DIR}}|$VENV_DIR|g" -e "s|/home/ubuntu/Samshodhanam|$APP_DIR|g" "$OCR_BOT_SERVICE_FILE" > /etc/systemd/system/${OCR_BOT_SERVICE}.service
    chmod 644 /etc/systemd/system/${OCR_BOT_SERVICE}.service
    systemctl daemon-reload
    systemctl enable $OCR_BOT_SERVICE
    systemctl restart $OCR_BOT_SERVICE || true
    echo "Samshodhana Telegram OCR Bot service status:"
    systemctl is-active $OCR_BOT_SERVICE && echo "✅ Telegram OCR Bot running as service" || echo "⚠️ OCR Bot service failed — check: journalctl -u $OCR_BOT_SERVICE -n 30"
else
    sudo -u $USER_NAME "$VENV_DIR/bin/python" "$APP_DIR/apps/ocr_bot/run_bot.py" &
fi



# 3. Patch Nginx to proxy /ws/stt/ → 127.0.0.1:8091 (no new port needed)
echo "[3/5] Patching Nginx for /ws/stt/ WebSocket proxy..."
NGINX_CONF="/etc/nginx/sites-available/${APP_NAME}"

# Only add the ws proxy block if not already present
if ! grep -q "location /ws/stt/" "$NGINX_CONF"; then
    # Insert before the closing } of the server block
    sed -i 's|^\}$|    # Samshodhana STT WebSocket proxy\n    location /ws/stt/ {\n        proxy_pass http://127.0.0.1:8091/ws/;\n        proxy_http_version 1.1;\n        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection "upgrade";\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_read_timeout 3600s;\n        proxy_send_timeout 3600s;\n    }\n}|' "$NGINX_CONF"
    echo "✅ Nginx /ws/stt/ proxy block added"
else
    echo "✅ Nginx /ws/stt/ proxy block already present"
fi

# Add static asset location blocks if not present
if ! grep -q "location /static/" "$NGINX_CONF"; then
    sed -i 's|^\}$|    # Direct static assets (prevents 502 Bad Gateway and speeds up CSS/JS)\n    location /static/ {\n        alias '"$APP_DIR"'/static/;\n        expires 7d;\n    }\n    location /admin/static/ {\n        alias '"$APP_DIR"'/static/;\n        expires 7d;\n    }\n}|' "$NGINX_CONF"
    echo "✅ Nginx direct static asset location blocks added"
fi

# Verify Nginx config and reload
nginx -t && systemctl reload nginx && echo "✅ Nginx reloaded successfully"

# 4. Restart Gunicorn Service
echo "[4/5] Restarting Gunicorn..."
systemctl restart $APP_NAME 2>/dev/null || systemctl restart samshodhanamandiram 2>/dev/null || true

# 5. Restart Nginx
echo "[5/5] Restarting Nginx..."
systemctl restart nginx

echo "========================================================"
echo "DEPLOYMENT UPDATE COMPLETE!"
echo ""
echo "Access URLs:"
echo "  Web App:    https://$DOMAIN/apps/sanskrit_stt/"
echo "  STT Admin:  https://$DOMAIN/apps/sanskrit_stt/admin.html"
echo "  OCR Admin:  https://$DOMAIN/apps/ocr_bot/admin.html"
echo "  STT WS:     wss://$DOMAIN/ws/stt/ (via Nginx proxy)"

echo ""
echo "No new ports needed — STT is proxied through Nginx on port 443!"
echo "========================================================"


