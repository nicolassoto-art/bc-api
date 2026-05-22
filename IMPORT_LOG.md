# Registro de imports a bc-api

Tracking de proyectos importados a la DB de producción `bcapi` en el VPS.

## 2026-05-21 · Seed inicial (Pinar 1 + 2)

| Origen | Inmobiliaria | Proyectos | Unidades | Imágenes | Estado |
|---|---|---|---|---|---|
| `seed-pinar.js` del frontend stock-interno | MNK | 2 (pinar-1, pinar-2) | 33 | 47 | ✅ Importado |

**Comando**: `python scripts/seed_from_frontend.py /tmp/seed-pinar.js`

**Notas**: Las imágenes referencian paths relativos (`data/img/pinar-{1,2}/*.png`) del frontend. En la DB se guardó la URL tal cual; cuando el frontend hace switch a la API real, va a leer las imágenes desde el bundle del frontend, no de la API.

---

## 2026-05-21 · Intento Larraín Prieto (JetBroker)

| Resultado | Detalle |
|---|---|
| ❌ No importado | Larraín Prieto **NO aparece** en el scraper de JetBroker |
| Snapshot revisado | `/opt/bigcapital/data/snapshots/snapshot_20260511_021112.json` (11 may 2026) |
| Organizations encontradas (23) | BigCapital, Maestra, Empresas Socovesa, BROKERFY, INMOBILIARIA NORTE VERDE, Gespania, Leben, SOCOVESA SUR, Inmobiliaria Nollagam, INNOVAVISIÓN, INSIGNE, Puerto Capital, Be Growth, DICSA, Vitalia, Krono, Metra, FIRÓ, Sudamericana, Icom, TORINA, Nahmías |

**Hipótesis**: LP usa otro CRM (DD360, Toctoc, propio). No publica en JetBroker.

**Plan B sugerido** (decidir con usuario):
1. Importar otra inmobiliaria que SÍ está (Empresas Socovesa: 14 proyectos · 424 unidades)
2. Scraper específico para sitio web de LP
3. Importar manualmente desde Excel/PDF que tenga el equipo

---

## Próximos imports (TODO)

- [ ] Larraín Prieto — pendiente confirmar fuente
- [ ] Empresas Socovesa (14 proy / 424 uni) — disponible en JetBroker
- [ ] Maestra (14 proy / 1.369 uni)
- [ ] Socovesa Sur (9 proy / 208 uni)

---

## Cómo importar desde el snapshot de JetBroker (referencia)

```bash
# 1. SSH al VPS
ssh -i ~/.ssh/bigcapital_vps root@178.105.91.29

# 2. Encontrar el último snapshot
LATEST=$(ls -t /opt/bigcapital/data/snapshots/*.json | head -1)

# 3. Filtrar por inmobiliaria y convertir a formato bc-api
sudo -u bcapi /opt/bc-api/.venv/bin/python /opt/bc-api/scripts/seed_from_jetbroker.py \
  --snapshot "$LATEST" \
  --organization "Empresas Socovesa"
```

> ⚠ El script `seed_from_jetbroker.py` está pendiente de crear. Cuando se defina la primera inmobiliaria a importar masivamente, se hace en el momento.
