# Fuentes de stock: SJB vs SBC, y qué proyectos NO tocar desde JetBrokers

> Última actualización: 2026-08-12

El catálogo que ven los brokers (`herramientas.bigcapital.cl/paginas/catalogo.html`) y el
sitio público (`bigcapital.cl`) **mezclan dos fuentes**. Confundirlas causa pérdida de
datos, así que conviene tener clara la diferencia antes de correr cualquier importador.

## Las dos fuentes

| | **SJB** | **SBC** |
|---|---|---|
| Origen | JetBrokers, en vivo | bc-api (stock propio) |
| Quién actualiza | JetBrokers/la inmobiliaria | nosotros |
| Aparece en "Stock propio" | ❌ no | ✅ sí |
| Se edita en el editor | ❌ no | ✅ sí |
| Latencia | hasta ~6h (caché KV del worker) | inmediata (si se purga la caché) |

El merge lo hace el Cloudflare Worker (repo `Sitio web BigCapital`,
`cloudflare-worker/worker.js`, función que fusiona ambas listas): **si el proyecto está en
bc-api gana SBC; si no está, queda SJB**. El match es por id normalizado (`jb-<jbid>` ↔
`<jbid>`) con fallback por nombre.

Requisito para que un proyecto cuente como SBC: `extra.publicar_en_catalogo = true`.
Sin ese flag, `/proyectos/public` no lo devuelve (`app/routes/proyectos.py::_is_publicable`)
y el worker lo sigue sirviendo como SJB aunque exista en bc-api.
Se activa con `scripts/patch_publicar_catalogo.py` o desde el editor.

## Pasar un proyecto de SJB a SBC

Para proyectos del **marketplace** de JB (de otra inmobiliaria, listados en nuestro
catálogo de reventa — URL `/marketplace/workview/{id}`, no `/projects/edit/{id}`):

```bash
gh workflow run import-marketplace-workview.yml -f jb_id=<JB_ID> -f dry_run=true   # revisar
gh workflow run import-marketplace-workview.yml -f jb_id=<JB_ID> -f dry_run=false  # importar
```

Después: activar `publicar_en_catalogo`, purgar la caché del worker
(`POST /api/purge-catalog`, lo hace el editor solo al guardar) y validar en el catálogo.

**Ese workflow NO tiene cron a propósito.** Es para el import inicial puntual. Un proyecto
migrado a SBC queda desconectado de JB y lo mantiene el equipo a mano; si se quisiera que
siguiera actualizándose solo desde JB, la respuesta correcta es dejarlo como SJB (fuera de
bc-api), no ponerle un cron.

## ⛔ Proyectos protegidos

`PROYECTOS_PROTEGIDOS` en `app/services/jb_importer.py`. `JBImporter.run()` hace **wipe
completo + reimport**; para estos proyectos eso destruiría el dato bueno:

- **AJ URBANA** — su stock viene del Excel de Drive (sync propio en el VPS,
  `/opt/bigcapital-tests/sync_aj_to_bcapi.py`). Sin el guard se pisaban en loop: el import
  JB borraba el stock y el sync lo restauraba.
- **Marketplace migrados a SBC** — mantención manual del equipo.

El guard corre en `run()` (antes del wipe) y en `scripts/import_detail.py`, que importa la
misma lista para no desincronizarse. Cubierto por `tests/test_proyectos_protegidos.py`.

Para forzar a propósito: `FORCE_IMPORT=1` (acepta también `FORCE_AJ=1` por compatibilidad).

> **Nota histórica**: hasta el 2026-08-12 la lista vivía SOLO en `scripts/import_detail.py`,
> un script suelto. El servicio real —el que usan `import-jb.yml`, `reimport-todos-84.yml`
> y `batch-import-jb.yml`— no la consultaba, así que **en la práctica no protegía nada**.

## Precio Final de JetBrokers ≠ `precio_final_uf`

En el tab Stock del workview, JB muestra `Precio`, `Descuento`, `Bono Pie` y `Precio Final`,
donde:

```
Precio Final(JB) = precio_lista × (1 − descuento) ÷ (1 − bono_pie)
```

Ese valor es la **tasación inflada por bono pie** (esquema "Maestra"), no el precio de
venta. `precio_final_uf` de bc-api es otra cosa: precio neto con descuento,
`lista × (1 − descuento)` (`app/routes/unidades.py::_precio_final`).

**Nunca guardar el "Precio Final" de JB en `precio_final_uf`.** Rompe la invariante
`final ≤ lista` (la cumplen 5.888 de 5.894 unidades), dispara CRÍTICOS en el mega-audit de
precios, e infla el precio del catálogo público.

Si un proyecto realmente usa el esquema donde el bono infla la tasación, la vía correcta es
declararlo en la ficha: `extra.comercial.bono_infla_tasacion = true` (dato comercial, carga
humana — ningún scraper escribe la ficha del proyecto). El cotizador ya sabe aplicar
`÷(1−bono)` cuando ese flag está activo.

⚠️ Trampa: cuando `descuento == bono` (ej. ambos 10%) los factores se cancelan y
`Precio Final == Precio`, dando la falsa impresión de que "en unos proyectos el bono infla
y en otros no". Es siempre la misma fórmula.
