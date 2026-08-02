# Graph Report - bc-api  (2026-07-31)

## Corpus Check
- 179 files · ~133,851 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1295 nodes · 2257 edges · 154 communities (110 shown, 44 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 86 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5dd0f84f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Rutas admin: informes e inmobiliarias
- Rutas de unidades (deptos)
- Servicio de email y alertas
- Gestion de inmobiliarias (catalogo)
- Reporte de importacion y utilidades scraping
- Infraestructura DB y autenticacion
- Eventos anomalos y workflows batch
- Modulo JBImporter (importador core)
- Autenticacion y esquemas de sesion
- Diagnosticos API JetBrokers
- Descarga y gestion de assets JB
- Modelos de datos (Proyecto, Ticket)
- Exportador Playwright del catalogo JB
- Mapeo de campos JB hacia bc-api
- Vista previa del informe diario
- Ruta de importacion batch (API)
- Generacion HTML del informe diario
- Reporte de actividad del operador
- Diagnostico de scraping en vivo
- Rutas de documentos del proyecto
- Importador desde bigcapital.cl Worker
- Test de paridad DOM (JB vs BC)
- Rutas de imagenes del proyecto
- Verificacion visual con IA (AI Vision)
- Importacion desde export manual JB
- Motor del informe diario de stock
- Calculo de metricas del informe diario
- CI/CD, despliegue y seed inicial
- Test de paridad UI campo a campo
- Motor de alertas de proyecto (criticos)
- Dry-run de importacion (solo lectura)
- Patch no-destructivo de stock
- Scraping de superficies individuales
- Borrado de proyecto antes de reimportar
- Configuracion de la aplicacion (Settings)
- Debug exhaustivo de proyectos
- CLI de importacion JetBrokers
- Listado de proyectos JetBrokers
- Reimportacion de proyectos multibloque
- Test visual: capturas JB vs BC
- Permisos de acceso a Stock/Worker
- Links al editor en el informe
- Auditoria de fotos y plantas vs JB
- Diagnostico de stock total JB
- Fix de unidades huerfanas (modelo)
- Limpieza de nombres de modelos
- Patch no-destructivo de enums
- Reimportacion de proyectos sin unidades
- Auditoria profunda de modelos y stock
- Clasificacion de CSV maestro JB
- Diagnostico de autenticacion (401)
- Caza del endpoint de detalle JB
- Diagnostico de stock en marketplace
- Confirmacion del pipeline API-first JB
- Diagnostico de estac/bodegas extra
- Reparacion de unidades sin modelo
- Ranking de pendientes por stock
- Revision final consolidada de proyectos
- Revision exhaustiva de un proyecto
- Script de instalacion en el VPS
- Auditoria de listado de proyectos
- Diagnostico de assets (estac/bodegas)
- Diagnostico de carga de detalle (click)
- Diagnostico completo de proyecto
- Scraping de etiquetas JB
- Diagnostico de proyectos Euro
- Diagnostico de filtros de unidades
- Diagnostico de headers (fix 401)
- Ranking de pendientes Ingevec
- Investigacion de casos puntuales
- Diagnostico de tipos en marketplace
- Diagnostico de superficies por modelo
- Diagnostico del paginador de unidades
- Diagnostico de scroll de stock (v2)
- Diagnostico de tab Stock del workview
- Diagnostico de selector Tipo en Stock
- Fix de inmobiliaria placeholder
- Reimportacion de los 84 proyectos
- Revision consolidada de Ingevec
- Auditoria de issues de importacion
- Sincronizacion de modelos desde DOM
- Verificacion de import de detalle
- Compatibilidad de tipos Python 3.9+
- Descubrimiento del editor JetBrokers
- Auditoria de superficies (todos)
- Borrado de modelos placeholder
- Ubicacion de stock (estac/bodegas)
- Diagnostico Abdon Cifuentes
- Auditoria de etiquetas por proyecto
- Diagnostico Novus Torre G
- Diagnostico proyecto Terrazzo
- Diagnostico de totales sin detalle
- Inspeccion de unidades huerfanas
- Inspeccion detallada de stock
- Limpieza de modelos sin unidades
- Patch de totales fisicos
- Reimportacion de 7 proyectos puntuales
- Test del guardado (PUT editor)
- Restauracion de datos ViMa
- Diagnostico de unidades huerfanas
- Diagnostico de 3 proyectos (Vivaceta)
- Inspeccion cruda de unidades
- Reimportacion de 4 assets puntuales
- Verificacion de ambiguedad D/B
- Diagnostico depto sin planta (Vivaceta)
- Workflow de auditoria de superficies
- crear
- _build_operador_html
- Auditoría profunda — Modelos y Stock
- backup_stock_diario.py
- Registro de imports a bc-api
- diag_csv_batch.py
- diag_api_explore.py
- audit_aj_urbana_freshness.py
- import_marketplace_workview.py
- diag_bod_raw.py
- diag_chips_full.py
- diag_detail_page.py
- diag_vm_cotizar.py
- diag_vm_typesel.py
- diag_workview.py
- diag_quotes_explore.py
- seed_inmobiliarias_from_proyectos.py
- check_proyecto.py
- check_stock_recencia.py
- patch_reserva.py
- Auditoria profunda modelos y stock (84 proyectos)
- eventos_anomalos.jsonl (almacen de eventos deduplicados 24h)
- Mapeo de campos JB workview -> bc-api extra.*
- Migracion JB 7.43.1 (nuevo esquema de IDs + namespace marketplace)
- Mapa API publica JetBrokers 7.43.1
- Eventos anomalos - registro automatico
- Workflow: Deploy to VPS
- README: arquitectura y operacion bc-api
- scripts/seed_from_jetbroker.py (planeado, aun no creado)

## God Nodes (most connected - your core abstractions)
1. `JBImporter` - 171 edges
2. `Usuario` - 63 edges
3. `Proyecto` - 44 edges
4. `Unidad` - 23 edges
5. `build_daily_report()` - 23 edges
6. `subir_excel()` - 21 edges
7. `_build_html()` - 16 edges
8. `Base` - 14 edges
9. `build_operador_today()` - 13 edges
10. `process_inbox()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/backfill_codigo_corto.py → app/models/proyecto.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/backfill_precio_cotizacion_lista.py → app/models/proyecto.py
- `preview_operador_today()` --indirect_call--> `db()`  [INFERRED]
  app/main.py → tests/conftest.py
- `main()` --indirect_call--> `Inmobiliaria`  [INFERRED]
  scripts/seed_inmobiliarias_from_proyectos.py → app/models/inmobiliaria.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/backfill_tipologia_desde_modelo.py → app/models/proyecto.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **** — github_workflows_import_jb_workflow, github_workflows_batch_import_jb_workflow, github_workflows_monitor_health_workflow [EXTRACTED 1.00]
- **** — docs_jb_api_7_43_mapa_api, concept_mapeo_campos_jb_bcapi, scripts_import_jb, scripts_import_detail [INFERRED 0.75]
- **** — eventos_registro, concept_eventos_anomalos_jsonl, github_workflows_registrar_eventos_workflow [EXTRACTED 1.00]

## Communities (154 total, 44 thin omitted)

### Community 0 - "Rutas admin: informes e inmobiliarias"
Cohesion: 0.06
Nodes (70): normalize_inmobiliarias(), Unifica EN EL SISTEMA las inmobiliarias que son la misma con distinto tipeo, Imagen, Proyecto, Usuario, actualizar(), eliminar(), _ensure_project() (+62 more)

### Community 1 - "Rutas de unidades (deptos)"
Cohesion: 0.05
Nodes (69): Unidad, actualizar(), actualizar_arriendos(), _build_idx_map(), _build_jb_extras(), crear(), crear_alerta_timeline(), crear_evento_timeline() (+61 more)

### Community 2 - "Servicio de email y alertas"
Cohesion: 0.10
Nodes (32): Dispara el procesador de inbox manualmente (solo super_admin). Lee emails con, trigger_inbox_poll(), _aplicar_excel(), _dominio_de(), _extract_body_text(), _extract_from_original(), _extraer_nombre_proyecto_del_excel(), _fetch_new() (+24 more)

### Community 3 - "Gestion de inmobiliarias (catalogo)"
Cohesion: 0.26
Nodes (15): Inmobiliaria, actualizar(), crear(), eliminar(), _gen_id(), listar(), _normalize(), _proyectos_usados_map() (+7 more)

### Community 4 - "Reporte de importacion y utilidades scraping"
Cohesion: 0.11
Nodes (13): Any, Paginación robusta: detecta JB Angular custom (no Material/Bootstrap estándar)., Visita /projects/detail/{jb_id} y scrapea la tabla de unidades.          El deta, Scrapea la tabla Unidades con VIRTUAL SCROLL acumulando.         La tabla JB no, Parsea filas de la tabla Unidades del editor JB → unidades bc-api.         Mapea, Scrapea la tabla principal de la página actual. Devuelve lista de rows con cells, Click en un tab del editor JB por su label visible. Tolerante a icons/badges., Descarga SOLO el Excel de la tab 'Stock' del editor JB.          Pensado para sy (+5 more)

### Community 5 - "Infraestructura DB y autenticacion"
Cohesion: 0.20
Nodes (12): create_token(), hash_password(), JWT + password hashing., Returns (token, expires_in_seconds)., main(), Crea (o resetea password de) el usuario super admin.  Uso:     python scripts/cr, _get(), main() (+4 more)

### Community 6 - "Eventos anomalos y workflows batch"
Cohesion: 0.12
Nodes (19): Workflow: Audit Plantas, Workflow: Batch import JB (encadenamiento dinámico, L-V 10-18 Chile), Workflow: Batch re-import (plantas + vacíos), Workflow: Import ALL pending JB (uno a la vez, hasta terminar), Workflow: Import JetBrokers project to bc-api, Workflow: List JetBrokers projects, Workflow: Monitor health bc-api + cadena import, Audita los 84 proyectos:  - vacíos (0 modelos + 0 unidades)  - modelos con plant (+11 more)

### Community 7 - "Modulo JBImporter (importador core)"
Cohesion: 0.07
Nodes (24): JBImporter, Lee el valor de un input/select. Lo normaliza a string o None., Workflow: Diag etiquetas JB (18 sin), Workflow: Diag Ingevec rank, Workflow: Diag investigate (Terrazzo + 0-uds + Abdón), Workflow: Diag paginador unidades, Workflow: Diag Rosas 1444, Workflow: Diag Sniff API (solo lectura) (+16 more)

### Community 8 - "Autenticacion y esquemas de sesion"
Cohesion: 0.21
Nodes (12): exchange_bc_token(), ExchangeIn, login(), me(), BaseModel, Session, Exchange a legacy bc_token for a bc-api JWT.      Validates the token against th, LoginIn (+4 more)

### Community 9 - "Diagnosticos API JetBrokers"
Cohesion: 0.47
Nodes (5): count_jb_assets(), head_url(), main(), verify_jb_assets.py — Test 2: paridad de assets (fotos, planos, documentos).  1., Navegar JB editor → tab Documentos → contar por tipo (fotos/planos/docs).

### Community 10 - "Descarga y gestion de assets JB"
Cohesion: 0.16
Nodes (9): AsyncClient, Llama /api/project-file/{jb_id}/list/0 para listar todos los archivos del proyec, Descarga TODOS los archivos del proyecto (fotos+planos+docs) + cover., Llama endpoints API JB para extraer la metadata base + unidades + modelos., classify(), _get_path(), main(), _normalize() (+1 more)

### Community 11 - "Modelos de datos (Proyecto, Ticket)"
Cohesion: 0.18
Nodes (8): Base, Re-export models for Alembic autogenerate + convenience., Catálogo maestro de inmobiliarias.  Antes vivía en localStorage del navegador de, Tickets de reporte de fallas (Fase 5).  Cualquier usuario autenticado de Herrami, Ticket, Usuario — auth and audit., DeclarativeBase, Alembic env: usa el DATABASE_URL del .env y el metadata de los modelos.

### Community 12 - "Exportador Playwright del catalogo JB"
Cohesion: 0.20
Nodes (21): Client, api_login(), fetch_catalog(), fetch_parking(), fetch_project_detail(), fetch_storage(), fetch_units(), _float() (+13 more)

### Community 13 - "Mapeo de campos JB hacia bc-api"
Cohesion: 0.20
Nodes (16): Workflow: Import batch (todos los pendientes), Workflow: Import detail (proyecto propio), asset_m2(), asset_num(), asset_uf(), emap(), facing_es(), fnum() (+8 more)

### Community 14 - "Vista previa del informe diario"
Cohesion: 0.16
Nodes (15): preview_daily_report(), preview_pendientes_pdf(), Devuelve el HTML del informe diario con los datos REALES de prod, SIN enviarlo, PDF con el listado COMPLETO de pendientes vigentes (críticos, sin cortar —     p, _start_scheduler(), _attach_pendientes_pdf(), _pendientes_pdf_bytes(), PDF con TODOS los pendientes vigentes, uno por fila, CADA FILA es un link     cl (+7 more)

### Community 15 - "Ruta de importacion batch (API)"
Cohesion: 0.17
Nodes (20): batch_import(), BatchImportRequest, BatchImportResult, _build_notas(), ImportDetail, _make_proyecto(), _make_unidades(), _normalize_jb_photo_url() (+12 more)

### Community 16 - "Generacion HTML del informe diario"
Cohesion: 0.12
Nodes (20): _build_html(), _calidad_band(), _catalogo_vs_stock_html(), _editor_url(), _faltantes_html(), _hora_cl(), _kpi_cell(), _operador_section_html() (+12 more)

### Community 17 - "Reporte de actividad del operador"
Cohesion: 0.14
Nodes (21): _age_hours(), build_daily_report(), build_operador_today(), _disp(), _enriquecer_resueltos(), _eventos_ventana(), _operador_actividad(), _operador_email() (+13 more)

### Community 18 - "Diagnostico de scraping en vivo"
Cohesion: 0.19
Nodes (15): Workflow: Diag Scrape Live (solo lectura), _count_xlsx_rows(), _deptos(), _items_of(), main(), probe_api(), probe_dom(), probe_excel() (+7 more)

### Community 19 - "Rutas de documentos del proyecto"
Cohesion: 0.08
Nodes (35): Documento, Proyecto + entidades hijas (unidades, imágenes, documentos).  El modelo refleja, actualizar(), DocumentoUpdate, DocumentoUrlIn, eliminar(), _ensure_project(), listar() (+27 more)

### Community 20 - "Importador desde bigcapital.cl Worker"
Cohesion: 0.26
Nodes (12): bcapi_login(), bcapi_upload_foto_url(), bcapi_upsert(), foto_payloads(), get_detail(), list_projects(), main(), Importa proyectos desde la API pública del Cloudflare Worker de bigcapital.cl  L (+4 more)

### Community 21 - "Test de paridad DOM (JB vs BC)"
Cohesion: 0.17
Nodes (14): diff_tab(), load_jb_data_from_import(), main(), _norm_label(), _norm_value(), verify_dom_diff.py — Test 6: Comparación DOM directa JB ↔ BC editor.  Determinís, Carga los datos JB del scrape exhaustivo del importer.     Mucho más confiable q, [DEPRECATED en favor de load_jb_data_from_import] (+6 more)

### Community 22 - "Rutas de imagenes del proyecto"
Cohesion: 0.12
Nodes (30): _is_jb_excel(), _parse_jb_excel(), Parsea sheet UNIDAD del Excel JB → lista de dicts compatibles con bc-api.      R, Detecta si el .xlsx es formato JB (tiene los 4 sheets típicos)., check_baja_masiva(), get_jwt(), _is_depto(), sync_jb_stock.py — Sync liviano de stock JetBrokers → bc-api (bajo consumo JB). (+22 more)

### Community 23 - "Verificacion visual con IA (AI Vision)"
Cohesion: 0.22
Nodes (13): ai_vision_compare(), _dismiss_jb_popups(), main(), normalize_val(), Path, verify_jb_editor_walkthrough.py — Test 5: simulador humano clickeando tabs.  Abr, Normalize values for comparison., Abre BC editor, clickea cada tab, screenshot + extrae datos. (+5 more)

### Community 24 - "Importacion desde export manual JB"
Cohesion: 0.26
Nodes (12): bcapi_login(), bcapi_upsert(), filter_by_org(), main(), Importa proyectos desde un EXPORT MANUAL del usuario logueado en JetBroker.  Flu, Filtra proyectos cuya organization matchee org_query (case-insensitive, fuzzy)., Transforma proyecto JB → payload bc-api., to_bcapi_payload() (+4 more)

### Community 25 - "Motor del informe diario de stock"
Cohesion: 0.14
Nodes (17): _antiguedad_color(), _calidad_score(), _eventos_24h(), Informe diario de stock — bc-api · 2026-06-08  Disparado por APScheduler L-V 09:, Una fila tipo tarjeta para el resumen., Hace 3h', 'Hace 2d 5h', 'Hace 14d', '—' si None. dt es naive UTC de bc-api., Guarda el set de pendientes en el slot ('morning'). Escritura ATÓMICA     (tmp +, Compara los pendientes de AHORA contra el snapshot guardado en `slot` (el inform (+9 more)

### Community 26 - "Calculo de metricas del informe diario"
Cohesion: 0.10
Nodes (9): ImportReport, Extrae modelos únicos desde el array de units, con sus blueprints., #93: deja traza en extra.timeline cuando el import corre por los         fallbac, POST de unidades que YA vienen en formato bc-api (del scrape DOM Unidades)., Inserta unidades en bc-api desde el array de API JB.          Usa el campo apart, GET /proyectos/{id} y compara contra expected counts. Devuelve dict con diff., Busca el proyecto cuyo extra.jb_id == jb_id., Build payload completo y PUT. (+1 more)

### Community 27 - "CI/CD, despliegue y seed inicial"
Cohesion: 0.12
Nodes (13): _acquire_scheduler_lock(), diag_email(), diag_usuario(), bc-api · backend privado para Herramientas BigCapital.  Uvicorn entry: `uvicorn, Dispara el informe diario manualmente (solo super_admin) y lo ENVÍA a los     de, Dispara y ENVÍA el informe de las 13:00 a operador_report_to (solo super_admin)., Estado de la fila bc-api de un usuario (solo super_admin). Para diagnosticar, Diagnóstico SMTP (solo super admin). Sin args: estado de config.     Con ?send=1 (+5 more)

### Community 28 - "Test de paridad UI campo a campo"
Cohesion: 0.11
Nodes (21): Workflow: Dry-run project (solo lectura), bp_id(), derive_tipo(), main(), norm(), dryrun_project.py — Validación DRY-RUN (solo lectura) de un proyecto con el pipe, blueprint puede venir como string (proyectos propios) o dict {id} (marketplace)., main() (+13 more)

### Community 29 - "Motor de alertas de proyecto (criticos)"
Cohesion: 0.20
Nodes (10): _alertas_de_proyecto(), _catalogo_vs_stock(), _critico_key(), _is_depto(), _pendientes_actuales(), Genera TODAS las alertas (críticos + warnings) para un proyecto, con la MISMA, Compara, por proyecto, lo que el CATÁLOGO público mostrará contra el STOCK     I, Clave ESTABLE de un crítico, ignorando conteos/listados variables. Así     '3 mo (+2 more)

### Community 30 - "Dry-run de importacion (solo lectura)"
Cohesion: 0.18
Nodes (20): Email INMEDIATO cuando algo falla (scraper, importación, etc.).      Lo emiten l, send_error_alert(), _configured(), _esc(), _fecha_cl(), _html(), notify_change(), notify_ticket() (+12 more)

### Community 31 - "Patch no-destructivo de stock"
Cohesion: 0.43
Nodes (7): Workflow: Patch stock (no-destructivo), asset_m2(), asset_num(), asset_uf(), _fnum(), main(), patch_stock.py — Refresca estac/bodegas/packs de un proyecto SIN wipe. Trae el m

### Community 32 - "Scraping de superficies individuales"
Cohesion: 0.32
Nodes (7): Workflow: Scrape superficies individuales (5 sin desglose), build_numero_to_unitid_map(), main(), scrape_superficies_individual.py — Para los 5 proyectos sin desglose (Conexión I, Scrapea la tab Unidades y devuelve {numero → jb_unit_id} desde href., Abre /units/edit/{id} y lee Total/Interior/Terraza/Logia/Jardín., read_unit_surfaces()

### Community 33 - "Borrado de proyecto antes de reimportar"
Cohesion: 0.43
Nodes (7): find_proyecto_by_jb_id(), get_jwt(), main(), AsyncClient, wipe_proyecto_jb.py — Borra TODO de un proyecto antes de re-importar limpio.  Es, Busca proyecto cuyo extra.jb_id == jb_id., wipe()

### Community 34 - "Configuracion de la aplicacion (Settings)"
Cohesion: 0.29
Nodes (3): Path, Settings, BaseSettings

### Community 35 - "Debug exhaustivo de proyectos"
Cohesion: 0.38
Nodes (6): Workflow: Debug general, check(), gp(), main(), debug_general.py — Debug exhaustivo de todos los proyectos importados v2. Detect, Devuelve lista de (nivel, mensaje) — nivel: ERROR/WARN/INFO.

### Community 36 - "CLI de importacion JetBrokers"
Cohesion: 0.29
Nodes (5): get_jwt(), import_jb.py — CLI thin wrapper sobre JBImporter.  Uso:   python3 scripts/import, Obtiene un JWT — prioriza BC_API_JWT (ya fresco), sino exchange con BC_TOKEN., run_all(), run_one()

### Community 37 - "Listado de proyectos JetBrokers"
Cohesion: 0.38
Nodes (6): list_via_api(), list_via_dom(), main(), list_jb_projects.py — Lista TODOS los proyectos del broker en JB.  Output: JSON, Intenta varios endpoints API conocidos de JB., Scrape DOM del Catálogo (vista Tabla) en JB.     Aplica filtro Disponible=Sí + J

### Community 38 - "Reimportacion de proyectos multibloque"
Cohesion: 0.43
Nodes (6): batch_import(), bcapi_login(), find_multibloque(), main(), Re-importa proyectos multibloque (con números de unidad duplicados).  Estos proy, Devuelve proyectos que tienen números de depto duplicados (multibloque).

### Community 39 - "Test visual: capturas JB vs BC"
Cohesion: 0.12
Nodes (15): 1. Lista de proyectos de BigCapital (org `uv13koru`), 2. Detalle de proyecto (la ficha completa — 75 campos), 3. Modelos + plantas, 4. Unidades (stock individual), 5. Archivos (fotos + documentos), 6. Descarga de imágenes, API pública JetBrokers 7.43.1 — mapa completo (descubierto 2026-06-05), Autenticación (+7 more)

### Community 40 - "Permisos de acceso a Stock/Worker"
Cohesion: 0.17
Nodes (16): get_db(), SQLAlchemy engine + session factory., FastAPI dependency: yields a SQLAlchemy session per request., current_user(), Session, FastAPI dependencies for auth: extract user from Authorization header., Valida el token de servicio del Cloudflare Worker (catálogo público).      Compa, Acceso a Stock propio: super admin O usuario con permiso de stock.      El permi (+8 more)

### Community 41 - "Links al editor en el informe"
Cohesion: 0.22
Nodes (14): Workflow: Registrar eventos anómalos, append_event(), detect_bc_anomalies(), detect_workflow_anomalies(), load_existing(), main(), now_chile(), now_iso() (+6 more)

### Community 42 - "Auditoria de fotos y plantas vs JB"
Cohesion: 0.40
Nodes (5): Workflow: Audit fotos+plantas vs JB, count_jb_assets(), main(), audit_assets_vs_jb.py — Audita fotos+plantas en bc-api y compara con JB.  1. Lis, Navega a /projects/edit/{jb_id} → tab Documentos y cuenta tipos.

### Community 43 - "Diagnostico de stock total JB"
Cohesion: 0.40
Nodes (5): Workflow: Diagnóstico stock total JB, find_stock_fields(), main(), diag_stock_total.py — Para los 5 proyectos sin unidades, consulta la API JB y du, Recorre recursivamente el JSON y devuelve campos numéricos cuyo nombre     sugie

### Community 44 - "Fix de unidades huerfanas (modelo)"
Cohesion: 0.40
Nodes (5): Workflow: Fix huérfanas modelos, main(), parse_tipologia(), fix_huerfanas_modelos.py — Para cada unidad huérfana (modelo no existe en extra., 1D-1B → (1,1); 2D2B → (2,2); 3D-2B(5) → (3,2).

### Community 45 - "Limpieza de nombres de modelos"
Cohesion: 0.40
Nodes (5): Workflow: Limpiar nombres modelos+unidades, clean_nombre(), main(), limpiar_nombres_modelos.py — Normaliza nombres de modelos y unidades.  Patrón JB, Si tiene patrón 'X - número - X - X' (3+ guiones), tomar primer segmento.     Si

### Community 46 - "Patch no-destructivo de enums"
Cohesion: 0.47
Nodes (5): Workflow: Patch enums (no-destructivo), get_path(), main(), patch_enums.py — Corrige NO-DESTRUCTIVAMENTE los enums crudos (inglés) de un pro, set_path()

### Community 47 - "Reimportacion de proyectos sin unidades"
Cohesion: 0.47
Nodes (5): Workflow: Re-import lista (proyectos sin unidades), main(), reimport_list.py — Re-importa una lista fija de proyectos que quedaron sin unida, trigger_and_wait(), units_count()

### Community 49 - "Clasificacion de CSV maestro JB"
Cohesion: 0.50
Nodes (4): Workflow: Clasificar CSV, main(), clasificar_csv.py — Cruza el CSV master (92 proyectos JB) con lo importado en bc, slugify()

### Community 50 - "Diagnostico de autenticacion (401)"
Cohesion: 0.50
Nodes (4): Workflow: Diag Auth (401 version/token), main(), _mask(), diag_auth.py — Resuelve el 401: ¿es el header de versión (7.42.0 vs 7.43.1) o el

### Community 51 - "Caza del endpoint de detalle JB"
Cohesion: 0.50
Nodes (4): Workflow: Diag Detail (caza endpoint detalle JB), main(), diag_detail.py — Caza el endpoint de DETALLE de proyecto en la API pública JB 7., _summ()

### Community 52 - "Diagnostico de stock en marketplace"
Cohesion: 0.50
Nodes (4): Workflow: Diag mkt stock, main(), diag_mkt_stock.py — Encuentra endpoints de estac/bodegas/packs en MARKETPLACE (r, summ()

### Community 53 - "Confirmacion del pipeline API-first JB"
Cohesion: 0.50
Nodes (4): Workflow: Diag Pipeline (API-first JB), main(), diag_pipeline.py — Confirma el pipeline API-first completo de JB 7.43.1.  1. Cap, _summ()

### Community 54 - "Diagnostico de estac/bodegas extra"
Cohesion: 0.50
Nodes (4): Workflow: Diag stock extra (estac/bodegas), main(), diag_stock_extra.py — Encuentra endpoints de estacionamientos/bodegas/packs (pro, summ()

### Community 55 - "Reparacion de unidades sin modelo"
Cohesion: 0.50
Nodes (4): Workflow: Patch modelo huerfanas, main(), parse_db(), patch_modelo_huerfanas.py — Repara unidades con modelo="" en proyectos afectados

### Community 56 - "Ranking de pendientes por stock"
Cohesion: 0.40
Nodes (3): Workflow: Rank pendientes JB, main(), rank_pendientes.py — Rankea 58 pendientes JB por stock total (uds+estac+bod+pack

### Community 57 - "Revision final consolidada de proyectos"
Cohesion: 0.50
Nodes (4): Workflow: Review all, gp(), main(), review_all.py — Revisión final consolidada de todos los proyectos importados v2.

### Community 59 - "Script de instalacion en el VPS"
Cohesion: 0.70
Nodes (4): die(), log(), vps_install.sh script, warn()

### Community 61 - "Diagnostico de assets (estac/bodegas)"
Cohesion: 0.50
Nodes (3): Workflow: Diag assets, main(), diag_assets.py — Inspecciona /project/{id}/assets (estac/bodegas/packs vía cotiz

### Community 62 - "Diagnostico de carga de detalle (click)"
Cohesion: 0.08
Nodes (19): jb_importer.py — Importador JetBrokers → bc-api.  Módulo reusable. Diseñado para, Sentinel interno para saltar una sección de scrape_marketplace_workview     en m, _SkipSection, Exception, Workflow: Diag Click (detalle real), Workflow: Diag completo proyecto (qué falta), Workflow: Diag modelo superficies, Workflow: Diag vm scroll (+11 more)

### Community 63 - "Diagnostico completo de proyecto"
Cohesion: 0.16
Nodes (7): Path, Borra todas las Imagenes con categoria que empieza con 'jb-' o 'cover'., Sube TODOS los assets descargados a bc-api con categoria apropiada.          IDE, POST multipart a /proyectos/{id}/imagenes. Devuelve URL pública., 1D - 1B" -> (1, 1). bc-api deriva extra tipologia de la columna Modelo         c, Construye un .xlsx formato JB (INSTRUCCIONES/UNIDAD/ESTACIONAMIENTOS/         BO, Sube el Excel JB descargado a /excel/upload de bc-api.         bc-api parsea las

### Community 64 - "Scraping de etiquetas JB"
Cohesion: 0.29
Nodes (11): buscar(), _extraer_filas(), _goto_catalog(), main(), _norm(), _paginar_y_juntar(), _quitar_filtros(), find_jb_project.py — Busca un proyecto por NOMBRE en el catálogo JetBrokers (log (+3 more)

### Community 65 - "Diagnostico de proyectos Euro"
Cohesion: 0.50
Nodes (3): Workflow: Diag Euro batch, main(), diag_euro.py — Diagnóstico rápido de los 8 proyectos de Euro para ver cuál tiene

### Community 66 - "Diagnostico de filtros de unidades"
Cohesion: 0.50
Nodes (3): Workflow: Diag filtros unidades, main(), Inspecciona el estado de la tab Unidades: filtros activos, contadores, botones o

### Community 67 - "Diagnostico de headers (fix 401)"
Cohesion: 0.50
Nodes (3): Workflow: Diag Headers (401 fix), main(), diag_headers.py — Captura los headers REALES que manda el navegador en stock-sel

### Community 68 - "Ranking de pendientes Ingevec"
Cohesion: 0.17
Nodes (9): Smoke test del CRUD de proyectos., Si el server no tiene BC_API_SERVICE_TOKEN, el endpoint está deshabilitado., Con token configurado, un Bearer incorrecto da 401 (antes de tocar la DB)., La ruta /public no debe ser capturada por /{proyecto_id}.     Sin token → 503/40, El catálogo público (allow-list) NUNCA debe exponer RUT, cuenta bancaria,     co, test_public_dict_no_filtra_datos_sensibles(), test_public_no_choca_con_detalle(), test_public_sin_token_configurado_da_503() (+1 more)

### Community 69 - "Investigacion de casos puntuales"
Cohesion: 0.20
Nodes (9): Eventos anómalos — registro automático, 🚨 Fallos de workflow (26 en total, mostrando últimos 26), ℹ Batches fuera de ventana L-V 10-18 (59 en total, mostrando últimos 30), ℹ Errores leyendo GH CLI (1 en total, mostrando últimos 1), ℹ Inmobiliaria sin asignar (32 en total, mostrando últimos 30), ℹ Nombre stub no actualizado (2 en total, mostrando últimos 2), ℹ Workflows cancelados (118 en total, mostrando últimos 30), ⚠ Proyectos con modelos pero sin unidades (114 en total, mostrando últimos 30) (+1 more)

### Community 70 - "Diagnostico de tipos en marketplace"
Cohesion: 0.50
Nodes (3): Workflow: Diag mkt types, main(), diag_mkt_types.py — Captura el body de units-search al filtrar por tipo + distri

### Community 71 - "Diagnostico de superficies por modelo"
Cohesion: 0.20
Nodes (9): bc-api, Deploy automático (GitHub Actions), Endpoints (resumen), Operación, Pendiente / Roadmap, Primera instalación en el VPS, Seguridad, Setup local (dev) (+1 more)

### Community 72 - "Diagnostico del paginador de unidades"
Cohesion: 0.47
Nodes (9): _card(), _imp(), Tests de JBImporter._parse_marketplace_unidades (pura, sin red/Playwright/DB)., test_descarta_cards_sin_numero(), test_flags_obligatorio_y_nunca(), test_modelo_faltante_usa_sm(), test_multiples_cards(), test_parsea_card_real_depto_1402() (+1 more)

### Community 73 - "Diagnostico de scroll de stock (v2)"
Cohesion: 0.50
Nodes (3): Workflow: Diag vm scroll, main(), diag_vm_scroll2.py — Scroll del Stock (tarjetas) hasta el final; scrapea todos l

### Community 74 - "Diagnostico de tab Stock del workview"
Cohesion: 0.50
Nodes (3): Workflow: Diag vm stock, main(), diag_vm_stock.py — Abre el tab Stock del workview y captura TODO lo que dispara.

### Community 75 - "Diagnostico de selector Tipo en Stock"
Cohesion: 0.50
Nodes (3): Workflow: Diag vm tipo, main(), diag_vm_tipo.py — Usa el ng-select 'Tipo' del Stock para scrapear estac/bodegas/

### Community 82 - "Compatibilidad de tipos Python 3.9+"
Cohesion: 0.67
Nodes (3): main(), Reescribe sintaxis de tipos para que el código sea Python 3.9+ compatible.  PEP, transform()

### Community 83 - "Descubrimiento del editor JetBrokers"
Cohesion: 0.67
Nodes (3): log(), discover_jb_editor.py — Descubre qué expone el editor de JetBrokers para 1 proye, run()

### Community 122 - "crear"
Cohesion: 0.25
Nodes (9): crear(), listar(), BackgroundTasks, Session, UploadFile, Marca resuelto CON evidencia: qué se hizo (texto, obligatorio) + captura     de, Crea un ticket. Cualquier usuario autenticado de Herramientas puede hacerlo., Lista tickets (solo super admin). ?estado=abierto|cerrado para filtrar. (+1 more)

### Community 123 - "_build_operador_html"
Cohesion: 0.25
Nodes (8): preview_operador_today(), HTML del informe de las 13:00 (avances de HOY de Cristofer) con datos REALES,, _build_operador_html(), _disclaimer_html(), Email compacto: cabecera + mejoras de HOY + resolución de pendientes (sin nombre, Aviso fijo: informe automático en desarrollo., Bloque 'Resolución de pendientes' comparando contra el informe previo., _resolucion_html()

### Community 124 - "Auditoría profunda — Modelos y Stock"
Cohesion: 0.25
Nodes (7): Auditoría profunda — Modelos y Stock, 📋 Detalle por proyecto, 📈 Estadísticas globales, ⚠ Proyectos con modelos pero NINGUNO con planta_url (6), ⚠ Proyectos con unidades huérfanas (5), ⚠ Proyectos sin modelos (7), ⚠ Proyectos sin unidades (13)

### Community 125 - "backup_stock_diario.py"
Cohesion: 0.43
Nodes (7): _limpiar_viejos(), main(), Backup diario del stock (proyectos + unidades + imagenes + documentos).  Corre p, _serializar_documento(), _serializar_imagen(), _serializar_proyecto(), _serializar_unidad()

### Community 126 - "Registro de imports a bc-api"
Cohesion: 0.29
Nodes (6): 2026-05-21 · Intento Larraín Prieto (JetBroker), 2026-05-21 · Seed inicial (Pinar 1 + 2), 2026-05-22 · Hallazgo: bigcapital.cl Worker API es pública, Cómo importar desde el snapshot de JetBroker (referencia), Próximos imports (TODO), Registro de imports a bc-api

### Community 127 - "diag_csv_batch.py"
Cohesion: 0.40
Nodes (5): Workflow: Diag CSV batch (read-only), main(), diag_csv_batch.py — Diagnóstico read-only de los 20 proyectos del CSV de Ingevec, Sluggify igual que bc-api: minúsculas, sin acentos, espacios → guiones., slugify()

### Community 128 - "diag_api_explore.py"
Cohesion: 0.40
Nodes (3): Workflow: Diag API Explore (server-side, solo lectura), main(), diag_api_explore.py — Explorador PROFUNDO de la API JB (server-side, solo lectur

### Community 129 - "audit_aj_urbana_freshness.py"
Cohesion: 0.60
Nodes (4): main(), _parse_fecha(), datetime, audit_aj_urbana_freshness.py — Dead-man-switch de frescura para los 7 proyectos

### Community 130 - "import_marketplace_workview.py"
Cohesion: 0.50
Nodes (3): main(), import_marketplace_workview.py — Importa un proyecto de marketplace/workview (pr, run()

### Community 131 - "diag_bod_raw.py"
Cohesion: 0.50
Nodes (3): Workflow: Diag bod raw, main(), Inspecciona la respuesta cruda de bodegas (¿trae superficie en algún campo?).

### Community 132 - "diag_chips_full.py"
Cohesion: 0.50
Nodes (3): Workflow: Diag chips completo (4 grupos), main(), diag_chips_full.py — Verificación COMPLETA de los 4 grupos de chips: etiquetas,

### Community 133 - "diag_detail_page.py"
Cohesion: 0.50
Nodes (3): Workflow: Diag detail page (proyectos propios), main(), diag_detail_page.py — Explora /projects/detail/{id} (vista de proyectos PROPIOS

### Community 134 - "diag_vm_cotizar.py"
Cohesion: 0.50
Nodes (3): Workflow: Diag vm cotizar, main(), diag_vm_cotizar.py — Clic en 'Cotizar' de un depto; captura inventario estac/bod

### Community 135 - "diag_vm_typesel.py"
Cohesion: 0.50
Nodes (3): Workflow: Diag vm typesel, main(), diag_vm_typesel.py — Encuentra el selector de tipo en el Stock del workview y sc

### Community 136 - "diag_workview.py"
Cohesion: 0.50
Nodes (3): Workflow: Diag Workview (modelos/unidades/galeria), main(), diag_workview.py — Mapea los sub-endpoints del workview (modelos/unidades/galerí

### Community 138 - "seed_inmobiliarias_from_proyectos.py"
Cohesion: 0.67
Nodes (3): _gen_id(), main(), Seed: poblar el catálogo maestro 'inmobiliarias' a partir de los nombres distint

## Knowledge Gaps
- **127 isolated node(s):** `📈 Estadísticas globales`, `📋 Detalle por proyecto`, `⚠ Proyectos sin unidades (13)`, `⚠ Proyectos sin modelos (7)`, `⚠ Proyectos con unidades huérfanas (5)` (+122 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **44 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JBImporter` connect `Modulo JBImporter (importador core)` to `diag_api_explore.py`, `Rutas de unidades (deptos)`, `import_marketplace_workview.py`, `diag_bod_raw.py`, `Reporte de importacion y utilidades scraping`, `diag_chips_full.py`, `diag_detail_page.py`, `diag_vm_cotizar.py`, `diag_vm_typesel.py`, `diag_quotes_explore.py`, `Descarga y gestion de assets JB`, `diag_workview.py`, `Diagnosticos API JetBrokers`, `Mapeo de campos JB hacia bc-api`, `Diagnostico de scraping en vivo`, `Test de paridad DOM (JB vs BC)`, `Rutas de imagenes del proyecto`, `Verificacion visual con IA (AI Vision)`, `Calculo de metricas del informe diario`, `Test de paridad UI campo a campo`, `Patch no-destructivo de stock`, `Scraping de superficies individuales`, `CLI de importacion JetBrokers`, `Listado de proyectos JetBrokers`, `Auditoria de fotos y plantas vs JB`, `Diagnostico de stock total JB`, `Diagnostico de autenticacion (401)`, `Caza del endpoint de detalle JB`, `Diagnostico de stock en marketplace`, `Confirmacion del pipeline API-first JB`, `Diagnostico de estac/bodegas extra`, `Ranking de pendientes por stock`, `Diagnostico de assets (estac/bodegas)`, `Diagnostico de carga de detalle (click)`, `Diagnostico completo de proyecto`, `Scraping de etiquetas JB`, `Diagnostico de proyectos Euro`, `Diagnostico de filtros de unidades`, `Diagnostico de headers (fix 401)`, `Diagnostico de tipos en marketplace`, `Diagnostico del paginador de unidades`, `Diagnostico de scroll de stock (v2)`, `Diagnostico de tab Stock del workview`, `Diagnostico de selector Tipo en Stock`, `diag_csv_batch.py`?**
  _High betweenness centrality (0.275) - this node is a cross-community bridge._
- **Why does `Usuario` connect `Rutas admin: informes e inmobiliarias` to `Rutas de unidades (deptos)`, `Servicio de email y alertas`, `Gestion de inmobiliarias (catalogo)`, `Infraestructura DB y autenticacion`, `Permisos de acceso a Stock/Worker`, `CI/CD, despliegue y seed inicial`, `Autenticacion y esquemas de sesion`, `Modelos de datos (Proyecto, Ticket)`, `Vista previa del informe diario`, `Ruta de importacion batch (API)`, `Rutas de documentos del proyecto`, `crear`, `_build_operador_html`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `Dependencias Python (requirements.txt)` connect `CI/CD, despliegue y seed inicial` to `Motor del informe diario de stock`, `CLI de importacion JetBrokers`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Usuario` (e.g. with `login()` and `main()`) actually correct?**
  _`Usuario` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `Proyecto` (e.g. with `normalize_inmobiliarias()` and `batch_import()`) actually correct?**
  _`Proyecto` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Unidad` (e.g. with `batch_import()` and `actualizar()`) actually correct?**
  _`Unidad` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `SQLAlchemy engine + session factory.`, `FastAPI dependency: yields a SQLAlchemy session per request.`, `FastAPI dependencies for auth: extract user from Authorization header.` to the rest of the system?**
  _486 weakly-connected nodes found - possible documentation gaps or missing edges._