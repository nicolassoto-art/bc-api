# Graph Report - bc-api-sin-iva  (2026-10-29)

## Corpus Check
- 224 files · ~188,716 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2188 nodes · 3744 edges · 329 communities (143 shown, 186 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 314 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e966810b`
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
- find_jb_project.py
- Diagnostico de headers (fix 401)
- Ranking de pendientes Ingevec
- Investigacion de casos puntuales
- Diagnostico de tipos en marketplace
- Diagnostico de superficies por modelo
- Diagnostico del paginador de unidades
- db.py
- Diagnostico de tab Stock del workview
- Diagnostico de selector Tipo en Stock
- Fix de inmobiliaria placeholder
- Reimportacion de los 84 proyectos
- Revision consolidada de Ingevec
- Auditoria de issues de importacion
- Sincronizacion de modelos desde DOM
- Verificacion de import de detalle
- video_proyecto.py
- Descubrimiento del editor JetBrokers
- Tests del healthcheck
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
- Migracion inicial de base de datos
- Migracion: tabla inmobiliarias
- Migracion: timestamp de stock
- Migracion: tabla de tickets
- Migracion: borrado logico de proyecto
- Migracion: arriendo garantizado
- Restauracion de datos ViMa
- Diagnostico de unidades huerfanas
- Diagnostico de 3 proyectos (Vivaceta)
- Inspeccion cruda de unidades
- Reimportacion de 4 assets puntuales
- Verificacion de ambiguedad D/B
- Diagnostico depto sin planta (Vivaceta)
- Inicializador de dependencias
- Inicializador del paquete app
- Inicializador de rutas
- Inicializador de servicios
- Workflow de auditoria de superficies
- Chequeo de datos ViMa
- estado_stock
- Diagnostico completo Vivaceta
- Inicializador de tests
- check
- verify_jb_assets.py
- Auditoría profunda — Modelos y Stock
- verify_jb_visual.py
- Registro de imports a bc-api
- diag_csv_batch.py
- diag_api_explore.py
- audit_aj_urbana_freshness.py
- import_marketplace_workview.py
- diag_bod_raw.py
- diag_chips_full.py
- diag_csv_batch.py
- diag_vm_cotizar.py
- diag_vm_typesel.py
- diag_workview.py
- diag_stock_total.py
- parse_tipologia
- __init__.py
- 2026_07_23_0000-008_ultima_revision_at.py
- 2026_07_23_0100-009_ticket_resolucion.py
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
- vps_install.sh
- zadarma.py
- _catalogo_vs_stock
- env.py
- audit_aj_urbana_freshness.py
- clasificar_csv.py
- _compat_types.py
- diag_api_explore.py
- diag_auth.py
- diag_detail.py
- diag_mkt_stock.py
- diag_pipeline.py
- diag_stock_extra.py
- discover_jb_editor.py
- inspect_marketplace_workview.py
- patch_modelo_huerfanas.py
- capacitaciones_hls.py
- review_all.py
- review_full.py
- tickets.py
- 2026_09_24_0000-010_reserva_bc.py
- audit_modelos_stock.py
- audit_proyectos.py
- documentos.py
- test_video_proyecto.py
- diag_chips_full.py
- diag_euro.py
- diag_investigate.py
- diag_mkt_types.py
- diag_modelo_superficies.py
- test_video_proyecto.py
- firma_api
- test_estado_stock.py
- diag_vm_scroll2.py
- diag_vm_scroll.py
- diag_vm_stock.py
- migrar_snapshot_viejo
- diag_vm_typesel.py
- fix_inmobiliaria_placeholder.py
- reimport_todos_84.py
- review_ingevec.py
- review_issues.py
- sync_modelos_from_dom.py
- test_llamadas_consulta.py
- verify_detail.py
- diag_usuario
- patch_publicar_catalogo.py
- audit_plantas_vs_uploads.py
- audit_superficies.py
- borrar_placeholders.py
- check_ambig.py
- check_proyecto.py
- check_stock_loc.py
- check_stock_recencia.py
- diag_abdon.py
- diag_etiquetas.py
- diag_novus_g.py
- diag_terrazzo.py
- diag_totales.py
- diag_vivaceta.py
- inspect_huerfanas.py
- inspect_stock.py
- limpiar_modelos_sin_unidades.py
- patch_reserva.py
- patch_totals.py
- reimport_7_puntuales.py
- test_save.py
- Workflow: Audit fotos+plantas vs JB
- Workflow: Audit Plantas
- Workflow: Diag Click (detalle real)
- Workflow: Diag completo proyecto (qué falta)
- Workflow: Diag detail page (proyectos propios)
- Workflow: Diag filtros unidades
- Workflow: Diag investigate (Terrazzo + 0-uds + Abdón)
- Workflow: Diag paginador unidades
- Workflow: Diag vm scroll
- Workflow: Diag vm scroll
- diag_investigate.py
- BaseModel
- Session
- BaseModel
- Session
- UploadFile
- BaseModel
- Session
- UploadFile
- Session
- BackgroundTasks
- Session
- UploadFile
- BaseModel
- BaseModel
- BaseModel
- Session
- diag_modelo_superficies.py
- datetime
- Client
- Path
- Path
- Client
- datetime
- Path
- Path
- Path
- AsyncClient
- diag_etiquetas_jb.py
- diag_paginador.py
- origen_stock.py
- _SMTP
- diag_workview.py
- ._log_timeline_evento
- rank_pendientes.py
- .build_jb_style_excel
- _build_idx_map
- inspect_marketplace_workview.py
- diag_bod_raw.py
- diag_detail_page.py
- diag_filtros_unidades.py
- diag_paginador_unidades.py
- diag_rosas.py
- diag_vm_scroll2.py
- diag_vm_typesel.py
- diag_workview.py
- diag_usuario
- _respetar_reserva_bc
- main
- main
- patch_publicar_catalogo.py
- Workflow: Import detail (proyecto propio)
- BaseModel
- Session
- Session
- Any
- datetime
- Any
- datetime
- Any
- AsyncClient
- Exception
- Path
- RuntimeError
- date
- datetime
- Session
- Any
- datetime

## God Nodes (most connected - your core abstractions)
1. `JBImporter` - 89 edges
2. `Proyecto` - 60 edges
3. `Usuario` - 58 edges
4. `Llamada` - 54 edges
5. `estado_stock()` - 34 edges
6. `Unidad` - 31 edges
7. `subir_excel()` - 27 edges
8. `build_daily_report()` - 21 edges
9. `_ficha()` - 20 edges
10. `_proy()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `main()` --indirect_call--> `Llamada`  [INFERRED]
  scripts/zadarma_sincronizar.py → app/models/llamada.py
- `llamada()` --indirect_call--> `Llamada`  [INFERRED]
  tests/test_evaluador_llamadas.py → app/models/llamada.py
- `llamadas()` --indirect_call--> `Llamada`  [INFERRED]
  tests/test_llamadas_consulta.py → app/models/llamada.py
- `proyecto()` --indirect_call--> `Proyecto`  [INFERRED]
  tests/test_video_proyecto.py → app/models/proyecto.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/backfill_codigo_corto.py → app/models/proyecto.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **** — github_workflows_import_jb_workflow, github_workflows_batch_import_jb_workflow, github_workflows_monitor_health_workflow [EXTRACTED 1.00]
- **** — eventos_registro, concept_eventos_anomalos_jsonl, github_workflows_registrar_eventos_workflow [EXTRACTED 1.00]

## Communities (329 total, 186 thin omitted)

### Community 0 - "Rutas admin: informes e inmobiliarias"
Cohesion: 0.08
Nodes (45): Proyecto, alertas_proyecto(), comercial_broker(), crear(), detalle(), detalle_publico(), eliminar(), _estado_stock_seguro() (+37 more)

### Community 1 - "Rutas de unidades (deptos)"
Cohesion: 0.17
Nodes (23): actualizar(), crear(), crear_alerta_timeline(), crear_evento_timeline(), eliminar(), _ensure_project(), listar(), marcar_reserva_bc() (+15 more)

### Community 2 - "Servicio de email y alertas"
Cohesion: 0.11
Nodes (33): aplicar_patch(), clasificar(), descargar_y_preparar_imagen(), es_candidata(), escribir_summary(), health_check(), listar_imagenes(), listar_proyectos() (+25 more)

### Community 3 - "Gestion de inmobiliarias (catalogo)"
Cohesion: 0.11
Nodes (45): _aware(), es_alerta_stock_actualizado(), es_automatico(), _es_jetbrokers(), estado_stock(), grupo_publicacion(), motivo_legible(), _nombre_persona() (+37 more)

### Community 4 - "Reporte de importacion y utilidades scraping"
Cohesion: 0.10
Nodes (43): comercial_normalizado(), _ejemplos(), es_depto(), fallas_de_proyecto(), fallas_seguras(), _fisico(), _fmt_pct(), _it() (+35 more)

### Community 5 - "Infraestructura DB y autenticacion"
Cohesion: 0.16
Nodes (38): _unidad_dict(), _build_jb_extras(), Construye los campos de extra que el frontend lee: estacionamientos, bodegas, pa, _excel(), _hoja_unidad(), _proy(), _proyecto(), _put_proyecto() (+30 more)

### Community 6 - "Eventos anomalos y workflows batch"
Cohesion: 0.47
Nodes (6): Workflow: Batch import JB (encadenamiento dinámico, L-V 10-18 Chile), Workflow: Batch re-import (plantas + vacíos), Workflow: Import ALL pending JB (uno a la vez, hasta terminar), Workflow: Import JetBrokers project to bc-api, Workflow: List JetBrokers projects, Workflow: Monitor health bc-api + cadena import

### Community 7 - "Modulo JBImporter (importador core)"
Cohesion: 0.16
Nodes (9): llamada(), ModeloFalso, Evaluador de llamadas: puntaje, omisiones, reintentos y job con modelo simulado., test_job_evalua_pendiente(), test_job_no_toma_las_recien_llegadas(), test_job_registrado_en_el_programador(), test_job_reintenta_y_luego_error(), test_omite_anexos_que_no_son_setters() (+1 more)

### Community 8 - "Autenticacion y esquemas de sesion"
Cohesion: 0.06
Nodes (80): _actualizar(), admin_herramientas(), _agregar(), _api_url_para(), _arrancar_vigia(), _audios(), _avisar_falla(), _barrer_viejos() (+72 more)

### Community 9 - "Diagnosticos API JetBrokers"
Cohesion: 0.25
Nodes (6): main(), Backfill: fuerza comercial.precio_cotizacion='lista' en todos los proyectos que, main(), _norm(), Backfill: deducir Proyecto.region desde Proyecto.comuna.  Muchos proyectos impor, Lowercase + strip + sin tildes (para matchear 'Ñuñoa' con 'nunoa').

### Community 10 - "Descarga y gestion de assets JB"
Cohesion: 0.20
Nodes (15): check_baja_masiva(), get_jwt(), _is_depto(), sync_jb_stock.py — Sync liviano de stock JetBrokers → bc-api (bajo consumo JB)., Obtiene un JWT — prioriza BC_API_JWT (ya fresco), sino exchange con BC_TOKEN., Compara deptos disponibles actuales en bc-api vs los que trae el Excel nuevo., Tests de la guardia anti-baja-masiva de scripts/sync_jb_stock.py (pura, sin red/, test_baja_bajo_piso_absoluto_no_aborta() (+7 more)

### Community 12 - "Exportador Playwright del catalogo JB"
Cohesion: 0.08
Nodes (36): es_cuenta_automatica(), es_cuenta_robot(), etiqueta_origen(), _norm(), norm_inmobiliaria(), Etiqueta de origen para los eventos de stock del timeline — bc-api · 2026-09-01, Nombre de inmobiliaria normalizado (sin tildes, minúsculas, espacios colapsados), Nombre corto del robot de una inmobiliaria para mostrar a personas     ("robot I (+28 more)

### Community 14 - "Vista previa del informe diario"
Cohesion: 0.08
Nodes (25): _acquire_scheduler_lock(), diag_email(), diag_usuario(), preview_daily_report(), preview_fallas_fichas(), preview_fallas_pdf(), preview_pendientes_pdf(), bc-api · backend privado para Herramientas BigCapital.  Uvicorn entry: `uvicorn (+17 more)

### Community 15 - "Ruta de importacion batch (API)"
Cohesion: 0.10
Nodes (27): _es_protegido(), True si el proyecto no debe tocarse desde el import JB (salvo forzado explícito), asset_m2(), asset_num(), asset_uf(), emap(), facing_es(), fnum() (+19 more)

### Community 16 - "Generacion HTML del informe diario"
Cohesion: 0.18
Nodes (16): _cliente(), enmascarar(), evaluar_llamada(), evaluar_pendientes(), evaluar_transcripcion(), puntaje_total(), Any, Session (+8 more)

### Community 17 - "Reporte de actividad del operador"
Cohesion: 0.08
Nodes (16): _bajada_jb_habilitada(), BajadaJBApagada, _exigir_bajada_habilitada(), ImportReport, jb_importer.py — Importador JetBrokers → bc-api.  Módulo reusable. Diseñado para, Se intentó bajar stock de JetBrokers con la bajada apagada., Sentinel interno para saltar una sección de scrape_marketplace_workview     en m, Extrae modelos únicos desde el array de units, con sus blueprints. (+8 more)

### Community 19 - "Rutas de documentos del proyecto"
Cohesion: 0.50
Nodes (4): geocode(), main(), Geocodificar masivamente proyectos sin GPS usando Nominatim (OpenStreetMap).  83, Devuelve (lat, lon) o None si no resuelve.

### Community 21 - "Test de paridad DOM (JB vs BC)"
Cohesion: 0.12
Nodes (15): 1. Lista de proyectos de BigCapital (org `uv13koru`), 2. Detalle de proyecto (la ficha completa — 75 campos), 3. Modelos + plantas, 4. Unidades (stock individual), 5. Archivos (fotos + documentos), 6. Descarga de imágenes, API pública JetBrokers 7.43.1 — mapa completo (descubierto 2026-06-05), Autenticación (+7 more)

### Community 22 - "Rutas de imagenes del proyecto"
Cohesion: 0.17
Nodes (22): EmailMessage, Envía un email de respuesta al remitente original., _send_response(), Email INMEDIATO cuando algo falla (scraper, importación, etc.).      Lo emiten l, send_error_alert(), _configured(), enviar_html(), _esc() (+14 more)

### Community 23 - "Verificacion visual con IA (AI Vision)"
Cohesion: 0.07
Nodes (32): SQLAlchemy engine + session factory., Inmobiliaria, Catálogo maestro de inmobiliarias.  Antes vivía en localStorage del navegador de, Tickets de reporte de fallas (Fase 5).  Cualquier usuario autenticado de Herrami, Ticket, Usuario — auth and audit., actualizar(), crear() (+24 more)

### Community 24 - "Importacion desde export manual JB"
Cohesion: 0.11
Nodes (20): exchange_bc_token(), ExchangeIn, login(), me(), Exchange a legacy bc_token for a bc-api JWT.      Validates the token against th, LoginIn, TokenOut, UserOut (+12 more)

### Community 25 - "Motor del informe diario de stock"
Cohesion: 0.21
Nodes (27): _excel(), _marcar(), _pid(), _proyecto_con(), Marca "reservada por BigCapital" (reserva_bc) — 2026-09-24.  Nuestro stock y el, Segunda subida idéntica con la unidad marcada: debe quedar 'Sin cambios'., El editor reenvía la unidad completa desde una copia que puede ser vieja., El importador por lotes borra en bloque y recrea: la marca debe sobrevivir. (+19 more)

### Community 26 - "Calculo de metricas del informe diario"
Cohesion: 0.11
Nodes (12): Paginación robusta: detecta JB Angular custom (no Material/Bootstrap estándar)., Visita /projects/detail/{jb_id} y scrapea la tabla de unidades.          El deta, Scrapea la tabla Unidades con VIRTUAL SCROLL acumulando.         La tabla JB no, Parsea filas de la tabla Unidades del editor JB → unidades bc-api.         Mapea, Scrapea la tabla principal de la página actual. Devuelve lista de rows con cells, Click en un tab del editor JB por su label visible. Tolerante a icons/badges., Descarga SOLO el Excel de la tab 'Stock' del editor JB.          Pensado para sy, Scrapea un proyecto listado en el marketplace de JB (no editable por         nos (+4 more)

### Community 27 - "CI/CD, despliegue y seed inicial"
Cohesion: 0.17
Nodes (21): _clave_orden(), es_alerta(), fusionar_timeline(), parse_fecha(), Historia (timeline) de un proyecto — bc-api · 2026-10-05  La historia vive en `P, Fecha de un evento → datetime aware UTC, o None si no se puede leer.      Acepta, Tope de la historia. Conserva el orden recibido.      Se quedan: todo evento que, Historia que queda guardada después de un PUT del proyecto.      - `entrante` No (+13 more)

### Community 28 - "Test de paridad UI campo a campo"
Cohesion: 0.17
Nodes (14): diff_tab(), load_jb_data_from_import(), main(), _norm_label(), _norm_value(), verify_dom_diff.py — Test 6: Comparación DOM directa JB ↔ BC editor.  Determinís, Carga los datos JB del scrape exhaustivo del importer.     Mucho más confiable q, [DEPRECATED en favor de load_jb_data_from_import] (+6 more)

### Community 29 - "Motor de alertas de proyecto (criticos)"
Cohesion: 0.22
Nodes (13): _count_xlsx_rows(), _deptos(), _items_of(), main(), probe_api(), probe_dom(), probe_excel(), diag_scrape_live.py — Diagnóstico SOLO-LECTURA de las 3 fuentes de unidades del (+5 more)

### Community 30 - "Dry-run de importacion (solo lectura)"
Cohesion: 0.11
Nodes (29): _aplicar_excel(), _dominio_de(), _extract_body_text(), _extract_from_original(), _extraer_nombre_proyecto_del_excel(), _fetch_new(), _html_err(), _html_ok() (+21 more)

### Community 33 - "Borrado de proyecto antes de reimportar"
Cohesion: 0.29
Nodes (9): _dump_paginator(), _first(), main(), normalize_quote(), _num(), scrape_jb_quotes.py — Baja TODAS las cotizaciones de la organización desde JetBr, Diagnóstico (sin PII): vuelca la estructura del paginador de /quotes     para sa, Primer valor no vacío entre varios nombres de campo posibles. (+1 more)

### Community 34 - "Configuracion de la aplicacion (Settings)"
Cohesion: 0.18
Nodes (4): Path, correo (minúsculas) → anexo., Settings, BaseSettings

### Community 38 - "Reimportacion de proyectos multibloque"
Cohesion: 0.26
Nodes (12): bcapi_login(), bcapi_upload_foto_url(), bcapi_upsert(), foto_payloads(), get_detail(), list_projects(), main(), Importa proyectos desde la API pública del Cloudflare Worker de bigcapital.cl  L (+4 more)

### Community 39 - "Test visual: capturas JB vs BC"
Cohesion: 0.26
Nodes (12): bcapi_login(), bcapi_upsert(), filter_by_org(), main(), Importa proyectos desde un EXPORT MANUAL del usuario logueado en JetBroker.  Flu, Filtra proyectos cuya organization matchee org_query (case-insensitive, fuzzy)., Transforma proyecto JB → payload bc-api., to_bcapi_payload() (+4 more)

### Community 40 - "Permisos de acceso a Stock/Worker"
Cohesion: 0.33
Nodes (8): extraer(), _fecha(), main(), _pares(), datetime, Extrae las reuniones de las setters desde la foto de GHL (latest.json) para bc-a, main(), Diagnóstico (solo lectura) de las reuniones de las setters en la foto de GHL.  C

### Community 59 - "Script de instalacion en el VPS"
Cohesion: 0.26
Nodes (12): append_event(), detect_bc_anomalies(), detect_workflow_anomalies(), load_existing(), main(), now_chile(), now_iso(), registrar_eventos.py — Registra eventos anómalos detectados para revisión manual (+4 more)

### Community 62 - "Diagnostico de carga de detalle (click)"
Cohesion: 0.06
Nodes (20): main(), diag_etiquetas_jb.py — Scrapea las ETIQUETAS directo del editor JB para los 18 p, main(), Probar endpoints de DETALLE de modelo JB para encontrar las superficies (Sup Tot, main(), Dump simple del paginador de la tab Unidades (V.Mackenna 1796)., main(), Vuelca los controles de paginación de la tab Unidades de un proyecto JB. (+12 more)

### Community 64 - "Scraping de etiquetas JB"
Cohesion: 0.21
Nodes (12): ai_vision_compare(), _dismiss_jb_popups(), main(), normalize_val(), verify_jb_editor_walkthrough.py — Test 5: simulador humano clickeando tabs.  Abr, Normalize values for comparison., Abre BC editor, clickea cada tab, screenshot + extrae datos., JB muestra un modal '¿Ya descargaste nuestra APP?' que tapa los screenshots. (+4 more)

### Community 66 - "find_jb_project.py"
Cohesion: 0.29
Nodes (11): buscar(), _extraer_filas(), _goto_catalog(), main(), _norm(), _paginar_y_juntar(), _quitar_filtros(), find_jb_project.py — Busca un proyecto por NOMBRE en el catálogo JetBrokers (log (+3 more)

### Community 68 - "Ranking de pendientes Ingevec"
Cohesion: 0.15
Nodes (11): _claves(), _fila(), _naive(), _pid(), _Prog, _proyecto(), Correos "Stock interno" (proyectos sin revisar · fallas en fichas) — 2026-10-05., test_falla_que_vuelve_antes_de_7_dias_no_es_nueva() (+3 more)

### Community 69 - "Investigacion de casos puntuales"
Cohesion: 0.20
Nodes (9): Eventos anómalos — registro automático, 🚨 Fallos de workflow (132 en total, mostrando últimos 30), ℹ Batches fuera de ventana L-V 10-18 (140 en total, mostrando últimos 30), ℹ Errores leyendo GH CLI (1 en total, mostrando últimos 1), ℹ Inmobiliaria sin asignar (32 en total, mostrando últimos 30), ℹ Nombre stub no actualizado (2 en total, mostrando últimos 2), ℹ Workflows cancelados (280 en total, mostrando últimos 30), ⚠ Proyectos con modelos pero sin unidades (195 en total, mostrando últimos 30) (+1 more)

### Community 73 - "db.py"
Cohesion: 0.16
Nodes (25): acotar_rango(), alertas(), calidad(), cargar_reuniones(), _fin(), gestion_dia(), gestion_rango(), guardar_metas() (+17 more)

### Community 82 - "video_proyecto.py"
Cohesion: 0.13
Nodes (42): _ahora(), _bitrate(), _borrar_archivos(), calidades_con_respaldo(), cancelar(), _comando_hls(), _dir_trabajo(), elegir_calidades() (+34 more)

### Community 83 - "Descubrimiento del editor JetBrokers"
Cohesion: 0.20
Nodes (9): bc-api, Deploy automático (GitHub Actions), Endpoints (resumen), Operación, Pendiente / Roadmap, Primera instalación en el VPS, Seguridad, Setup local (dev) (+1 more)

### Community 84 - "Tests del healthcheck"
Cohesion: 0.47
Nodes (9): _card(), _imp(), Tests de JBImporter._parse_marketplace_unidades (pura, sin red/Playwright/DB)., test_descarta_cards_sin_numero(), test_flags_obligatorio_y_nunca(), test_modelo_faltante_usa_sm(), test_multiples_cards(), test_parsea_card_real_depto_1402() (+1 more)

### Community 99 - "Migracion inicial de base de datos"
Cohesion: 0.31
Nodes (8): main(), normalize(), verify_jb_ui_parity.py — Test 4: comparación UI campo-por-campo.  Abre BC vista, Scrape BC vista. Inyecta bc_api_token directo en localStorage para saltar login., Normaliza valor para comparación: lowercase, sin acentos, sin espacios extra., Scrape el tab General del editor JB. Retorna lista de {section, label, value}., scrape_bc_vista(), scrape_jb_general()

### Community 101 - "Migracion: timestamp de stock"
Cohesion: 0.11
Nodes (37): conteo_stock_interno(), preview_stock_sin_revisar(), HTML del correo «proyectos sin revisar» con datos reales, SIN enviarlo., Números para decidir el encendido: fichas por regla (y % del total), fallas por, _registrar_resultado_informe(), asunto_fallas(), asunto_sin_revisar(), _avisar_error() (+29 more)

### Community 102 - "Migracion: tabla de tickets"
Cohesion: 0.25
Nodes (7): Auditoría profunda — Modelos y Stock, 📋 Detalle por proyecto, 📈 Estadísticas globales, ⚠ Proyectos con modelos pero NINGUNO con planta_url (6), ⚠ Proyectos con unidades huérfanas (5), ⚠ Proyectos sin modelos (7), ⚠ Proyectos sin unidades (13)

### Community 103 - "Migracion: borrado logico de proyecto"
Cohesion: 0.43
Nodes (7): _limpiar_viejos(), main(), Backup diario del stock (proyectos + unidades + imagenes + documentos).  Corre p, _serializar_documento(), _serializar_imagen(), _serializar_proyecto(), _serializar_unidad()

### Community 104 - "Migracion: arriendo garantizado"
Cohesion: 0.29
Nodes (6): 2026-05-21 · Intento Larraín Prieto (JetBroker), 2026-05-21 · Seed inicial (Pinar 1 + 2), 2026-05-22 · Hallazgo: bigcapital.cl Worker API es pública, Cómo importar desde el snapshot de JetBroker (referencia), Próximos imports (TODO), Registro de imports a bc-api

### Community 110 - "Verificacion de ambiguedad D/B"
Cohesion: 0.38
Nodes (6): list_pending(), main(), batch_import_jb.py — Orquestador para importar tandas de N proyectos JB pendient, Devuelve proyectos del catálogo JB que NO están en bc-api., Dispara import-jb.yml workflow y espera. Retorna (success, run_id)., trigger_import()

### Community 111 - "Diagnostico depto sin planta (Vivaceta)"
Cohesion: 0.43
Nodes (6): bp_id(), derive_tipo(), main(), norm(), dryrun_project.py — Validación DRY-RUN (solo lectura) de un proyecto con el pipe, blueprint puede venir como string (proyectos propios) o dict {id} (marketplace).

### Community 112 - "Inicializador de dependencias"
Cohesion: 0.38
Nodes (6): list_via_api(), list_via_dom(), main(), list_jb_projects.py — Lista TODOS los proyectos del broker en JB.  Output: JSON, Intenta varios endpoints API conocidos de JB., Scrape DOM del Catálogo (vista Tabla) en JB.     Aplica filtro Disponible=Sí + J

### Community 113 - "Inicializador del paquete app"
Cohesion: 0.52
Nodes (6): asset_m2(), asset_num(), asset_uf(), _fnum(), main(), patch_stock.py — Refresca estac/bodegas/packs de un proyecto SIN wipe. Trae el m

### Community 114 - "Inicializador de rutas"
Cohesion: 0.43
Nodes (6): batch_import(), bcapi_login(), find_multibloque(), main(), Re-importa proyectos multibloque (con números de unidad duplicados).  Estos proy, Devuelve proyectos que tienen números de depto duplicados (multibloque).

### Community 115 - "Inicializador de servicios"
Cohesion: 0.38
Nodes (6): build_numero_to_unitid_map(), main(), scrape_superficies_individual.py — Para los 5 proyectos sin desglose (Conexión I, Scrapea la tab Unidades y devuelve {numero → jb_unit_id} desde href., Abre /units/edit/{id} y lee Total/Interior/Terraza/Logia/Jardín., read_unit_surfaces()

### Community 117 - "Chequeo de datos ViMa"
Cohesion: 0.43
Nodes (6): find_proyecto_by_jb_id(), get_jwt(), main(), wipe_proyecto_jb.py — Borra TODO de un proyecto antes de re-importar limpio.  Es, Busca proyecto cuyo extra.jb_id == jb_id., wipe()

### Community 118 - "estado_stock"
Cohesion: 0.67
Nodes (3): main(), _mask(), diag_auth.py — Resuelve el 401: ¿es el header de versión (7.42.0 vs 7.43.1) o el

### Community 119 - "Diagnostico completo Vivaceta"
Cohesion: 0.18
Nodes (18): batch_import(), BatchImportRequest, BatchImportResult, _build_notas(), ImportDetail, _make_proyecto(), _make_unidades(), _normalize_jb_photo_url() (+10 more)

### Community 121 - "Inicializador de tests"
Cohesion: 0.12
Nodes (18): _build_html(), _calidad_band(), _catalogo_vs_stock_html(), _disclaimer_html(), _editor_url(), _faltantes_html(), _kpi_cell(), _proj_inline() (+10 more)

### Community 122 - "check"
Cohesion: 0.47
Nodes (5): check(), gp(), main(), debug_general.py — Debug exhaustivo de todos los proyectos importados v2. Detect, Devuelve lista de (nivel, mensaje) — nivel: ERROR/WARN/INFO.

### Community 123 - "verify_jb_assets.py"
Cohesion: 0.47
Nodes (5): count_jb_assets(), head_url(), main(), verify_jb_assets.py — Test 2: paridad de assets (fotos, planos, documentos).  1., Navegar JB editor → tab Documentos → contar por tipo (fotos/planos/docs).

### Community 124 - "Auditoría profunda — Modelos y Stock"
Cohesion: 0.19
Nodes (8): classify(), _get_path(), main(), _normalize(), verify_jb_fields.py — Test 1: comparación campo-a-campo JB editor DOM vs bc-api, Llama /api/project-file/{jb_id}/list/0 para listar todos los archivos del proyec, Descarga TODOS los archivos del proyecto (fotos+planos+docs) + cover., Llama endpoints API JB para extraer la metadata base + unidades + modelos.

### Community 125 - "verify_jb_visual.py"
Cohesion: 0.47
Nodes (5): main(), verify_jb_visual.py — Test 3: screenshots side-by-side de JB editor vs BC vista., Usa una segunda página de Playwright (reusar mismo browser para ahorrar)., screenshot_bc_tabs(), screenshot_jb_tabs()

### Community 126 - "Registro de imports a bc-api"
Cohesion: 0.08
Nodes (63): _actualizar(), _archivo_codigo(), _armar_combos(), _armar_zip(), _arrancar_vigia(), _barrer(), borrar_clip(), _clave() (+55 more)

### Community 129 - "audit_aj_urbana_freshness.py"
Cohesion: 0.60
Nodes (4): _es_depto(), main(), _norm(), Backfill: deriva tipologia="{d}D{b}B" para unidades-depto sin tipología, usando

### Community 130 - "import_marketplace_workview.py"
Cohesion: 0.29
Nodes (5): get_jwt(), import_jb.py — CLI thin wrapper sobre JBImporter.  Uso:   python3 scripts/import, Obtiene un JWT — prioriza BC_API_JWT (ya fresco), sino exchange con BC_TOKEN., run_all(), run_one()

### Community 133 - "diag_csv_batch.py"
Cohesion: 0.50
Nodes (4): main(), diag_csv_batch.py — Diagnóstico read-only de los 20 proyectos del CSV de Ingevec, Sluggify igual que bc-api: minúsculas, sin acentos, espacios → guiones., slugify()

### Community 137 - "diag_stock_total.py"
Cohesion: 0.11
Nodes (17): Llamada, motivo_para_omitir(), dia(), _ll(), Gestión diaria de las setters, sincronización con Zadarma y accesos., test_acceso_informes(), test_calidad_por_paso(), test_calidad_promedio_ignora_sin_puntaje() (+9 more)

### Community 138 - "parse_tipologia"
Cohesion: 0.50
Nodes (4): main(), parse_tipologia(), fix_huerfanas_modelos.py — Para cada unidad huérfana (modelo no existe en extra., 1D-1B → (1,1); 2D2B → (2,2); 3D-2B(5) → (3,2).

### Community 139 - "__init__.py"
Cohesion: 0.12
Nodes (13): Smoke test del CRUD de proyectos., Si el server no tiene BC_API_SERVICE_TOKEN, el endpoint está deshabilitado., (23-sep-2026) Las dos listas que se cargan a mano en la ficha deben llegar al wo, Un proyecto que nunca cargó las listas nuevas sale igual que antes (sin las clav, Con token configurado, un Bearer incorrecto da 401 (antes de tocar la DB)., La ruta /public no debe ser capturada por /{proyecto_id}.     Sin token → 503/40, El catálogo público (allow-list) NUNCA debe exponer RUT, cuenta bancaria,     co, test_public_dict_no_filtra_datos_sensibles() (+5 more)

### Community 140 - "2026_07_23_0000-008_ultima_revision_at.py"
Cohesion: 0.67
Nodes (3): main(), diag_mkt_stock.py — Encuentra endpoints de estac/bodegas/packs en MARKETPLACE (r, summ()

### Community 141 - "2026_07_23_0100-009_ticket_resolucion.py"
Cohesion: 0.50
Nodes (4): clean_nombre(), main(), limpiar_nombres_modelos.py — Normaliza nombres de modelos y unidades.  Patrón JB, Si tiene patrón 'X - número - X - X' (3+ guiones), tomar primer segmento.     Si

### Community 142 - "check_proyecto.py"
Cohesion: 0.60
Nodes (4): get_path(), main(), patch_enums.py — Corrige NO-DESTRUCTIVAMENTE los enums crudos (inglés) de un pro, set_path()

### Community 143 - "check_stock_recencia.py"
Cohesion: 0.60
Nodes (4): main(), reimport_list.py — Re-importa una lista fija de proyectos que quedaron sin unida, trigger_and_wait(), units_count()

### Community 144 - "patch_reserva.py"
Cohesion: 0.50
Nodes (4): main(), verify_jb_all.py — Orquestador: corre los 3 tests en serie.  Exit code:   0 si t, Corre un script verify_jb_X.py como subproceso. Devuelve (returncode, last_lines, run_subprocess()

### Community 154 - "vps_install.sh"
Cohesion: 0.70
Nodes (4): die(), log(), vps_install.sh script, warn()

### Community 155 - "zadarma.py"
Cohesion: 0.08
Nodes (41): _anexo(), aplicar_evento(), enlace_grabacion(), _entero(), _ext(), _fecha(), fila_estadistica_a_campos(), firma_api() (+33 more)

### Community 156 - "_catalogo_vs_stock"
Cohesion: 0.14
Nodes (3): Informe de las 09:00 al equipo y fin del de las 13:00 — 2026-10-05., _SMTP, test_mejoras_cuentan_a_cualquier_persona_y_nunca_a_robots()

### Community 157 - "env.py"
Cohesion: 0.18
Nodes (11): Registra los jobs del programador según los flags. Devuelve los ids registrados., Dispara el informe diario manualmente (solo super_admin) y lo ENVÍA SOLO A QUIEN, _registrar_jobs(), trigger_daily_report(), _attach_pendientes_pdf(), Adjunta el PDF con TODOS los pendientes vigentes (persisten + nuevos). Si no, Disparado por APScheduler L-V 09am. Retorna el estado real del envío     ('envia, send_daily_report() (+3 more)

### Community 158 - "audit_aj_urbana_freshness.py"
Cohesion: 0.67
Nodes (3): main(), _parse_fecha(), audit_aj_urbana_freshness.py — Dead-man-switch de frescura para los 7 proyectos

### Community 159 - "clasificar_csv.py"
Cohesion: 0.67
Nodes (3): main(), clasificar_csv.py — Cruza el CSV master (92 proyectos JB) con lo importado en bc, slugify()

### Community 160 - "_compat_types.py"
Cohesion: 0.67
Nodes (3): main(), Reescribe sintaxis de tipos para que el código sea Python 3.9+ compatible.  PEP, transform()

### Community 161 - "diag_api_explore.py"
Cohesion: 0.11
Nodes (18): Re-export models for Alembic autogenerate + convenience., Llamadas de las setters (Zadarma) y registro crudo de los eventos recibidos.  `z, ZadarmaEvento, main(), datetime, Valida (solo lectura) lo que muestra el panel de Llamadas contra Zadarma y contr, traer(), main() (+10 more)

### Community 162 - "diag_auth.py"
Cohesion: 0.29
Nodes (13): _excel(), _proy(), Unidad NUEVA por Excel: descuento/bono con celda vacía quedan None ("sin dato"),, Excel JB mínimo con columnas Descuento y Bonopie en la hoja UNIDAD., Proyecto NUEVO por corrida: con un id fijo, una corrida anterior contra la misma, Un 0 que SÍ viene en el Excel es dato real de la fuente: se guarda 0., Regresión del camino de actualización: vacío sigue preservando lo cargado., _subir() (+5 more)

### Community 163 - "diag_detail.py"
Cohesion: 0.67
Nodes (3): main(), diag_detail.py — Caza el endpoint de DETALLE de proyecto en la API pública JB 7., _summ()

### Community 164 - "diag_mkt_stock.py"
Cohesion: 0.12
Nodes (21): boton(), card(), codigo(), dato(), email_html(), esc(), etiqueta(), h2() (+13 more)

### Community 165 - "diag_pipeline.py"
Cohesion: 0.67
Nodes (3): main(), diag_pipeline.py — Confirma el pipeline API-first completo de JB 7.43.1.  1. Cap, _summ()

### Community 166 - "diag_stock_extra.py"
Cohesion: 0.67
Nodes (3): main(), diag_stock_extra.py — Encuentra endpoints de estacionamientos/bodegas/packs (pro, summ()

### Community 167 - "discover_jb_editor.py"
Cohesion: 0.67
Nodes (3): log(), discover_jb_editor.py — Descubre qué expone el editor de JetBrokers para 1 proye, run()

### Community 168 - "inspect_marketplace_workview.py"
Cohesion: 0.17
Nodes (12): _age_hours(), _antiguedad_color(), build_daily_report(), _calidad_score(), _disp(), _eventos_24h(), _proyectos_activos(), Color del 'estado de salud' del stock según cuándo fue la última actualización. (+4 more)

### Community 169 - "patch_modelo_huerfanas.py"
Cohesion: 0.67
Nodes (3): main(), parse_db(), patch_modelo_huerfanas.py — Repara unidades con modelo="" en proyectos afectados

### Community 170 - "capacitaciones_hls.py"
Cohesion: 0.31
Nodes (12): alturas_para(), generar(), generar_async(), hls_de(), _mapa(), Any, Path, _raiz() (+4 more)

### Community 171 - "review_all.py"
Cohesion: 0.67
Nodes (3): gp(), main(), review_all.py — Revisión final consolidada de todos los proyectos importados v2.

### Community 173 - "tickets.py"
Cohesion: 0.09
Nodes (27): _campos_sin_iva(), _comparar_secundarios(), _desc_modificacion(), _fmt_val(), _lleva_con_iva(), _num_or_none(), _parse_jb_bodegas(), _parse_jb_estacionamientos() (+19 more)

### Community 175 - "2026_09_24_0000-010_reserva_bc.py"
Cohesion: 0.22
Nodes (10): _nombre_persona(), _quien_html(), Informe diario de stock — bc-api · 2026-06-08  Disparado por APScheduler L-V 09:, Una fila tipo tarjeta para el resumen., Resumen día a día de la semana anterior (informe del lunes): por cada día con, Hace 3h', 'Hace 2d 5h', 'Hace 14d', '—' si None. dt es naive UTC de bc-api., _resumen_semana_html(), _row() (+2 more)

### Community 188 - "test_video_proyecto.py"
Cohesion: 0.31
Nodes (9): actualizar(), DocumentoOut, ImagenOut, ImagenUpdate, ProyectoBase, ProyectoIn, ProyectoOut, BaseModel (+1 more)

### Community 191 - "diag_investigate.py"
Cohesion: 0.27
Nodes (10): Unidad, actualizar_arriendos(), descargar_plantilla(), _excel_legacy(), _is_depto(), _parse_dorm_banos(), Formato viejo de 1 sheet — fallback opcional., Actualiza arriendoGarantizado en lote para las unidades de un proyecto.      Bod (+2 more)

### Community 192 - "diag_mkt_types.py"
Cohesion: 0.06
Nodes (44): Documento, Imagen, Proyecto + entidades hijas (unidades, imágenes, documentos).  El modelo refleja, Red final: una unidad con marca de reserva nunca se guarda disponible.      Cubr, _respetar_reserva_bc(), DeclarativeBase, datos(), _iso() (+36 more)

### Community 193 - "diag_modelo_superficies.py"
Cohesion: 0.18
Nodes (26): alertas_hoy(), _anexo_propio(), calidad(), detalle_llamada(), fijar_metas(), _filtrar(), gestion(), gestion_rango() (+18 more)

### Community 197 - "diag_vm_scroll2.py"
Cohesion: 0.20
Nodes (10): _alertas_de_proyecto(), _catalogo_vs_stock(), _critico_key(), _is_depto(), _pendientes_actuales(), ¿La unidad es un departamento (no estac/bodega/pack)?, Genera TODAS las alertas (críticos + warnings) para un proyecto, con la MISMA, Compara, por proyecto, lo que el CATÁLOGO público mostrará contra el STOCK     I (+2 more)

### Community 198 - "diag_vm_scroll.py"
Cohesion: 0.28
Nodes (9): migrar_snapshot_viejo(), Saca report_snapshots.json de uploads/ (público) y lo deja en state_dir. Lo, Guarda el set de pendientes en el slot ('morning'). Escritura ATÓMICA     (tmp +, Compara los pendientes de AHORA contra el snapshot guardado en `slot` (el inform, _resolucion_cruce(), _snap_load(), _snap_path(), _snap_path_viejo() (+1 more)

### Community 200 - "migrar_snapshot_viejo"
Cohesion: 0.25
Nodes (15): _is_jb_excel(), _parse_jb_excel(), Parsea sheet UNIDAD del Excel JB → lista de dicts compatibles con bc-api.      R, Detecta si el .xlsx es formato JB (tiene los 4 sheets típicos)., run_one(), _imp(), Round-trip: JBImporter.build_jb_style_excel() -> app.routes.unidades._parse_jb_e, Regresión: encontrado en producción (unidad 1402, modelo "B") -- el     modelo d (+7 more)

### Community 207 - "test_llamadas_consulta.py"
Cohesion: 0.13
Nodes (4): Centralized settings loaded from environment via pydantic-settings., llamadas(), Panel de llamadas: listado, resumen, detalle y grabación (solo super admin)., Alembic env: usa el DATABASE_URL del .env y el metadata de los modelos.

### Community 209 - "diag_usuario"
Cohesion: 0.39
Nodes (8): _crear_proy(), _jb_excel(), Tests del flag permitir_sin_unidades en POST /proyectos/{id}/unidades/excel/uplo, Excel JB mínimo: UNIDAD (opcionalmente vacío) + ESTAC + BODEGA + INSTRUCCIONES., SEGURIDAD: un upload sin deptos + flag NO debe dar de baja deptos existentes., test_flag_no_da_de_baja_deptos_existentes(), test_unidad_vacia_con_flag_sincroniza_estac_bodega(), test_unidad_vacia_sin_flag_da_400()

### Community 210 - "patch_publicar_catalogo.py"
Cohesion: 0.29
Nodes (8): _es_cambio_manual(), _eventos_ventana(), _operador_actividad(), _operador_eventos_planos(), Eventos del timeline de un proyecto desde `cutoff` (datetime aware UTC).     Dev, Cambio hecho a mano por una persona del equipo: no es Alerta, no es automático, Cambios MANUALES de cualquier persona del equipo por proyecto en [cutoff, end)., Todos los movimientos MANUALES del equipo en [cutoff, end), aplanados con su

### Community 241 - "diag_investigate.py"
Cohesion: 0.17
Nodes (15): _clip(), _dur(), _entrar(), _generar_y_esperar(), _nivel(), Variaciones de video: acceso por código, subida por pedazos, combinaciones y ZIP, _subir(), test_archivo_que_no_es_video_se_rechaza() (+7 more)

### Community 262 - "diag_modelo_superficies.py"
Cohesion: 0.33
Nodes (6): _enriquecer_resueltos(), _hora_cl(), _operador_section_html(), Hora exacta del evento en Chile (≈UTC-4) con 'hoy/ayer'. Ej: 'ayer 14:32',     ', Bloque HTML "Mejoras …" como LÍNEA DE TIEMPO: una fila por movimiento ordenada, Agrega a cada pendiente 'resuelto' la HORA en que se solucionó: el último cambio

### Community 282 - "diag_etiquetas_jb.py"
Cohesion: 0.33
Nodes (5): Fuentes de stock: SJB vs SBC, y qué proyectos NO tocar desde JetBrokers, Las dos fuentes, Pasar un proyecto de SJB a SBC, Precio Final de JetBrokers ≠ `precio_final_uf`, ⛔ Proyectos protegidos

### Community 283 - "diag_paginador.py"
Cohesion: 0.50
Nodes (4): count_jb_assets(), main(), audit_assets_vs_jb.py — Audita fotos+plantas en bc-api y compara con JB.  1. Lis, Navega a /projects/edit/{jb_id} → tab Documentos y cuenta tipos.

### Community 285 - "_SMTP"
Cohesion: 0.50
Nodes (3): main(), import_marketplace_workview.py — Importa un proyecto de marketplace/workview (pr, run()

### Community 286 - "diag_workview.py"
Cohesion: 0.14
Nodes (19): current_user(), lector_informes(), Session, FastAPI dependencies for auth: extract user from Authorization header., Valida el token de servicio del Cloudflare Worker (catálogo público).      Compa, Super admin o lectores de Informes (settings.informes_lectores): pestaña Llamada, Acceso a Stock propio: super admin O usuario con permiso de stock.      El permi, service_token() (+11 more)

### Community 288 - "rank_pendientes.py"
Cohesion: 0.50
Nodes (4): find_stock_fields(), main(), diag_stock_total.py — Para los 5 proyectos sin unidades, consulta la API JB y du, Recorre recursivamente el JSON y devuelve campos numéricos cuyo nombre     sugie

### Community 289 - ".build_jb_style_excel"
Cohesion: 0.67
Nodes (3): metrica(), Request, Calidad de reproducción real (pausas, calidad, velocidad). Solo va al registro,

### Community 290 - "_build_idx_map"
Cohesion: 0.50
Nodes (4): _build_idx_map(), _normalize_label(), Mapea índice de columna → bc-api key, con matching robusto (case+tildes+sinónimo, Normaliza header: sin tildes, lowercase, sin puntos, espacios normalizados.

### Community 292 - "inspect_marketplace_workview.py"
Cohesion: 0.67
Nodes (3): main(), inspect_marketplace_workview.py — Reconocimiento de una URL /marketplace/workvie, run()

## Knowledge Gaps
- **135 isolated node(s):** `TicketOut`, `📈 Estadísticas globales`, `📋 Detalle por proyecto`, `⚠ Proyectos sin unidades (13)`, `⚠ Proyectos sin modelos (7)` (+130 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **186 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JBImporter` connect `Diagnostico de carga de detalle (click)` to `import_marketplace_workview.py`, `diag_csv_batch.py`, `2026_07_23_0000-008_ultima_revision_at.py`, `Ruta de importacion batch (API)`, `Reporte de actividad del operador`, `Calculo de metricas del informe diario`, `origen_stock.py`, `Motor de alertas de proyecto (criticos)`, `_SMTP`, `._log_timeline_evento`, `rank_pendientes.py`, `Borrado de proyecto antes de reimportar`, `diag_detail.py`, `inspect_marketplace_workview.py`, `diag_pipeline.py`, `diag_bod_raw.py`, `diag_detail_page.py`, `diag_filtros_unidades.py`, `diag_paginador_unidades.py`, `diag_rosas.py`, `diag_stock_extra.py`, `diag_vm_scroll2.py`, `diag_vm_typesel.py`, `diag_usuario`, `_respetar_reserva_bc`, `main`, `main`, `diag_workview.py`, `documentos.py`, `diag_chips_full.py`, `diag_euro.py`, `test_video_proyecto.py`, `firma_api`, `test_estado_stock.py`, `diag_vm_stock.py`, `migrar_snapshot_viejo`, `diag_vm_typesel.py`, `Migracion: tabla inmobiliarias`, `Diagnostico depto sin planta (Vivaceta)`, `Inicializador del paquete app`, `estado_stock`, `Auditoría profunda — Modelos y Stock`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Why does `run_one()` connect `migrar_snapshot_viejo` to `Descarga y gestion de assets JB`, `Diagnostico de carga de detalle (click)`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `Proyecto` connect `Rutas admin: informes e inmobiliarias` to `Rutas de unidades (deptos)`, `audit_aj_urbana_freshness.py`, `Gestion de inmobiliarias (catalogo)`, `Infraestructura DB y autenticacion`, `Diagnosticos API JetBrokers`, `Vista previa del informe diario`, `Rutas de documentos del proyecto`, `Importador desde bigcapital.cl Worker`, `Verificacion visual con IA (AI Vision)`, `Motor del informe diario de stock`, `CI/CD, despliegue y seed inicial`, `_catalogo_vs_stock`, `Dry-run de importacion (solo lectura)`, `diag_workview.py`, `diag_api_explore.py`, `diag_auth.py`, `inspect_marketplace_workview.py`, `test_video_proyecto.py`, `diag_mkt_types.py`, `Ranking de pendientes Ingevec`, `diag_usuario`, `video_proyecto.py`, `Migracion: timestamp de stock`, `Migracion: borrado logico de proyecto`, `Diagnostico completo Vivaceta`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Are the 47 inferred relationships involving `JBImporter` (e.g. with `main()` and `main()`) actually correct?**
  _`JBImporter` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 48 inferred relationships involving `Proyecto` (e.g. with `normalize_inmobiliarias()` and `actualizar()`) actually correct?**
  _`Proyecto` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Usuario` (e.g. with `_token_para()` and `exchange_bc_token()`) actually correct?**
  _`Usuario` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Llamada` (e.g. with `detalle_llamada()` and `grabacion_llamada()`) actually correct?**
  _`Llamada` has 31 INFERRED edges - model-reasoned connections that need verification._