# bc-api

Backend privado de BigCapital. FastAPI + PostgreSQL, corre en el VPS Hetzner detrás de Caddy.

- **Producción**: https://api.bigcapital.cl (requiere DNS A record activo)
- **Docs interactivas**: https://api.bigcapital.cl/docs
- **VPS**: `178.105.91.29` puerto interno `:8011` (`:8001` lo usa otro Python)
- **Service**: `systemctl status bc-api` · logs: `journalctl -u bc-api -f`
- **Auth**: bearer JWT (super admin only, audiencia "tools internas")

## Stack

| Componente | Tecnología |
|---|---|
| Web framework | FastAPI 0.115 |
| Server WSGI | uvicorn (2 workers) bajo systemd |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| DB | PostgreSQL 16 |
| Reverse proxy + TLS | Caddy (Let's Encrypt automático) |
| Deploy | GitHub Actions → ssh + git pull + migrations + systemctl restart |
| Tests | pytest |

## Endpoints (resumen)

| Método | Path | Para qué |
|---|---|---|
| `POST` | `/auth/login` | Email+password → JWT bearer |
| `GET` | `/auth/me` | Quién soy (requiere bearer) |
| `GET` | `/proyectos` | Listado con filtros (q, activo, fase, comuna) |
| `POST` | `/proyectos` | Crear |
| `GET` | `/proyectos/{id}` | Detalle (con unidades + imágenes + docs) |
| `PUT` | `/proyectos/{id}` | Actualizar |
| `DELETE` | `/proyectos/{id}` | Eliminar |
| `GET` | `/proyectos/{id}/imagenes` | Listar fotos |
| `POST` | `/proyectos/{id}/imagenes` | Subir 1+ fotos (multipart, con `categoria` + `es_principal`) |
| `PATCH` | `/proyectos/{id}/imagenes/{img_id}` | Cambiar categoría / marcar principal |
| `DELETE` | `/proyectos/{id}/imagenes/{img_id}` | Eliminar foto |
| `GET` | `/proyectos/{id}/unidades` | Listar |
| `POST` | `/proyectos/{id}/unidades` | Crear |
| `PUT/DELETE` | `/proyectos/{id}/unidades/{uid}` | Editar / eliminar |
| `GET` | `/proyectos/{id}/unidades/excel/template?con_datos=true` | Descargar `.xlsx` (vacío o con datos actuales) |
| `POST` | `/proyectos/{id}/unidades/excel/upload` | Subir `.xlsx` (upsert por `numero_depto`) |
| `GET` | `/health` | Healthcheck |

Las imágenes se sirven en `/uploads/<proyecto_id>/<uuid>.<ext>` (FastAPI dev; Caddy las puede servir directo en prod).

## Setup local (dev)

```bash
git clone git@github.com:nicolassoto-art/bc-api.git
cd bc-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # editar DATABASE_URL
docker run -d --name pg-bcapi -e POSTGRES_USER=bcapi -e POSTGRES_PASSWORD=bcapi -e POSTGRES_DB=bcapi -p 5432:5432 postgres:16-alpine
alembic upgrade head
python scripts/create_admin.py nicolas.soto@bigcapital.cl 'tu-pass'
python scripts/seed_from_frontend.py  # importa pinar-1 y pinar-2 del frontend
uvicorn app.main:app --reload --port 8001
open http://localhost:8001/docs
```

## Primera instalación en el VPS

1. **DNS** en Cloudflare: agregar `A api.bigcapital.cl → 178.105.91.29` (proxy off, gris)
2. **Crear repo `bc-api` en GitHub** y agregar la deploy key
3. **SSH al VPS** y correr:
   ```bash
   sudo REPO_URL=git@github.com:nicolassoto-art/bc-api.git bash <(curl -fsSL https://raw.githubusercontent.com/nicolassoto-art/bc-api/main/scripts/vps_install.sh)
   ```
4. **Crear usuario admin**:
   ```bash
   sudo -u bcapi /opt/bc-api/.venv/bin/python /opt/bc-api/scripts/create_admin.py nicolas.soto@bigcapital.cl 'micontraseña'
   ```
5. **Importar datos iniciales** (opcional, una vez):
   ```bash
   sudo scp /Users/nicolas/Documents/Claude/Projects/Herramientas\ BC/src/stock-interno/data/seed-pinar.js bigcapital-vps:/tmp/seed-pinar.js
   ssh bigcapital-vps "sudo -u bcapi /opt/bc-api/.venv/bin/python /opt/bc-api/scripts/seed_from_frontend.py /tmp/seed-pinar.js"
   ```
6. **Smoke test**:
   ```bash
   curl https://api.bigcapital.cl/health
   open https://api.bigcapital.cl/docs
   ```

## Deploy automático (GitHub Actions)

Configurar **GitHub Secrets** en el repo `bc-api`:

| Secret | Valor |
|---|---|
| `VPS_HOST` | `178.105.91.29` |
| `VPS_USER` | `root` (o `deploy` si creás usuario sudoer) |
| `VPS_SSH_KEY` | Contenido completo de la clave privada SSH (recomendado: clave dedicada **distinta** a `~/.ssh/bigcapital_vps`, solo para CI) |

A partir de ahí: cada `git push` a `main` corre `.github/workflows/deploy.yml` y el deploy es automático.

## Operación

| Acción | Comando |
|---|---|
| Estado servicio | `systemctl status bc-api` |
| Logs en vivo | `journalctl -u bc-api -f` |
| Reiniciar | `systemctl restart bc-api` |
| Editar config | `sudo vim /opt/bc-api/.env && systemctl restart bc-api` |
| Backup DB | `sudo -u postgres pg_dump bcapi > bcapi-$(date +%F).sql` |
| Backup uploads | `tar czf uploads-$(date +%F).tar.gz /opt/bc-api/uploads` |

## Seguridad

- `/opt/bc-api/.env` tiene `chmod 600` y es solo del usuario `bcapi`
- Postgres escucha solo en `localhost` (no expuesto)
- JWT secret se genera con `openssl rand -hex 32` en la primera instalación
- CORS restringido a `https://herramientas.bigcapital.cl` (no `*`)
- Caddy hace upgrade automático a HTTPS con Let's Encrypt

## Pendiente / Roadmap

- [ ] Audit log de cambios (quién editó qué)
- [ ] Rate limiting por IP
- [ ] Endpoint `/proyectos/{id}/documentos` upload
- [ ] Refresh tokens (hoy expira a las 24h y hay que re-loguear)
- [ ] Tests E2E del flow Excel upload
- [ ] Endpoint público read-only para vista de brokers (`GET /public/proyectos`)
