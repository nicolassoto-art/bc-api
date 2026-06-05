# API pública JetBrokers 7.43.1 — mapa completo (descubierto 2026-06-05)

## Contexto del cambio
JB migró en la versión **7.43.1** a un **nuevo esquema de IDs de proyecto** y un nuevo
namespace de API (`/marketplace/*`). Los slugs viejos (ej. `igfwzvh2`, `iaiq9ith`)
ahora devuelven **404 / "Proyecto no encontrado"**. Por eso el batch de re-import
"vació" proyectos: respondían 404, no por bug de scroll.

**Los datos NO se perdieron** — están bajo IDs nuevos, accesibles por la API pública.

## Autenticación
- Login Playwright → token en `localStorage['broker-storage_broker-user-token']` (8 chars).
- Header `Authorization: Bearer <token>` + `jet-brokers-version: 7.43.1` + `device: w`.
- Base: `https://app.jetbrokers.io/api`.

## Pipeline de endpoints (todos 200, sin scraping)

### 1. Lista de proyectos de BigCapital (org `uv13koru`)
```
POST /project/organization/uv13koru/list/{ts_ms}
body: {"locality":null,"stage":null,"year":null,"available":null,"tipology":null,
       "developer":null,"priceFrom":null,"priceTo":null,"jetStock":null,
       "modalityType":null,"projectTags":[],"element":0,"elements":9999}
→ 201 {"projects":[{id,name,locality,gpsLat,gpsLon,pie,reservaCLP,cachedTipologies,
       cachedUnitTypes,stockLastUpdateAt,tags,cover,organization:{id,name},...}]}
```
Devuelve ~237 proyectos (catálogo vendible). `id` = ID NUEVO.

### 2. Detalle de proyecto (la ficha completa — 75 campos)
```
GET /marketplace/{id}/workview
→ 200 { name, buildingCompany, shellCompanyName, shellCompanyTaxId, shellCompanyFulAddress,
        address, locality, dateOfDelivery, yearOfDelivery, stage, floors,
        buildingPermit, buildingPermitNumber, description, termDetails, available,
        promoBroker, promoCustomer, stockType, gpsLat, gpsLon, allowTransfer,
        preApprovalRequired, perks[], pie, pieTipo, reservaCLP, reservaTipo,
        discountType, bonoPieTipo, reservaDestino, cuotasPreEntrega, cuotasPostEntrega,
        reserveName, reserveTaxId, reserveAccountType, reserveAccountNumber, reserveBank,
        perksNearby[], perksCommonAreas[], apartmentsTotal, apartmentsByFloor,
        parkingsTotal, storesTotal, elevatorsTotal, cuotonFinal, cuotonInicial,
        parkingRent, storeRent, onlinePaymentLink, commissionDetails, developerName,
        developerWeb, developerAddress, developerTaxId, valorCuotaCLP, allowCustomerBlock,
        saleRoomConditions, saleArguments, reserveRefund, expensesCommonCLP,
        cuotasLastPayDate, videoPresentationUrl, modalityType, tags[], payMethodPreEntrega,
        payMethodCuotas, payMethodPostEntrega, organization:{id,name,web,logo,legalAddress},
        cover, jetstock, apartmentsAvailable }
```
**Incluye TODO lo "privado"**: cuenta reserva (banco), SPA (shellCompany), comercial, notas.

### 3. Modelos + plantas
```
GET /marketplace/stock-selectors/{id}
→ 200 { facings:[...], tipologies:["3D2B",...],
        models:[{ id, name, rooms, bathrooms,
                  requiredStorage, requiredParking, requiredPack,
                  blueprint:{ id, mime, size, type:"blueprint" } }] }
```
**Planta del modelo = `blueprint.id`** → imagen vía `/file/download/{blueprint.id}/{w}/{h}`.

### 4. Unidades (stock individual)
```
POST /marketplace/units-search/{ts_ms}
→ 201 { apartments:[{ id, available, number, price, surfaceTotal, surfaceInterior,
        surfaceTerrace, surfaceLogia, surfaceGarden, facing, discountRate, bonoPie,
        idExternal, modality, finalPrice, type,
        apartmentModel:{id,name,rooms,bathrooms,requiredStorage,requiredParking,
                        requiredPack,blueprint:{id,mime}} }] }
```
(body del POST por confirmar — probablemente projectJsId + filtros + paginación)

### 5. Archivos (fotos + documentos)
```
GET /marketplace/files/{id}/{page}
→ 200 { files:[{ id, createdAt, mime, size, type, project, createdBy:{id,name} }], count }
```
Tipos vistos: `projectBrochure` (PDF), `projectPerk`, `projectPerkCommonArea`,
`projectPerkNearby` (imágenes de amenidades/entorno). Foto principal = `cover` del workview.

### 6. Descarga de imágenes
```
GET /file/download/{fileId}/{w}/{h}            (autenticado)
GET /file-unauthenticated/download/{fileId}/{w}/{h}   (público)
```

## Mapeo JB → bc-api (campos)

### Proyecto (workview → top-level + extra)
| JB workview | bc-api |
|---|---|
| name | nombre |
| address | direccion |
| locality | comuna |
| dateOfDelivery / yearOfDelivery | fecha_entrega / ano_entrega |
| stage | fase |
| available (yes/paused/no) | disponible |
| modalityType | modalidad |
| gpsLat / gpsLon | gps_lat / gps_lon |
| organization.name | inmobiliaria |
| organization.{web,logo,legalAddress} | extra.inmobiliaria.{web,logo_url,direccion} |
| cover | foto_principal_url (download file) |
| floors | extra.fisicos.pisos |
| apartmentsTotal / apartmentsByFloor | extra.fisicos.unidades_totales / unidades_por_piso |
| parkingsTotal / storesTotal / elevatorsTotal | extra.fisicos.estacionamientos_totales / bodegas_totales / ascensores |
| buildingCompany | extra.fisicos.constructora |
| buildingPermit / buildingPermitNumber | extra.fisicos.permiso_construccion / numero_permiso |
| allowTransfer | extra.fisicos.acepta_cesion |
| description | extra.descripcion |
| termDetails / saleRoomConditions | extra.condiciones_especiales |
| promoBroker / promoCustomer | extra.promocion_broker / promocion_cliente |
| preApprovalRequired | extra.solicita_preaprobacion |
| stockType | extra.stock_type |
| tags | extra.etiquetas |
| perks / perksCommonAreas / perksNearby | extra.equipamiento / areas_comunes / entorno |
| pie / pieTipo | extra.comercial.pie_pct / tipo_pie |
| cuotonInicial / cuotonFinal | extra.comercial.cuoton_inicial_pct / cuoton_final_pct |
| discountType / bonoPieTipo | extra.comercial.tipo_descuento / tipo_bono_pie |
| reservaCLP / reservaTipo / reservaDestino | extra.comercial.valor_reserva_clp / tipo_reserva / destino_reserva |
| cuotasPreEntrega / cuotasPostEntrega | extra.formas_pago_pie.cuotas_pre_entrega / cuotas_post_entrega |
| payMethodPreEntrega / payMethodCuotas / payMethodPostEntrega | extra.formas_pago_pie.pago_pre_entrega / pago_cuoton_inicial / pago_post_entrega |
| valorCuotaCLP | extra.formas_pago_pie.valor_cuota_clp |
| reserveName / reserveTaxId | extra.cuenta_reserva.titular_nombre / titular_rut |
| reserveAccountType / reserveAccountNumber / reserveBank | extra.cuenta_reserva.tipo_cuenta / numero_cuenta / banco |
| onlinePaymentLink | extra.cuenta_reserva.link_pago |
| shellCompanyName / shellCompanyTaxId / shellCompanyFulAddress | extra.spa_proyecto.nombre / rut / direccion |
| commissionDetails | extra.comercial.comision_detalle |
| parkingRent / storeRent | extra.arriendos.estacionamiento_clp / bodega_clp |
| expensesCommonCLP | extra.fisicos.gastos_comunes_clp |
| videoPresentationUrl | extra.video_url |

### Modelo (stock-selectors.models[] → extra.modelos[])
| JB | bc-api |
|---|---|
| name | nombre |
| rooms / bathrooms | dormitorios / banos |
| requiredStorage / requiredParking / requiredPack | cotiza_bodega / cotiza_estac / cotiza_pack |
| blueprint.id | planta (download → planta_url) |

### Unidad (units-search.apartments[] → unidades[])
| JB | bc-api |
|---|---|
| number | numero |
| apartmentModel.name | modelo |
| type | tipo |
| facing | orientacion |
| surfaceTotal/Interior/Terrace/Logia/Garden | sup_total/sup_interior/sup_terraza/sup_logia/sup_jardin |
| price / finalPrice | precio_lista_uf / precio_final_uf |
| discountRate / bonoPie | descuento_pct / bono_pie_pct |
| idExternal | id_externo |
| available | disponible |

## Implicancias
- **El scraper DOM se vuelve casi innecesario**: la API entrega proyecto+modelos+plantas+
  unidades+fotos+documentos, incluido lo "privado" (cuenta reserva, SPA). Eventualmente
  solo `notas_html` (texto rico) podría requerir scraping — a confirmar.
- **Re-vincular viejo→nuevo ID**: match por nombre+comuna entre los 84 de bc-api y los 237
  de la lista org. Operación única de migración.
- **Recuperación**: los 20 proyectos vaciados se recuperan re-importando con el ID nuevo.
