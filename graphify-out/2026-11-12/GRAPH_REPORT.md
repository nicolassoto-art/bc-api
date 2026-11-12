# Graph Report - bc-api-planes  (2026-11-10)

## Corpus Check
- 239 files · ~207,624 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2505 nodes · 4645 edges · 340 communities (145 shown, 195 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 292 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4056c34b`
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
- aplicar_lectura
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
- llamada.py
- _build_idx_map
- 2026_10_21_0000-013_llamadas.py
- inspect_marketplace_workview.py
- diag_bod_raw.py
- diag_detail_page.py
- diag_paginador_unidades.py
- diag_rosas.py
- diag_vm_scroll2.py
- Reglas del proyecto
- diag_workview.py
- patch_publicar_catalogo.py
- Workflow: Import detail (proyecto propio)
- Session
- Session
- Any
- datetime
- Any
- datetime
- date
- datetime
- Session
- Any
- datetime
- Path
- Any
- AsyncClient
- BaseModel
- Exception
- Path
- Request
- RuntimeError
- UploadFile
- Any
- BackgroundTasks
- BaseModel
- Path
- Request
- Any
- Session
- datetime
- Session
- datetime
- Path

## God Nodes (most connected - your core abstractions)
1. `JBImporter` - 89 edges
2. `Proyecto` - 78 edges
3. `Usuario` - 69 edges
4. `_proy()` - 45 edges
5. `Llamada` - 43 edges
6. `_plan()` - 43 edges
7. `_patch()` - 38 edges
8. `_proyecto_con()` - 36 edges
9. `_unidad()` - 36 edges
10. `Unidad` - 35 edges

## Surprising Connections (you probably didn't know these)
- `test_sincronizar_idempotente()` --indirect_call--> `Llamada`  [INFERRED]
  tests/test_gestion_setters.py → app/models/llamada.py
- `llamadas()` --indirect_call--> `Llamada`  [INFERRED]
  tests/test_llamadas_consulta.py → app/models/llamada.py
- `limpio()` --indirect_call--> `Proyecto`  [INFERRED]
  tests/test_video_compartido.py → app/models/proyecto.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/backfill_codigo_corto.py → app/models/proyecto.py
- `main()` --indirect_call--> `Proyecto`  [INFERRED]
  scripts/backfill_precio_cotizacion_lista.py → app/models/proyecto.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **** — github_workflows_import_jb_workflow, github_workflows_batch_import_jb_workflow, github_workflows_monitor_health_workflow [EXTRACTED 1.00]
- **** — eventos_registro, concept_eventos_anomalos_jsonl, github_workflows_registrar_eventos_workflow [EXTRACTED 1.00]

## Communities (340 total, 195 thin omitted)

### Community 0 - "Rutas admin: informes e inmobiliarias"
Cohesion: 0.06
Nodes (61): Proyecto, actualizar(), alertas_proyecto(), comercial_broker(), crear(), detalle(), _detalle_garantia(), _detalle_planes() (+53 more)

### Community 1 - "Rutas de unidades (deptos)"
Cohesion: 0.07
Nodes (61): Unidad, actualizar(), actualizar_arriendos(), _campos_sin_iva(), _canon_de(), _comparar_secundarios(), crear(), crear_alerta_timeline() (+53 more)

### Community 2 - "Servicio de email y alertas"
Cohesion: 0.11
Nodes (33): aplicar_patch(), clasificar(), descargar_y_preparar_imagen(), es_candidata(), escribir_summary(), health_check(), listar_imagenes(), listar_proyectos() (+25 more)

### Community 3 - "Gestion de inmobiliarias (catalogo)"
Cohesion: 0.07
Nodes (64): _aware(), es_alerta_stock_actualizado(), es_automatico(), _es_jetbrokers(), estado_stock(), grupo_publicacion(), motivo_legible(), _nombre_persona() (+56 more)

### Community 4 - "Reporte de importacion y utilidades scraping"
Cohesion: 0.06
Nodes (72): _actualizar(), admin_herramientas(), _agregar(), _api_url_para(), _arrancar_vigia(), _audios(), _avisar_falla(), _barrer_viejos() (+64 more)

### Community 5 - "Infraestructura DB y autenticacion"
Cohesion: 0.12
Nodes (46): _unidad_dict(), _build_jb_extras(), Construye los campos de extra que el frontend lee: estacionamientos, bodegas, pa, Estacionamientos y bodegas con «ValorUF» / «Sup Total» (Excel de Ingevec) — 2026, test_ingevec_valoruf_y_sup_total_llegan_al_precio_y_superficie(), test_pack_suma_con_valoruf(), test_precio_uf_vacio_usa_valoruf_y_sin_ninguno_queda_none(), test_precio_uf_y_superficie_mandan_si_vienen_los_dos_nombres() (+38 more)

### Community 6 - "Eventos anomalos y workflows batch"
Cohesion: 0.47
Nodes (6): Workflow: Batch import JB (encadenamiento dinámico, L-V 10-18 Chile), Workflow: Batch re-import (plantas + vacíos), Workflow: Import ALL pending JB (uno a la vez, hasta terminar), Workflow: Import JetBrokers project to bc-api, Workflow: List JetBrokers projects, Workflow: Monitor health bc-api + cadena import

### Community 7 - "Modulo JBImporter (importador core)"
Cohesion: 0.13
Nodes (17): dia(), _ll(), test_calidad_por_paso(), test_calidad_promedio_ignora_sin_puntaje(), test_horarios_sin_eco(), test_job_una_llamada_rara_no_frena_el_lote(), Llamada, main() (+9 more)

### Community 8 - "Autenticacion y esquemas de sesion"
Cohesion: 0.08
Nodes (57): _actualizar(), _archivo_codigo(), _armar_combos(), _armar_zip(), _arrancar_vigia(), _barrer(), borrar_clip(), _clave() (+49 more)

### Community 9 - "Diagnosticos API JetBrokers"
Cohesion: 0.50
Nodes (4): main(), _norm(), Backfill: deducir Proyecto.region desde Proyecto.comuna.  Muchos proyectos impor, Lowercase + strip + sin tildes (para matchear 'Ñuñoa' con 'nunoa').

### Community 10 - "Descarga y gestion de assets JB"
Cohesion: 0.09
Nodes (34): _build_idx_map(), _is_jb_excel(), _normalize_label(), _parse_jb_excel(), Mapea índice de columna → bc-api key, con matching robusto (case+tildes+sinónimo, Parsea sheet UNIDAD del Excel JB → lista de dicts compatibles con bc-api.      R, Detecta si el .xlsx es formato JB (tiene los 4 sheets típicos)., Normaliza header: sin tildes, lowercase, sin puntos, espacios normalizados. (+26 more)

### Community 12 - "Exportador Playwright del catalogo JB"
Cohesion: 0.08
Nodes (36): es_cuenta_automatica(), es_cuenta_robot(), etiqueta_origen(), _norm(), norm_inmobiliaria(), Etiqueta de origen para los eventos de stock del timeline — bc-api · 2026-09-01, Nombre de inmobiliaria normalizado (sin tildes, minúsculas, espacios colapsados), Nombre corto del robot de una inmobiliaria para mostrar a personas     ("robot I (+28 more)

### Community 14 - "Vista previa del informe diario"
Cohesion: 0.08
Nodes (22): _acquire_scheduler_lock(), diag_email(), diag_usuario(), preview_pendientes_pdf(), bc-api · backend privado para Herramientas BigCapital.  Uvicorn entry: `uvicorn, Registra los jobs del programador según los flags. Devuelve los ids registrados., Dispara el informe diario manualmente (solo super_admin) y lo ENVÍA SOLO A QUIEN, PDF con el listado COMPLETO de pendientes vigentes (críticos, sin cortar —     p (+14 more)

### Community 15 - "Ruta de importacion batch (API)"
Cohesion: 0.10
Nodes (27): _es_protegido(), True si el proyecto no debe tocarse desde el import JB (salvo forzado explícito), asset_m2(), asset_num(), asset_uf(), emap(), facing_es(), fnum() (+19 more)

### Community 16 - "Generacion HTML del informe diario"
Cohesion: 0.17
Nodes (16): test_enmascarar_rut_y_telefonos(), test_puntaje_total_tolera_basura(), test_sync_prefiere_contestada_e_interna(), _cliente(), enmascarar(), evaluar_llamada(), evaluar_pendientes(), evaluar_transcripcion() (+8 more)

### Community 17 - "Reporte de actividad del operador"
Cohesion: 0.07
Nodes (17): ImportReport, AsyncClient, Path, Extrae modelos únicos desde el array de units, con sus blueprints., Llama /api/project-file/{jb_id}/list/0 para listar todos los archivos del proyec, Descarga TODOS los archivos del proyecto (fotos+planos+docs) + cover., Borra todas las Imagenes con categoria que empieza con 'jb-' o 'cover'., Sube TODOS los assets descargados a bc-api con categoria apropiada.          IDE (+9 more)

### Community 19 - "Rutas de documentos del proyecto"
Cohesion: 0.50
Nodes (4): geocode(), main(), Geocodificar masivamente proyectos sin GPS usando Nominatim (OpenStreetMap).  83, Devuelve (lat, lon) o None si no resuelve.

### Community 21 - "Test de paridad DOM (JB vs BC)"
Cohesion: 0.12
Nodes (15): 1. Lista de proyectos de BigCapital (org `uv13koru`), 2. Detalle de proyecto (la ficha completa — 75 campos), 3. Modelos + plantas, 4. Unidades (stock individual), 5. Archivos (fotos + documentos), 6. Descarga de imágenes, API pública JetBrokers 7.43.1 — mapa completo (descubierto 2026-06-05), Autenticación (+7 more)

### Community 22 - "Rutas de imagenes del proyecto"
Cohesion: 0.39
Nodes (6): _proyecto_con_externa(), Reemplazar el archivo de una foto (02-nov-2026): trae a nuestro disco las fotos, test_rechaza_pdf_vacio_y_ajena(), test_sin_sesion_401(), test_trae_externa_y_conserva_datos(), test_traer_externas_baja_y_reporta()

### Community 23 - "Verificacion visual con IA (AI Vision)"
Cohesion: 0.06
Nodes (41): Documento, SQLAlchemy engine + session factory., Inmobiliaria, Catálogo maestro de inmobiliarias.  Antes vivía en localStorage del navegador de, Tickets de reporte de fallas (Fase 5).  Cualquier usuario autenticado de Herrami, Ticket, Usuario — auth and audit., actualizar() (+33 more)

### Community 24 - "Importacion desde export manual JB"
Cohesion: 0.08
Nodes (52): _public_extra(), Allow-list: SOLO las claves seguras de extra van al catálogo público., _assert_evento(), _excel(), _extra(), _garantia(), _patch(), _proy() (+44 more)

### Community 25 - "Motor del informe diario de stock"
Cohesion: 0.14
Nodes (57): _envejecer(), _eventos(), _marca_antigua(), «PlanOk manda»: marca de reserva provisoria — 2026-11-06.  Los 10 escenarios del, Ofrecida → no ofrecida → ofrecida: el conteo vuelve a empezar., Mueve hacia atrás la hora de la marca y, si se pide, la de la 1ª vista disponibl, PlanOk ya no la ofrece (aunque no sea nuestra): PlanOk manda, sigue oculta., Una subida que bajaría ≥ 8 y ≥ 40 % de los disponibles es parcial: las marcas no (+49 more)

### Community 26 - "Calculo de metricas del informe diario"
Cohesion: 0.10
Nodes (17): JBImporter, Any, RuntimeError, Lee el valor de un input/select. Lo normaliza a string o None., Paginación robusta: detecta JB Angular custom (no Material/Bootstrap estándar)., Visita /projects/detail/{jb_id} y scrapea la tabla de unidades.          El deta, Scrapea la tabla Unidades con VIRTUAL SCROLL acumulando.         La tabla JB no, Parsea filas de la tabla Unidades del editor JB → unidades bc-api.         Mapea (+9 more)

### Community 27 - "CI/CD, despliegue y seed inicial"
Cohesion: 0.10
Nodes (51): comercial_normalizado(), _ejemplos(), es_depto(), fallas_de_proyecto(), fallas_seguras(), _fisico(), _fmt_pct(), _it() (+43 more)

### Community 28 - "Test de paridad UI campo a campo"
Cohesion: 0.17
Nodes (14): diff_tab(), load_jb_data_from_import(), main(), _norm_label(), _norm_value(), verify_dom_diff.py — Test 6: Comparación DOM directa JB ↔ BC editor.  Determinís, Carga los datos JB del scrape exhaustivo del importer.     Mucho más confiable q, [DEPRECATED en favor de load_jb_data_from_import] (+6 more)

### Community 29 - "Motor de alertas de proyecto (criticos)"
Cohesion: 0.22
Nodes (13): _count_xlsx_rows(), _deptos(), _items_of(), main(), probe_api(), probe_dom(), probe_excel(), diag_scrape_live.py — Diagnóstico SOLO-LECTURA de las 3 fuentes de unidades del (+5 more)

### Community 30 - "Dry-run de importacion (solo lectura)"
Cohesion: 0.10
Nodes (31): Dispara el procesador de inbox manualmente (solo super_admin). Lee emails con, trigger_inbox_poll(), _aplicar_excel(), _dominio_de(), _extract_body_text(), _extract_from_original(), _extraer_nombre_proyecto_del_excel(), _fetch_new() (+23 more)

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
Cohesion: 0.16
Nodes (21): asistencia_meet(), citas(), _contactos(), es_interna(), extraer(), _fecha(), main(), _nombres() (+13 more)

### Community 59 - "Script de instalacion en el VPS"
Cohesion: 0.26
Nodes (12): append_event(), detect_bc_anomalies(), detect_workflow_anomalies(), load_existing(), main(), now_chile(), now_iso(), registrar_eventos.py — Registra eventos anómalos detectados para revisión manual (+4 more)

### Community 62 - "Diagnostico de carga de detalle (click)"
Cohesion: 0.05
Nodes (32): _bajada_jb_habilitada(), BajadaJBApagada, _exigir_bajada_habilitada(), Exception, jb_importer.py — Importador JetBrokers → bc-api.  Módulo reusable. Diseñado para, Se intentó bajar stock de JetBrokers con la bajada apagada., Sentinel interno para saltar una sección de scrape_marketplace_workview     en m, _SkipSection (+24 more)

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
Nodes (9): Eventos anómalos — registro automático, 🚨 Fallos de workflow (143 en total, mostrando últimos 30), ℹ Batches fuera de ventana L-V 10-18 (150 en total, mostrando últimos 30), ℹ Errores leyendo GH CLI (1 en total, mostrando últimos 1), ℹ Inmobiliaria sin asignar (32 en total, mostrando últimos 30), ℹ Nombre stub no actualizado (2 en total, mostrando últimos 2), ℹ Workflows cancelados (300 en total, mostrando últimos 30), ⚠ Proyectos con modelos pero sin unidades (206 en total, mostrando últimos 30) (+1 more)

### Community 71 - "Diagnostico de superficies por modelo"
Cohesion: 0.10
Nodes (66): _c(), Centésimas, igual que el navegador: la cuadratura se compara en enteros., _bloquear(), _bloquear_y_escribir(), _en_hilo(), _excel_simple(), _extra(), _fila_libre() (+58 more)

### Community 73 - "db.py"
Cohesion: 0.14
Nodes (30): acotar_rango(), alertas(), calidad(), cargar_reuniones(), dias_del_rango(), _fin(), gestion_dia(), gestion_rango() (+22 more)

### Community 82 - "video_proyecto.py"
Cohesion: 0.11
Nodes (46): _ahora(), _bitrate(), _borrar_archivos(), calidades_con_respaldo(), cancelar(), _comando_hls(), _dir_trabajo(), elegir_calidades() (+38 more)

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
Cohesion: 0.10
Nodes (43): conteo_stock_interno(), preview_fallas_fichas(), preview_fallas_pdf(), preview_stock_sin_revisar(), HTML del correo «proyectos sin revisar» con datos reales, SIN enviarlo., HTML del correo «fallas en fichas» con datos reales, SIN enviarlo ni guardar est, PDF completo del correo «fallas en fichas», SIN enviarlo ni guardar estado., Números para decidir el encendido: fichas por regla (y % del total), fallas por (+35 more)

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
Cohesion: 0.16
Nodes (25): _clave(), codigo_compartir(), _proyecto_de(), Any, Video del edificio · link para enviar al cliente (31-oct-2026).  El video vigent, Código estable de 16 hex para el link del video de un proyecto., El video vigente del proyecto, solo si ya terminó de procesarse (estado «listo», _reconstruir_mapa() (+17 more)

### Community 121 - "Inicializador de tests"
Cohesion: 0.08
Nodes (28): preview_daily_report(), Devuelve el HTML del informe diario con los datos REALES de prod, SIN enviarlo, _build_html(), _calidad_band(), _catalogo_vs_stock_html(), _disclaimer_html(), _editor_url(), _faltantes_html() (+20 more)

### Community 122 - "check"
Cohesion: 0.47
Nodes (5): check(), gp(), main(), debug_general.py — Debug exhaustivo de todos los proyectos importados v2. Detect, Devuelve lista de (nivel, mensaje) — nivel: ERROR/WARN/INFO.

### Community 123 - "verify_jb_assets.py"
Cohesion: 0.47
Nodes (5): count_jb_assets(), head_url(), main(), verify_jb_assets.py — Test 2: paridad de assets (fotos, planos, documentos).  1., Navegar JB editor → tab Documentos → contar por tipo (fotos/planos/docs).

### Community 124 - "Auditoría profunda — Modelos y Stock"
Cohesion: 0.53
Nodes (5): classify(), _get_path(), main(), _normalize(), verify_jb_fields.py — Test 1: comparación campo-a-campo JB editor DOM vs bc-api

### Community 125 - "verify_jb_visual.py"
Cohesion: 0.47
Nodes (5): main(), verify_jb_visual.py — Test 3: screenshots side-by-side de JB editor vs BC vista., Usa una segunda página de Playwright (reusar mismo browser para ahorrar)., screenshot_bc_tabs(), screenshot_jb_tabs()

### Community 126 - "Registro de imports a bc-api"
Cohesion: 0.12
Nodes (21): boton(), card(), codigo(), dato(), email_html(), esc(), etiqueta(), h2() (+13 more)

### Community 129 - "audit_aj_urbana_freshness.py"
Cohesion: 0.12
Nodes (32): normalize_inmobiliarias(), Unifica EN EL SISTEMA las inmobiliarias que son la misma con distinto tipeo, Imagen, Proyecto + entidades hijas (unidades, imágenes, documentos).  El modelo refleja, Red final: una unidad con marca de reserva nunca se guarda disponible, salvo, _respetar_reserva_bc(), actualizar(), eliminar() (+24 more)

### Community 130 - "import_marketplace_workview.py"
Cohesion: 0.29
Nodes (5): get_jwt(), import_jb.py — CLI thin wrapper sobre JBImporter.  Uso:   python3 scripts/import, Obtiene un JWT — prioriza BC_API_JWT (ya fresco), sino exchange con BC_TOKEN., run_all(), run_one()

### Community 133 - "diag_csv_batch.py"
Cohesion: 0.50
Nodes (4): main(), diag_csv_batch.py — Diagnóstico read-only de los 20 proyectos del CSV de Ingevec, Sluggify igual que bc-api: minúsculas, sin acentos, espacios → guiones., slugify()

### Community 137 - "diag_stock_total.py"
Cohesion: 0.09
Nodes (12): _extractor(), Gestión diaria de las setters, sincronización con Zadarma y accesos., test_acceso_informes(), test_eco_4444_no_cuenta(), test_endpoint_reuniones_mismo_filtro(), test_extractor_cohorte_meet_y_pruebas(), test_lista_de_agendadas_cuadra_con_la_cifra(), test_metas_editables() (+4 more)

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
Cohesion: 0.17
Nodes (20): batch_import(), BatchImportRequest, BatchImportResult, _build_notas(), ImportDetail, _make_proyecto(), _make_unidades(), _normalize_jb_photo_url() (+12 more)

### Community 156 - "_catalogo_vs_stock"
Cohesion: 0.10
Nodes (5): Centralized settings loaded from environment via pydantic-settings., Alembic env: usa el DATABASE_URL del .env y el metadata de los modelos., Informe de las 09:00 al equipo y fin del de las 13:00 — 2026-10-05., _SMTP, test_mejoras_cuentan_a_cualquier_persona_y_nunca_a_robots()

### Community 157 - "env.py"
Cohesion: 0.13
Nodes (28): EmailMessage, Envía un email de respuesta al remitente original., _send_response(), _attach_pendientes_pdf(), Adjunta el PDF con TODOS los pendientes vigentes (persisten + nuevos). Si no, Disparado por APScheduler L-V 09am. Retorna el estado real del envío     ('envia, Email INMEDIATO cuando algo falla (scraper, importación, etc.).      Lo emiten l, send_daily_report() (+20 more)

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
Cohesion: 0.17
Nodes (15): _clip(), _dur(), _entrar(), _generar_y_esperar(), _nivel(), Variaciones de video: acceso por código, subida por pedazos, combinaciones y ZIP, _subir(), test_archivo_que_no_es_video_se_rechaza() (+7 more)

### Community 162 - "diag_auth.py"
Cohesion: 0.29
Nodes (13): _excel(), _proy(), Unidad NUEVA por Excel: descuento/bono con celda vacía quedan None ("sin dato"),, Excel JB mínimo con columnas Descuento y Bonopie en la hoja UNIDAD., Proyecto NUEVO por corrida: con un id fijo, una corrida anterior contra la misma, Un 0 que SÍ viene en el Excel es dato real de la fuente: se guarda 0., Regresión del camino de actualización: vacío sigue preservando lo cargado., _subir() (+5 more)

### Community 163 - "diag_detail.py"
Cohesion: 0.67
Nodes (3): main(), diag_detail.py — Caza el endpoint de DETALLE de proyecto en la API pública JB 7., _summ()

### Community 164 - "diag_mkt_stock.py"
Cohesion: 0.18
Nodes (10): ZadarmaEvento, _enviar(), pbx(), Webhook de Zadarma: firmas, barreras e idempotencia de las llamadas., test_ip_fuera_de_rango(), test_llamada_saliente_completa(), test_token_incorrecto(), test_transcripcion_antes_que_el_fin() (+2 more)

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
Cohesion: 0.07
Nodes (46): _age_hours(), _alertas_de_proyecto(), _antiguedad_color(), build_daily_report(), _calidad_score(), _catalogo_vs_stock(), _critico_key(), _disp() (+38 more)

### Community 169 - "patch_modelo_huerfanas.py"
Cohesion: 0.67
Nodes (3): main(), parse_db(), patch_modelo_huerfanas.py — Repara unidades con modelo="" en proyectos afectados

### Community 170 - "capacitaciones_hls.py"
Cohesion: 0.17
Nodes (14): enlace_grabacion(), firma_api(), firma_evento(), _hmac_b64_variantes(), llamar_api(), purgar_eventos(), Zadarma: verificación de notificaciones, armado de llamadas y firma de la API., Borra los eventos crudos más antiguos que `dias`. Devuelve cuántos borró. (+6 more)

### Community 171 - "review_all.py"
Cohesion: 0.67
Nodes (3): gp(), main(), review_all.py — Revisión final consolidada de todos los proyectos importados v2.

### Community 173 - "tickets.py"
Cohesion: 0.15
Nodes (24): categoria_foto(), completar_fisicos(), _entero(), ficha_desde_catalogo(), fotos_y_documentos(), main(), _modelo(), _numero() (+16 more)

### Community 175 - "2026_09_24_0000-010_reserva_bc.py"
Cohesion: 0.23
Nodes (13): canon_de(), _es_numero(), garantia_de(), GarantiaInvalida, publica(), Any, Arriendo Garantizado por la inmobiliaria — bc-api · 2026-11-03  Caso que lo orig, La garantía guardada del proyecto, o None si no tiene (o el dato está roto). (+5 more)

### Community 188 - "test_video_proyecto.py"
Cohesion: 0.11
Nodes (27): DescuentoPlan, DocumentoOut, ImagenOut, ImagenUpdate, _mas_de_dos_decimales(), _pct(), PlanesPagoIn, PlanPago (+19 more)

### Community 189 - "diag_chips_full.py"
Cohesion: 0.60
Nodes (4): _es_depto(), main(), _norm(), Backfill: deriva tipologia="{d}D{b}B" para unidades-depto sin tipología, usando

### Community 192 - "diag_mkt_types.py"
Cohesion: 0.67
Nodes (3): parse_seed(), Importa proyectos del seed-pinar.js (frontend stock-interno) a la DB Postgres., seed()

### Community 193 - "diag_modelo_superficies.py"
Cohesion: 0.15
Nodes (31): alertas_hoy(), _anexo_propio(), calidad(), detalle_llamada(), fijar_metas(), _filtrar(), gestion(), gestion_rango() (+23 more)

### Community 198 - "diag_vm_scroll.py"
Cohesion: 0.21
Nodes (12): _anexo(), aplicar_evento(), _entero(), _ext(), _fecha(), fila_estadistica_a_campos(), Primer valor con forma de anexo (3 dígitos, p. ej. '102')., Registra el evento crudo y actualiza la llamada. No hace commit. Los eventos que (+4 more)

### Community 200 - "migrar_snapshot_viejo"
Cohesion: 0.35
Nodes (10): alturas_para(), generar(), generar_async(), hls_de(), _mapa(), _raiz(), Capacitaciones: video con calidad automática, como YouTube (21-oct-2026).  Cada, Calidades que se generan: solo las que no superan el lado corto del original (nu (+2 more)

### Community 207 - "test_llamadas_consulta.py"
Cohesion: 0.22
Nodes (6): proyecto(), Video del edificio: subida en pedazos retomable, conversión a HLS y estado en ex, _subir(), test_subida_retomable_y_hls(), test_video_no_leible_da_error_claro(), _video()

### Community 209 - "diag_usuario"
Cohesion: 0.39
Nodes (8): _crear_proy(), _jb_excel(), Tests del flag permitir_sin_unidades en POST /proyectos/{id}/unidades/excel/uplo, Excel JB mínimo: UNIDAD (opcionalmente vacío) + ESTAC + BODEGA + INSTRUCCIONES., SEGURIDAD: un upload sin deptos + flag NO debe dar de baja deptos existentes., test_flag_no_da_de_baja_deptos_existentes(), test_unidad_vacia_con_flag_sincroniza_estac_bodega(), test_unidad_vacia_sin_flag_da_400()

### Community 241 - "diag_investigate.py"
Cohesion: 0.22
Nodes (8): `app/routes/proyectos.py`, `app/schemas/proyecto.py`, Cambios, Fix 1, Preocupaciones / decisiones a revisar, Pruebas, Task 1 — Reporte (bc-api, planes de pago), `tests/test_planes_pago.py` (nuevo, 14 tests)

### Community 249 - "BaseModel"
Cohesion: 0.31
Nodes (8): datos(), _iso(), _listar_referencia(), GET /proyectos (2026-10-18): la versión rápida (solo columnas del resumen + clav, Copia literal de la lógica anterior de `listar` (sin filtros)., Proyectos sintéticos con los casos raros del listado. Se borran al terminar., test_listado_con_filtros_identico(), test_listado_identico_a_la_version_anterior()

### Community 251 - "UploadFile"
Cohesion: 0.25
Nodes (8): _frases(), Normaliza `result` de SPEECH_RECOGNITION a [{"canal": n, "texto": "…"}]., Crea o completa la fila de la llamada sin pisar datos con vacíos., Pide la transcripción de llamadas grabadas y contestadas (20 s o más) que aún no, Job del programador: últimas 48 h de llamadas + transcripciones faltantes., sincronizar_job(), traer_transcripciones_faltantes(), _upsert()

### Community 262 - "aplicar_lectura"
Cohesion: 0.43
Nodes (6): aplicar_lectura(), estado_efectivo(), datetime, «PlanOk manda»: la marca de reserva de la intranet es PROVISORIA — bc-api · 2026, Estado de la marca; para una marca anterior a este cambio, por su edad., Actualiza el estado de la marca de `u` según la lectura de PlanOk.      `ofrecid

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
Cohesion: 0.24
Nodes (10): HTTPAuthorizationCredentials, decode_token(), Raises JWTError on invalid/expired., current_user(), FastAPI dependencies for auth: extract user from Authorization header., Valida el token de servicio del Cloudflare Worker (catálogo público).      Compa, Acceso a Stock propio: super admin O usuario con permiso de stock.      El permi, service_token() (+2 more)

### Community 287 - "._log_timeline_evento"
Cohesion: 0.47
Nodes (5): _llamar(), main(), _oculto(), Registra en Zadarma la URL del webhook de bc-api y activa la transcripción.  Uso, Texto de la respuesta sin el token del webhook (la URL registrada lo lleva en ?k

### Community 288 - "rank_pendientes.py"
Cohesion: 0.50
Nodes (4): find_stock_fields(), main(), diag_stock_total.py — Para los 5 proyectos sin unidades, consulta la API JB y du, Recorre recursivamente el JSON y devuelve campos numéricos cuyo nombre     sugie

### Community 291 - "2026_10_21_0000-013_llamadas.py"
Cohesion: 0.67
Nodes (3): main(), Valida (solo lectura) lo que muestra el panel de Llamadas contra Zadarma y contr, traer()

### Community 292 - "inspect_marketplace_workview.py"
Cohesion: 0.67
Nodes (3): main(), inspect_marketplace_workview.py — Reconocimiento de una URL /marketplace/workvie, run()

## Knowledge Gaps
- **142 isolated node(s):** `Orden`, `Task 1: bc-api — esquema, PATCH, PUT/POST protegidos`, ``app/schemas/proyecto.py``, ``app/routes/proyectos.py``, ``tests/test_planes_pago.py` (nuevo, 14 tests)` (+137 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **195 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JBImporter` connect `Calculo de metricas del informe diario` to `import_marketplace_workview.py`, `diag_csv_batch.py`, `Descarga y gestion de assets JB`, `2026_07_23_0000-008_ultima_revision_at.py`, `Ruta de importacion batch (API)`, `Reporte de actividad del operador`, `origen_stock.py`, `Motor de alertas de proyecto (criticos)`, `_SMTP`, `rank_pendientes.py`, `Borrado de proyecto antes de reimportar`, `_build_idx_map`, `diag_detail.py`, `inspect_marketplace_workview.py`, `diag_pipeline.py`, `diag_bod_raw.py`, `diag_detail_page.py`, `diag_stock_extra.py`, `diag_paginador_unidades.py`, `diag_rosas.py`, `diag_vm_scroll2.py`, `diag_workview.py`, `documentos.py`, `Diagnostico de carga de detalle (click)`, `diag_euro.py`, `diag_investigate.py`, `test_video_proyecto.py`, `firma_api`, `diag_vm_scroll2.py`, `diag_vm_stock.py`, `diag_vm_typesel.py`, `patch_publicar_catalogo.py`, `Migracion: tabla inmobiliarias`, `Diagnostico depto sin planta (Vivaceta)`, `Inicializador del paquete app`, `estado_stock`, `Auditoría profunda — Modelos y Stock`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `Proyecto` connect `Rutas admin: informes e inmobiliarias` to `audit_aj_urbana_freshness.py`, `Rutas de unidades (deptos)`, `Gestion de inmobiliarias (catalogo)`, `Infraestructura DB y autenticacion`, `Diagnosticos API JetBrokers`, `Vista previa del informe diario`, `Rutas de documentos del proyecto`, `Importador desde bigcapital.cl Worker`, `Rutas de imagenes del proyecto`, `Verificacion visual con IA (AI Vision)`, `Importacion desde export manual JB`, `Motor del informe diario de stock`, `zadarma.py`, `_catalogo_vs_stock`, `Dry-run de importacion (solo lectura)`, `diag_auth.py`, `inspect_marketplace_workview.py`, `diag_chips_full.py`, `diag_mkt_types.py`, `test_estado_stock.py`, `Ranking de pendientes Ingevec`, `Diagnostico de superficies por modelo`, `test_llamadas_consulta.py`, `diag_usuario`, `video_proyecto.py`, `Migracion: timestamp de stock`, `Migracion: borrado logico de proyecto`, `Diagnostico completo Vivaceta`, `BaseModel`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Why does `send_daily_report()` connect `env.py` to `inspect_marketplace_workview.py`, `Inicializador de tests`, `Migracion: timestamp de stock`, `Vista previa del informe diario`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 62 inferred relationships involving `Proyecto` (e.g. with `normalize_inmobiliarias()` and `batch_import()`) actually correct?**
  _`Proyecto` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `Usuario` (e.g. with `test_sin_permiso_de_stock_da_403()` and `_token_para()`) actually correct?**
  _`Usuario` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `Llamada` (e.g. with `detalle_llamada()` and `grabacion_llamada()`) actually correct?**
  _`Llamada` has 33 INFERRED edges - model-reasoned connections that need verification._
- **What connects `SQLAlchemy engine + session factory.`, `FastAPI dependency: yields a SQLAlchemy session per request.`, `FastAPI dependencies for auth: extract user from Authorization header.` to the rest of the system?**
  _759 weakly-connected nodes found - possible documentation gaps or missing edges._