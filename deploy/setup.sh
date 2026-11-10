#!/bin/bash
# Radar — 7/24 gözcü kurulumu (Ubuntu/Debian sunucu)
# Kullanım:
#   curl -fsSL https://raw.githubusercontent.com/krm00/radar/main/deploy/setup.sh | sudo bash
# veya dosyayı sunucuya kopyalayıp:
#   sudo bash setup.sh
#
# Kurulumdan sonra /etc/radar.env dosyasını düzenleyip cron'u başlatın.

set -e

APP_DIR="/opt/radar"
ENV_FILE="/etc/radar.env"
REPO="https://github.com/krm00/radar.git"

echo "== paketler =="
apt-get update -y
apt-get install -y python3 git cron

echo "== kod =="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only || true
else
  git clone --depth 1 "$REPO" "$APP_DIR"
fi

echo "== ortam dosyası =="
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# Radar ortam değişkenleri — doldur ve kaydet
X_BEARER=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NTFY_TOPIC=
EOF
  chmod 600 "$ENV_FILE"
  echo "  $ENV_FILE oluşturuldu — değerleri gir:  sudo nano $ENV_FILE"
fi

echo "== cron (her dakika) =="
CRON_LINE="* * * * * set -a; . $ENV_FILE; set +a; cd $APP_DIR && /usr/bin/python3 notify.py >> /var/log/radar.log 2>&1"
( crontab -l 2>/dev/null | grep -v "radar/notify.py" ; echo "$CRON_LINE" ) | crontab -
systemctl enable --now cron >/dev/null 2>&1 || service cron start || true

touch /var/log/radar.log

echo
echo "Kurulum tamam."
echo "1) Değerleri gir : sudo nano $ENV_FILE"
echo "2) Test et       : set -a; . $ENV_FILE; set +a; cd $APP_DIR && python3 notify.py"
echo "3) Log izle      : tail -f /var/log/radar.log"
