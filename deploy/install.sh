#!/bin/sh
set -eu

STAGING_DIR=${1:?Usage: install.sh STAGING_DIR PUBLIC_ORIGIN}
PUBLIC_ORIGIN=${2:?Usage: install.sh STAGING_DIR PUBLIC_ORIGIN}

case "$PUBLIC_ORIGIN" in
    https://*) ;;
    *) echo "PUBLIC_ORIGIN must start with https://" >&2; exit 2 ;;
esac

if ! getent passwd telegram-media >/dev/null; then
    useradd --system --home-dir /var/lib/telegram-media --shell /usr/sbin/nologin telegram-media
fi

install -d -o root -g root -m 0755 /opt/telegram-media/app /opt/telegram-media/web
install -d -o telegram-media -g telegram-media -m 0750 \
    /var/lib/telegram-media \
    /var/lib/telegram-media/media \
    /var/lib/telegram-media/thumbnails \
    /var/lib/telegram-media/temp

install -d -o root -g root -m 0755 /opt/telegram-media/app/telegram_media
cp -a "$STAGING_DIR/backend/telegram_media/." /opt/telegram-media/app/telegram_media/
cp "$STAGING_DIR/backend/requirements.txt" /opt/telegram-media/requirements.txt
cp -a "$STAGING_DIR/apps/web/dist/." /opt/telegram-media/web/
chown -R root:root /opt/telegram-media/app /opt/telegram-media/web
chmod -R a=rX,u+w /opt/telegram-media/app /opt/telegram-media/web

python3 -m venv /opt/telegram-media/venv
/opt/telegram-media/venv/bin/python -m pip install --disable-pip-version-check -r /opt/telegram-media/requirements.txt

install -o root -g root -m 0644 "$STAGING_DIR/deploy/telegram-media.service" /etc/systemd/system/telegram-media.service
install -o root -g root -m 0644 "$STAGING_DIR/deploy/nginx-telegram.conf" /etc/nginx/snippets/telegram-media.conf
install -o root -g root -m 0755 "$STAGING_DIR/deploy/telegram-media-configure" /usr/local/sbin/telegram-media-configure

if [ ! -f /etc/telegram-media.env ]; then
    umask 077
    SESSION_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    cat > /etc/telegram-media.env <<EOF
TELEGRAM_ENABLED=false
ADMIN_PASSWORD_HASH=disabled-until-configured
SESSION_SECRET=$SESSION_SECRET
PUBLIC_ORIGIN=$PUBLIC_ORIGIN
COOKIE_PATH=/telegram/
DATA_DIR=/var/lib/telegram-media
WEB_DIR=/opt/telegram-media/web
MAX_FILE_BYTES=2147483648
DISK_RESERVE_BYTES=5368709120
TRASH_RETENTION_DAYS=30
EOF
fi

usermod -a -G telegram-media www-data
systemctl daemon-reload
systemctl enable telegram-media.service
systemctl restart telegram-media.service
