#!/usr/bin/env bash
# bc-api · install / upgrade script para correr en el VPS como root.
#
# Idempotente: se puede correr varias veces sin romper nada.
# Lo que hace:
#   1. Instala Postgres + dependencias del sistema
#   2. Clona/actualiza repo en /opt/bc-api
#   3. Crea venv + instala requirements
#   4. Crea DB + usuario Postgres si no existen
#   5. Corre migrations
#   6. Instala systemd unit bc-api.service
#   7. Configura Caddy con api.bigcapital.cl
#
# Antes de la primera corrida:
#   - Definir REPO_URL (abajo)
#   - Tener llave deploy SSH ya cargada con acceso al repo
#   - Tener DNS api.bigcapital.cl → IP del VPS
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/<user>/bc-api/main/scripts/vps_install.sh | sudo bash
#   o bien: sudo bash vps_install.sh

set -euo pipefail

# ──────────────────────────────────────────────────
# CONFIG — ajustar antes de la primera corrida
# ──────────────────────────────────────────────────
REPO_URL="${REPO_URL:-git@github.com:nicolassoto-art/bc-api.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/bc-api}"
SERVICE_USER="${SERVICE_USER:-bcapi}"
DB_NAME="${DB_NAME:-bcapi}"
DB_USER="${DB_USER:-bcapi}"
DB_PASS_FILE="/root/.bcapi-db-pass"  # generado en la primera corrida
DOMAIN="${DOMAIN:-api.bigcapital.cl}"
PORT="${PORT:-8001}"

# ──────────────────────────────────────────────────

log()  { printf "\n\033[1;32m▶\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m⚠\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Hay que correr como root"

log "1) Instalando dependencias del sistema"
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    postgresql postgresql-contrib \
    libpq-dev build-essential \
    git curl ca-certificates

# Caddy (si no está)
if ! command -v caddy >/dev/null; then
    log "1b) Instalando Caddy"
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
fi

log "2) Usuario de servicio: $SERVICE_USER"
id -u "$SERVICE_USER" &>/dev/null || useradd --system --shell /usr/sbin/nologin --home "$INSTALL_DIR" "$SERVICE_USER"

log "3) Clonar/actualizar repo en $INSTALL_DIR"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" fetch --depth 1 origin main
    git -C "$INSTALL_DIR" reset --hard origin/main
else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
mkdir -p "$INSTALL_DIR/uploads"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

log "4) Venv + dependencias Python"
sudo -u "$SERVICE_USER" bash -lc "
    cd $INSTALL_DIR
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip wheel
    .venv/bin/pip install -r requirements.txt
"

log "5) Postgres: DB + usuario"
if [[ ! -f "$DB_PASS_FILE" ]]; then
    openssl rand -hex 24 > "$DB_PASS_FILE"
    chmod 600 "$DB_PASS_FILE"
fi
DB_PASS=$(cat "$DB_PASS_FILE")

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres createdb "$DB_NAME"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"

log "6) Archivo .env de producción"
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    JWT_SECRET=$(openssl rand -hex 32)
    cat > "$ENV_FILE" <<EOF
DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
JWT_SECRET=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_TTL_HOURS=24
UPLOAD_DIR=$INSTALL_DIR/uploads
MAX_UPLOAD_MB=10
CORS_ORIGINS=https://herramientas.bigcapital.cl
SUPER_ADMINS=nicolas.soto@bigcapital.cl
ENV=production
LOG_LEVEL=INFO
EOF
    chmod 600 "$ENV_FILE"
    chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"
    warn "Generé .env nuevo. Editá si querés cambiar CORS_ORIGINS o SUPER_ADMINS."
else
    log "   .env ya existe, no lo toco."
fi

log "7) Correr migrations"
sudo -u "$SERVICE_USER" bash -lc "cd $INSTALL_DIR && .venv/bin/alembic upgrade head"

log "8) systemd unit bc-api.service"
cat > /etc/systemd/system/bc-api.service <<EOF
[Unit]
Description=bc-api · BigCapital backend (FastAPI)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT --workers 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable bc-api.service
systemctl restart bc-api.service
sleep 2
systemctl is-active --quiet bc-api.service || die "bc-api.service no arrancó. Ver: journalctl -u bc-api -n 50"

log "9) Caddy reverse proxy para $DOMAIN"
CADDY_SNIPPET="/etc/caddy/conf.d/bc-api.caddy"
mkdir -p /etc/caddy/conf.d
cat > "$CADDY_SNIPPET" <<EOF
$DOMAIN {
    encode gzip zstd
    reverse_proxy 127.0.0.1:$PORT {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
    request_body {
        max_size 12MB
    }
    log {
        output file /var/log/caddy/bc-api.log
        format json
    }
}
EOF
# Asegurar que el Caddyfile principal importa los snippets
if [[ -f /etc/caddy/Caddyfile ]] && ! grep -q "import conf.d/\*.caddy" /etc/caddy/Caddyfile; then
    echo "" >> /etc/caddy/Caddyfile
    echo "import conf.d/*.caddy" >> /etc/caddy/Caddyfile
fi
systemctl reload caddy

log "✓ Instalación / actualización completada."
echo
echo "   Servicio:    systemctl status bc-api"
echo "   Logs:        journalctl -u bc-api -f"
echo "   DB pass:     cat $DB_PASS_FILE"
echo "   .env:        $ENV_FILE"
echo "   Health:      curl https://$DOMAIN/health"
echo "   Docs:        https://$DOMAIN/docs"
echo
echo "Próximo paso:"
echo "   sudo -u $SERVICE_USER $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/create_admin.py nicolas.soto@bigcapital.cl <password>"
