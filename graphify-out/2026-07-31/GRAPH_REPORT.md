# Graph Report - /Users/nicolas/Documents/Claude/Projects/bc-api  (2026-07-09)

## Corpus Check
- 246 files · ~116,744 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1103 nodes · 1967 edges · 122 communities (92 shown, 30 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 73 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `JBImporter` - 144 edges
2. `Usuario` - 59 edges
3. `Proyecto` - 38 edges
4. `Unidad` - 23 edges
5. `build_daily_report()` - 22 edges
6. `subir_excel()` - 21 edges
7. `_build_html()` - 15 edges
8. `Base` - 14 edges
9. `build_operador_today()` - 13 edges
10. `process_inbox()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/fix_region_from_comuna.py → app/models/proyecto.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/geocode_proyectos.py → app/models/proyecto.py
- `seed()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/seed_from_frontend.py → app/models/proyecto.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/seed_inmobiliarias_from_proyectos.py → app/models/proyecto.py
- `_crear_proy()` --indirect_call--> `Proyecto`  [INFERRED]
  tests/test_upload_sin_unidades.py → app/models/proyecto.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **** — github_workflows_import_jb_workflow, github_workflows_batch_import_jb_workflow, github_workflows_monitor_health_workflow [EXTRACTED 1.00]
- **** — docs_jb_api_7_43_mapa_api, concept_mapeo_campos_jb_bcapi, scripts_import_jb, scripts_import_detail [INFERRED 0.75]
- **** — eventos_registro, concept_eventos_anomalos_jsonl, github_workflows_registrar_eventos_workflow [EXTRACTED 1.00]

## Communities (122 total, 30 thin omitted)

### Community 0 - "Rutas admin: informes e inmobiliarias"
Cohesion: 0.06
Nodes (58): diag_email(), diag_usuario(), normalize_inmobiliarias(), Dispara el informe diario manualmente (solo super_admin) y lo ENVÍA a los     de, Dispara y ENVÍA el informe de las 13:00 a operador_report_to (solo super_admin)., Unifica EN EL SISTEMA las inmobiliarias que son la misma con distinto tipeo, Estado de la fila bc-api de un usuario (solo super_admin). Para diagnosticar, Diagnóstico SMTP (solo super admin). Sin args: estado de config.     Con ?send=1 (+50 more)

### Community 1 - "Rutas de unidades (deptos)"
Cohesion: 0.06
Nodes (58): Unidad, actualizar(), actualizar_arriendos(), _build_idx_map(), _build_jb_extras(), crear(), crear_alerta_timeline(), _desc_modificacion() (+50 more)

### Community 2 - "Servicio de email y alertas"
Cohesion: 0.07
Nodes (52): Dispara el procesador de inbox manualmente (solo super_admin). Lee emails con, trigger_inbox_poll(), Email INMEDIATO cuando algo falla (scraper, importación, etc.).      Lo emiten l, send_error_alert(), _configured(), _esc(), _fecha_cl(), _html() (+44 more)

### Community 3 - "Gestion de inmobiliarias (catalogo)"
Cohesion: 0.09
Nodes (33): Inmobiliaria, Catálogo maestro de inmobiliarias.  Antes vivía en localStorage del navegador de, actualizar(), crear(), eliminar(), _gen_id(), listar(), _normalize() (+25 more)

### Community 4 - "Reporte de importacion y utilidades scraping"
Cohesion: 0.06
Nodes (17): Any, ImportReport, Paginación robusta: detecta JB Angular custom (no Material/Bootstrap estándar)., Visita /projects/detail/{jb_id} y scrapea la tabla de unidades.          El deta, Scrapea la tabla Unidades con VIRTUAL SCROLL acumulando.         La tabla JB no, Parsea filas de la tabla Unidades del editor JB → unidades bc-api.         Mapea, Scrapea la tabla principal de la página actual. Devuelve lista de rows con cells, Click en un tab del editor JB por su label visible. Tolerante a icons/badges. (+9 more)

### Community 5 - "Infraestructura DB y autenticacion"
Cohesion: 0.11
Nodes (24): get_db(), SQLAlchemy engine + session factory., FastAPI dependency: yields a SQLAlchemy session per request., current_user(), FastAPI dependencies for auth: extract user from Authorization header., super_admin(), bc-api · backend privado para Herramientas BigCapital.  Uvicorn entry: `uvicorn, Usuario — auth and audit. (+16 more)

### Community 6 - "Eventos anomalos y workflows batch"
Cohesion: 0.07
Nodes (34): eventos_anomalos.jsonl (almacen de eventos deduplicados 24h), Eventos anomalos - registro automatico, Workflow: Audit Plantas, Workflow: Batch import JB (encadenamiento dinámico, L-V 10-18 Chile), Workflow: Batch re-import (plantas + vacíos), Workflow: Import ALL pending JB (uno a la vez, hasta terminar), Workflow: Import JetBrokers project to bc-api, Workflow: List JetBrokers projects (+26 more)

### Community 7 - "Modulo JBImporter (importador core)"
Cohesion: 0.07
Nodes (23): JBImporter, Lee el valor de un input/select. Lo normaliza a string o None., Build payload completo y PUT., Workflow: Diag bod raw, Workflow: Diag chips completo (4 grupos), Workflow: Diag detail page (proyectos propios), Workflow: Diag Rosas 1444, Workflow: Diag vm scroll (+15 more)

### Community 8 - "Autenticacion y esquemas de sesion"
Cohesion: 0.12
Nodes (27): exchange_bc_token(), ExchangeIn, login(), me(), BaseModel, Session, Exchange a legacy bc_token for a bc-api JWT.      Validates the token against th, LoginIn (+19 more)

### Community 9 - "Diagnosticos API JetBrokers"
Cohesion: 0.07
Nodes (20): jb_importer.py — Importador JetBrokers → bc-api.  Módulo reusable. Diseñado para, Workflow: Diag API Explore (server-side, solo lectura), Workflow: Diag Sniff API (solo lectura), Workflow: Diag vm cotizar, Workflow: Diag Workview (modelos/unidades/galeria), main(), diag_api_explore.py — Explorador PROFUNDO de la API JB (server-side, solo lectur, main() (+12 more)

### Community 10 - "Descarga y gestion de assets JB"
Cohesion: 0.10
Nodes (14): AsyncClient, Path, Llama /api/project-file/{jb_id}/list/0 para listar todos los archivos del proyec, Descarga TODOS los archivos del proyecto (fotos+planos+docs) + cover., Borra todas las Imagenes con categoria que empieza con 'jb-' o 'cover'., Sube TODOS los assets descargados a bc-api con categoria apropiada.          IDE, POST multipart a /proyectos/{id}/imagenes. Devuelve URL pública., Sube el Excel JB descargado a /excel/upload de bc-api.         bc-api parsea las (+6 more)

### Community 11 - "Modelos de datos (Proyecto, Ticket)"
Cohesion: 0.12
Nodes (16): Base, Re-export models for Alembic autogenerate + convenience., Proyecto + entidades hijas (unidades, imágenes, documentos).  El modelo refleja, Tickets de reporte de fallas (Fase 5).  Cualquier usuario autenticado de Herrami, Ticket, actualizar(), crear(), listar() (+8 more)

### Community 12 - "Exportador Playwright del catalogo JB"
Cohesion: 0.20
Nodes (21): Client, api_login(), fetch_catalog(), fetch_parking(), fetch_project_detail(), fetch_storage(), fetch_units(), _float() (+13 more)

### Community 13 - "Mapeo de campos JB hacia bc-api"
Cohesion: 0.16
Nodes (19): Mapeo de campos JB workview -> bc-api extra.*, Migracion JB 7.43.1 (nuevo esquema de IDs + namespace marketplace), Mapa API publica JetBrokers 7.43.1, Workflow: Import batch (todos los pendientes), Workflow: Import detail (proyecto propio), asset_m2(), asset_num(), asset_uf() (+11 more)

### Community 14 - "Vista previa del informe diario"
Cohesion: 0.12
Nodes (19): _acquire_scheduler_lock(), preview_daily_report(), preview_operador_today(), preview_pendientes_pdf(), Devuelve el HTML del informe diario con los datos REALES de prod, SIN enviarlo, PDF con el listado COMPLETO de pendientes vigentes (críticos, sin cortar —     p, HTML del informe de las 13:00 (avances de HOY de Cristofer) con datos REALES,, True solo en UN worker. uvicorn con >1 worker = N procesos, cada uno corre el (+11 more)

### Community 15 - "Ruta de importacion batch (API)"
Cohesion: 0.20
Nodes (17): batch_import(), BatchImportRequest, BatchImportResult, _build_notas(), ImportDetail, _make_proyecto(), _make_unidades(), _normalize_jb_photo_url() (+9 more)

### Community 16 - "Generacion HTML del informe diario"
Cohesion: 0.13
Nodes (18): _build_html(), _build_operador_html(), _calidad_band(), _disclaimer_html(), _faltantes_html(), _hora_cl(), _kpi_cell(), _operador_section_html() (+10 more)

### Community 17 - "Reporte de actividad del operador"
Cohesion: 0.16
Nodes (16): build_operador_today(), _enriquecer_resueltos(), _eventos_ventana(), _operador_actividad(), _operador_email(), _operador_eventos_planos(), _operador_nombre(), _proyectos_activos() (+8 more)

### Community 18 - "Diagnostico de scraping en vivo"
Cohesion: 0.19
Nodes (15): Workflow: Diag Scrape Live (solo lectura), _count_xlsx_rows(), _deptos(), _items_of(), main(), probe_api(), probe_dom(), probe_excel() (+7 more)

### Community 19 - "Rutas de documentos del proyecto"
Cohesion: 0.30
Nodes (14): Documento, actualizar(), DocumentoUpdate, DocumentoUrlIn, eliminar(), _ensure_project(), listar(), BaseModel (+6 more)

### Community 20 - "Importador desde bigcapital.cl Worker"
Cohesion: 0.21
Nodes (14): Registro de imports a bc-api, bcapi_login(), bcapi_upload_foto_url(), bcapi_upsert(), foto_payloads(), get_detail(), list_projects(), main() (+6 more)

### Community 21 - "Test de paridad DOM (JB vs BC)"
Cohesion: 0.17
Nodes (14): diff_tab(), load_jb_data_from_import(), main(), _norm_label(), _norm_value(), verify_dom_diff.py — Test 6: Comparación DOM directa JB ↔ BC editor.  Determinís, Carga los datos JB del scrape exhaustivo del importer.     Mucho más confiable q, [DEPRECATED en favor de load_jb_data_from_import] (+6 more)

### Community 22 - "Rutas de imagenes del proyecto"
Cohesion: 0.32
Nodes (13): Imagen, actualizar(), eliminar(), _ensure_project(), ImagenUrlIn, listar(), BaseModel, Session (+5 more)

### Community 23 - "Verificacion visual con IA (AI Vision)"
Cohesion: 0.22
Nodes (13): ai_vision_compare(), _dismiss_jb_popups(), main(), normalize_val(), Path, verify_jb_editor_walkthrough.py — Test 5: simulador humano clickeando tabs.  Abr, Normalize values for comparison., Abre BC editor, clickea cada tab, screenshot + extrae datos. (+5 more)

### Community 24 - "Importacion desde export manual JB"
Cohesion: 0.26
Nodes (12): bcapi_login(), bcapi_upsert(), filter_by_org(), main(), Importa proyectos desde un EXPORT MANUAL del usuario logueado en JetBroker.  Flu, Filtra proyectos cuya organization matchee org_query (case-insensitive, fuzzy)., Transforma proyecto JB → payload bc-api., to_bcapi_payload() (+4 more)

### Community 25 - "Motor del informe diario de stock"
Cohesion: 0.23
Nodes (11): Informe diario de stock — bc-api · 2026-06-08  Disparado por APScheduler L-V 09:, Guarda el set de pendientes en el slot ('morning'). Escritura ATÓMICA     (tmp +, Hace 3h', 'Hace 2d 5h', 'Hace 14d', '—' si None. dt es naive UTC de bc-api., Compara los pendientes de AHORA contra el snapshot guardado en `slot` (el inform, Una fila tipo tarjeta para el resumen., _resolucion_cruce(), _row(), _snap_load() (+3 more)

### Community 26 - "Calculo de metricas del informe diario"
Cohesion: 0.18
Nodes (11): _age_hours(), _antiguedad_color(), build_daily_report(), _calidad_score(), _disp(), _eventos_24h(), Eventos del timeline en últimas 24h. Devuelve [{tipo,fecha,detalles}]., Horas desde dt (naive UTC de bc-api) hasta ahora; None si dt es None. (+3 more)

### Community 27 - "CI/CD, despliegue y seed inicial"
Cohesion: 0.28
Nodes (8): Workflow: CI, Workflow: Deploy to VPS, README: arquitectura y operacion bc-api, Dependencias Python (requirements.txt), parse_seed(), Path, Importa proyectos del seed-pinar.js (frontend stock-interno) a la DB Postgres., seed()

### Community 28 - "Test de paridad UI campo a campo"
Cohesion: 0.31
Nodes (8): main(), normalize(), verify_jb_ui_parity.py — Test 4: comparación UI campo-por-campo.  Abre BC vista, Scrape BC vista. Inyecta bc_api_token directo en localStorage para saltar login., Normaliza valor para comparación: lowercase, sin acentos, sin espacios extra., Scrape el tab General del editor JB. Retorna lista de {section, label, value}., scrape_bc_vista(), scrape_jb_general()

### Community 29 - "Motor de alertas de proyecto (criticos)"
Cohesion: 0.25
Nodes (8): _alertas_de_proyecto(), _critico_key(), _is_depto(), _pendientes_actuales(), Genera TODAS las alertas (críticos + warnings) para un proyecto, con la MISMA, Clave ESTABLE de un crítico, ignorando conteos/listados variables. Así     '3 mo, Errores/pendientes CRÍTICOS vigentes ahora. key = 'pid::clave_estable'.     Guar, ¿La unidad es un departamento (no estac/bodega/pack)?

### Community 30 - "Dry-run de importacion (solo lectura)"
Cohesion: 0.36
Nodes (7): Workflow: Dry-run project (solo lectura), bp_id(), derive_tipo(), main(), norm(), dryrun_project.py — Validación DRY-RUN (solo lectura) de un proyecto con el pipe, blueprint puede venir como string (proyectos propios) o dict {id} (marketplace).

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
Cohesion: 0.48
Nodes (6): main(), Path, verify_jb_visual.py — Test 3: screenshots side-by-side de JB editor vs BC vista., Usa una segunda página de Playwright (reusar mismo browser para ahorrar)., screenshot_bc_tabs(), screenshot_jb_tabs()

### Community 40 - "Permisos de acceso a Stock/Worker"
Cohesion: 0.33
Nodes (6): Session, Valida el token de servicio del Cloudflare Worker (catálogo público).      Compa, Acceso a Stock propio: super admin O usuario con permiso de stock.      El permi, service_token(), stock_access(), HTTPAuthorizationCredentials

### Community 41 - "Links al editor en el informe"
Cohesion: 0.33
Nodes (6): _editor_url(), _proj_inline(), _project_link(), Link al EDITOR del proyecto (donde se corrige), opcionalmente en una pestaña., Nombre del proyecto como link al editor (pestaña opcional)., Link al proyecto (→ editor, pestaña Unidades por defecto) + inmobiliaria.

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

### Community 48 - "Auditoria profunda de modelos y stock"
Cohesion: 0.40
Nodes (3): Auditoria profunda modelos y stock (84 proyectos), Workflow: Auditoría profunda modelos + stock, audit_modelos_stock.py — Auditoría profunda de unidades + modelos.  Inspecciona

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
Cohesion: 0.50
Nodes (3): Workflow: Diag Click (detalle real), main(), diag_click.py — Observa a la app cargar un DETALLE real haciendo clic en una tar

### Community 63 - "Diagnostico completo de proyecto"
Cohesion: 0.50
Nodes (3): Workflow: Diag completo proyecto (qué falta), main(), diag_completo_proyecto.py — Compara TODO lo que bc-api tiene vs lo que JB expone

### Community 64 - "Scraping de etiquetas JB"
Cohesion: 0.50
Nodes (3): Workflow: Diag etiquetas JB (18 sin), main(), diag_etiquetas_jb.py — Scrapea las ETIQUETAS directo del editor JB para los 18 p

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
Cohesion: 0.50
Nodes (3): Workflow: Diag Ingevec rank, main(), diag_ingevec_rank.py — Ranking por stock total de los 17 Ingevec pendientes.

### Community 69 - "Investigacion de casos puntuales"
Cohesion: 0.50
Nodes (3): Workflow: Diag investigate (Terrazzo + 0-uds + Abdón), main(), diag_investigate.py — Investiga los 3 puntos problemáticos del lote CSV:  1. Ter

### Community 70 - "Diagnostico de tipos en marketplace"
Cohesion: 0.50
Nodes (3): Workflow: Diag mkt types, main(), diag_mkt_types.py — Captura el body de units-search al filtrar por tipo + distri

### Community 71 - "Diagnostico de superficies por modelo"
Cohesion: 0.50
Nodes (3): Workflow: Diag modelo superficies, main(), Probar endpoints de DETALLE de modelo JB para encontrar las superficies (Sup Tot

### Community 72 - "Diagnostico del paginador de unidades"
Cohesion: 0.50
Nodes (3): Workflow: Diag paginador unidades, main(), Vuelca los controles de paginación de la tab Unidades de un proyecto JB.

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

## Knowledge Gaps
- **81 isolated node(s):** `Workflow: Audit fotos+plantas vs JB`, `Workflow: Audit Plantas`, `Workflow: Audit proyectos bc-api`, `Workflow: Audit superficies (TODOS)`, `Workflow: Audit superficies` (+76 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JBImporter` connect `Modulo JBImporter (importador core)` to `Gestion de inmobiliarias (catalogo)`, `Reporte de importacion y utilidades scraping`, `Diagnosticos API JetBrokers`, `Descarga y gestion de assets JB`, `Mapeo de campos JB hacia bc-api`, `Diagnostico de scraping en vivo`, `Test de paridad DOM (JB vs BC)`, `Verificacion visual con IA (AI Vision)`, `Test de paridad UI campo a campo`, `Dry-run de importacion (solo lectura)`, `Patch no-destructivo de stock`, `Scraping de superficies individuales`, `CLI de importacion JetBrokers`, `Listado de proyectos JetBrokers`, `Test visual: capturas JB vs BC`, `Auditoria de fotos y plantas vs JB`, `Diagnostico de stock total JB`, `Diagnostico de autenticacion (401)`, `Caza del endpoint de detalle JB`, `Diagnostico de stock en marketplace`, `Confirmacion del pipeline API-first JB`, `Diagnostico de estac/bodegas extra`, `Ranking de pendientes por stock`, `Diagnostico de assets (estac/bodegas)`, `Diagnostico de carga de detalle (click)`, `Diagnostico completo de proyecto`, `Scraping de etiquetas JB`, `Diagnostico de proyectos Euro`, `Diagnostico de filtros de unidades`, `Diagnostico de headers (fix 401)`, `Ranking de pendientes Ingevec`, `Investigacion de casos puntuales`, `Diagnostico de tipos en marketplace`, `Diagnostico de superficies por modelo`, `Diagnostico del paginador de unidades`, `Diagnostico de scroll de stock (v2)`, `Diagnostico de tab Stock del workview`, `Diagnostico de selector Tipo en Stock`?**
  _High betweenness centrality (0.325) - this node is a cross-community bridge._
- **Why does `Dependencias Python (requirements.txt)` connect `CI/CD, despliegue y seed inicial` to `Motor del informe diario de stock`, `CLI de importacion JetBrokers`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `Usuario` connect `Rutas admin: informes e inmobiliarias` to `Rutas de unidades (deptos)`, `Servicio de email y alertas`, `Gestion de inmobiliarias (catalogo)`, `Infraestructura DB y autenticacion`, `Permisos de acceso a Stock/Worker`, `Autenticacion y esquemas de sesion`, `Modelos de datos (Proyecto, Ticket)`, `Vista previa del informe diario`, `Ruta de importacion batch (API)`, `Rutas de documentos del proyecto`, `Rutas de imagenes del proyecto`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Usuario` (e.g. with `login()` and `main()`) actually correct?**
  _`Usuario` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `Proyecto` (e.g. with `normalize_inmobiliarias()` and `batch_import()`) actually correct?**
  _`Proyecto` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Unidad` (e.g. with `batch_import()` and `actualizar()`) actually correct?**
  _`Unidad` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `SQLAlchemy engine + session factory.`, `FastAPI dependency: yields a SQLAlchemy session per request.`, `FastAPI dependencies for auth: extract user from Authorization header.` to the rest of the system?**
  _401 weakly-connected nodes found - possible documentation gaps or missing edges._