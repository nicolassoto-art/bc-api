# Auditoría profunda — Modelos y Stock

Generado a partir de 84 proyectos.

Por proyecto se reporta:
- **M**: total modelos en `extra.modelos`
- **U**: total unidades
- **M.con-planta**: modelos con `planta_url` no vacío
- **U.con-precio**: unidades con `precio_lista_uf > 0`
- **U.con-sup**: unidades con `sup_total > 0`
- **U.huérfanas**: unidades cuyo `modelo` no aparece en modelos
- **U.dups**: pares duplicados de `numero`

## 📈 Estadísticas globales

| Métrica | Valor |
|---|---|
| Proyectos auditados | 84 |
| Modelos totales | 933 |
| Modelos con planta_url | 699 (74%) |
| Modelos sin planta_url | 234 (25%) |
| Unidades totales | 4,879 |
| Unidades con precio | 4,879 (100%) |
| Unidades sin precio | 0 |
| Unidades con sup_total | 4,879 (100%) |
| Unidades sin sup_total | 0 |
| Unidades huérfanas (modelo no existe) | 67 |
| Duplicados de numero | 0 |
| Proyectos sin modelos | 7 |
| Proyectos sin unidades | 13 |
| Proyectos con huérfanas | 5 |
| Proyectos con duplicados | 0 |
| Proyectos con M sin planta | 6 |

## 📋 Detalle por proyecto

| Inmo | Nombre | M | M.planta | U | U.precio | U.sup | U.huérf | U.dup |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| AJ URBANA | Edificio DownTown San Martín | 21 | 19/21 | 141 | 141/141 | 141/141 | ✓ | ✓ |
| AJ URBANA | Edificio Teatinos 750 | 16 | 12/16 | 42 | 42/42 | 42/42 | ✓ | ✓ |
| AJ URBANA | Edificio Vista Amunategui | 18 | 15/18 | 84 | 84/84 | 84/84 | ✓ | ✓ |
| AJ URBANA | Edificio Vista Morandé | 19 | 16/19 | 94 | 94/94 | 94/94 | ✓ | ✓ |
| CISS | Fuentes de Lomas III | 1 | 1/1 | 14 | 14/14 | 14/14 | ✓ | ✓ |
| CISS | Fuentes de Lomas IV | 3 | 1/3 | 15 | 15/15 | 15/15 | ✓ | ✓ |
| CISS | Fuentes de Miguel Collao | 1 | 1/1 | 39 | 39/39 | 39/39 | ✓ | ✓ |
| Ecasa | Aires La Florida 2 | 9 | 7/9 | 128 | 128/128 | 128/128 | ✓ | ✓ |
| Ecasa | Bezanilla | 7 | 2/7 | 15 | 15/15 | 15/15 | ✓ | ✓ |
| Ecasa | Bosquemar | 5 | 4/5 | 25 | 25/25 | 25/25 | ✓ | ✓ |
| Ecasa | Cumbres de Peñuelas | 4 | 3/4 | 16 | 16/16 | 16/16 | ✓ | ✓ |
| Ecasa | Edificio HA | 3 | 2/3 | 4 | 4/4 | 4/4 | ✓ | ✓ |
| Ecasa | Terratoltén | 4 | 0/4 | 16 | 16/16 | 16/16 | ✓ | ✓ |
| Ecasa | Terratoltén 2 | 5 | 0/5 | 70 | 70/70 | 70/70 | ✓ | ✓ |
| Ecasa | Urban La Florida | 4 | 3/4 | 75 | 75/75 | 75/75 | ✓ | ✓ |
| EuroInmobiliaria | Edificio Vitro | 5 | 4/5 | 406 | 406/406 | 406/406 | ✓ | ✓ |
| EuroInmobiliaria | Guillermo Mann 1401 | 3 | 3/3 | 27 | 27/27 | 27/27 | ✓ | ✓ |
| EuroInmobiliaria | Independencia 4745 | 8 | 4/8 | 128 | 128/128 | 128/128 | ✓ | ✓ |
| EuroInmobiliaria | Jose Pedro Alessandri 1498 | 5 | 5/5 | 139 | 139/139 | 139/139 | ✓ | ✓ |
| EuroInmobiliaria | Rosas 1444 | 5 | 0/5 | 120 | 120/120 | 120/120 | ✓ | ✓ |
| EuroInmobiliaria | Vicuña Mackenna 1432 | 5 | 5/5 | 70 | 70/70 | 70/70 | ✓ | ✓ |
| INMOBILIARIA LARRAIN | EDIFICIO CONEXIÓN INDEPENDENCIA | 17 | 16/17 | 0 | — | — | ✓ | ✓ |
| INMOBILIARIA LARRAIN | EDIFICIO MISSOURI 3885 | 24 | 8/24 | 1 | 1/1 | 1/1 | ✓ | ✓ |
| INMOBILIARIA LARRAIN | EDIFICIO ÑUÑOA ZAÑARTU | 22 | 12/22 | 8 | 8/8 | 8/8 | ✓ | ✓ |
| INMOBILIARIA LARRAIN | ZAPADORES 1821 | 14 | 11/14 | 106 | 106/106 | 106/106 | ✓ | ✓ |
| Ileon | Edificio B.Come | 28 | 24/28 | 77 | 77/77 | 77/77 | ✓ | ✓ |
| Ingevec | Abdón Cifuentes | 30 | 25/30 | 51 | 51/51 | 51/51 | ⚠ 50 | ✓ |
| Ingevec | Brasil | 4 | 4/4 | 142 | 142/142 | 142/142 | ✓ | ✓ |
| Ingevec | Centenario I | 30 | 28/30 | 28 | 28/28 | 28/28 | ⚠ 1 | ✓ |
| Ingevec | Diagonal Paraguay 240 | 15 | 11/15 | 4 | 4/4 | 4/4 | ✓ | ✓ |
| Ingevec | Don Ignacio | 30 | 23/30 | 96 | 96/96 | 96/96 | ✓ | ✓ |
| Ingevec | Edificio Serrano Capital | 3 | 3/3 | 183 | 183/183 | 183/183 | ✓ | ✓ |
| Ingevec | Froilan Roa | 30 | 17/30 | 0 | — | — | ✓ | ✓ |
| Ingevec | Los Alerces | 25 | 23/25 | 0 | — | — | ✓ | ✓ |
| Ingevec | Matta | 2 | 1/2 | 31 | 31/31 | 31/31 | ✓ | ✓ |
| Ingevec | Santa Rosa 250 | 10 | 9/10 | 0 | — | — | ✓ | ✓ |
| Ingevec | Terrazzo | 6 | 0/6 | 211 | 211/211 | 211/211 | ✓ | ✓ |
| Ingevec | Tocornal | 30 | 24/30 | 9 | 9/9 | 9/9 | ⚠ 3 | ✓ |
| Ingevec | Vicuña Mackenna 1796 | 18 | 12/18 | 0 | — | — | ✓ | ✓ |
| Ingevec | Vicuña Mackenna 7589 Etapa I | 16 | 12/16 | 40 | 40/40 | 40/40 | ✓ | ✓ |
| Ingevec | Vicuña Mackenna 7589 Etapa II | 16 | 11/16 | 46 | 46/46 | 46/46 | ✓ | ✓ |
| Ingevec | Vivaceta 864 | 25 | 13/25 | 62 | 62/62 | 62/62 | ✓ | ✓ |
| Inmobiliaria Las Pal | Altos de Collao | 24 | 17/24 | 15 | 15/15 | 15/15 | ✓ | ✓ |
| Inmobiliaria Origen | Plaza Victoria | 18 | 16/18 | 6 | 6/6 | 6/6 | ✓ | ✓ |
| Iroyal | Condominio Mallorca | 13 | 7/13 | 46 | 46/46 | 46/46 | ✓ | ✓ |
| Iroyal | Edificio Peumayen | 6 | 5/6 | 83 | 83/83 | 83/83 | ✓ | ✓ |
| Iroyal | Mirador Chacabuco | 17 | 17/17 | 148 | 148/148 | 148/148 | ✓ | ✓ |
| Iroyal | Mirador oceánico | 10 | 7/10 | 57 | 57/57 | 57/57 | ✓ | ✓ |
| Iroyal | Parque Huertos | 13 | 13/13 | 206 | 206/206 | 206/206 | ✓ | ✓ |
| Itrio | Bulnes 138 | 29 | 27/29 | 4 | 4/4 | 4/4 | ✓ | ✓ |
| Itrio | EDIFICIO SANTA ELENA 236 | 6 | 6/6 | 11 | 11/11 | 11/11 | ✓ | ✓ |
| MNK | Condominio La Rioja | 12 | 8/12 | 36 | 36/36 | 36/36 | ✓ | ✓ |
| MNK | Cordillera Oriente Etapa 1 | 14 | 11/14 | 86 | 86/86 | 86/86 | ✓ | ✓ |
| MNK | ETAPA 2 PORTAL DEL PINAR | 7 | 7/7 | 27 | 27/27 | 27/27 | ✓ | ✓ |
| MNK | PORTAL DEL PINAR | 7 | 7/7 | 4 | 4/4 | 4/4 | ✓ | ✓ |
| Maestra | Alto Buzeta | 6 | 5/6 | 114 | 114/114 | 114/114 | ✓ | ✓ |
| Maestra | Apóstol Santiago | 4 | 3/4 | 12 | 12/12 | 12/12 | ✓ | ✓ |
| Maestra | Cáceres | 3 | 0/3 | 70 | 70/70 | 70/70 | ✓ | ✓ |
| Maestra | General Mackenna | 5 | 5/5 | 177 | 177/177 | 177/177 | ✓ | ✓ |
| Maestra | Jardines de Alvarado | 4 | 4/4 | 19 | 19/19 | 19/19 | ✓ | ✓ |
| Maestra | Pintor Cicarelli I | 4 | 4/4 | 233 | 233/233 | 233/233 | ✓ | ✓ |
| Maestra | Pintor Cicarelli II | 4 | 4/4 | 48 | 48/48 | 48/48 | ✓ | ✓ |
| Maestra | Plaza Cervantes torre B | 3 | 3/3 | 8 | 8/8 | 8/8 | ✓ | ✓ |
| Maestra | Serrano Torre A | 10 | 5/10 | 221 | 221/221 | 221/221 | ✓ | ✓ |
| Maestra | Trinidad III | 3 | 0/3 | 12 | 12/12 | 12/12 | ✓ | ✓ |
| Maestra | Vista Costanera | 3 | 3/3 | 24 | 24/24 | 24/24 | ✓ | ✓ |
| Maestra | Vista Reloncaví | 3 | 3/3 | 110 | 110/110 | 110/110 | ✓ | ✓ |
| Prohabit | MiraOlas Peñuelas | 9 | 9/9 | 24 | 24/24 | 24/24 | ✓ | ✓ |
| Prohabit | MiraOlas Peñuelas 2º etapa | 6 | 6/6 | 97 | 97/97 | 97/97 | ✓ | ✓ |
| Prohabit | Quinta Park | 18 | 18/18 | 122 | 122/122 | 122/122 | ✓ | ✓ |
| Sin asignar | Almanova | 0 | — | 0 | — | — | ✓ | ✓ |
| Sin asignar | Edificio Borja Plaza | 0 | — | 0 | — | — | ✓ | ✓ |
| Sin asignar | Ferroparque | 0 | — | 0 | — | — | ✓ | ✓ |
| Sin asignar | Fuentes de Lomas II | 0 | — | 0 | — | — | ✓ | ✓ |
| Sin asignar | Pionera Parque Cerrillos | 0 | — | 0 | — | — | ✓ | ✓ |
| Sin asignar | Vista San Martin | 0 | — | 0 | — | — | ✓ | ✓ |
| Stitchkin | Eleuterio Ramírez | 30 | 29/30 | 19 | 19/19 | 19/19 | ⚠ 7 | ✓ |
| Stitchkin | Las Condes 7039 | 30 | 28/30 | 2 | 2/2 | 2/2 | ✓ | ✓ |
| Stitchkin | Novus Torre E | 30 | 5/30 | 9 | 9/9 | 9/9 | ⚠ 6 | ✓ |
| Stitchkin | Novus Torre G | 0 | — | 0 | — | — | ✓ | ✓ |
| Stitchkin | Rodrigo Araya 1410 | 13 | 5/13 | 2 | 2/2 | 2/2 | ✓ | ✓ |
| Stitchkin | Vicuña Mackenna 1194 | 13 | 9/13 | 0 | — | — | ✓ | ✓ |
| Vellatrix | Bandera 1060 | 6 | 6/6 | 32 | 32/32 | 32/32 | ✓ | ✓ |
| Vellatrix | Vivo Rengo | 4 | 3/4 | 32 | 32/32 | 32/32 | ✓ | ✓ |

## ⚠ Proyectos sin unidades (13)

- `48t1IInf` **EDIFICIO CONEXIÓN INDEPENDENCIA** (INMOBILIARIA LARRAIN PRIETO) — 17 modelos pero 0 unidades
- `jfkJBrPQ` **Froilan Roa** (Ingevec) — 30 modelos pero 0 unidades
- `WWMCny3E` **Los Alerces** (Ingevec) — 25 modelos pero 0 unidades
- `T8UuEf2r` **Santa Rosa 250** (Ingevec) — 10 modelos pero 0 unidades
- `1kvflc3m` **Vicuña Mackenna 1796** (Ingevec) — 18 modelos pero 0 unidades
- `q8RwqXao` **Almanova** (Sin asignar) — 0 modelos pero 0 unidades
- `zOHnfOQJ` **Edificio Borja Plaza** (Sin asignar) — 0 modelos pero 0 unidades
- `C8R7VcvH` **Ferroparque** (Sin asignar) — 0 modelos pero 0 unidades
- `dX4Rddfn` **Fuentes de Lomas II** (Sin asignar) — 0 modelos pero 0 unidades
- `m9zXfNHe` **Pionera Parque Cerrillos** (Sin asignar) — 0 modelos pero 0 unidades
- `osnL3M1C` **Vista San Martin** (Sin asignar) — 0 modelos pero 0 unidades
- `4Kny8VBw` **Novus Torre G** (Stitchkin) — 0 modelos pero 0 unidades
- `sFfaXZIQ` **Vicuña Mackenna 1194** (Stitchkin) — 13 modelos pero 0 unidades

## ⚠ Proyectos sin modelos (7)

- `q8RwqXao` **Almanova** (Sin asignar)
- `zOHnfOQJ` **Edificio Borja Plaza** (Sin asignar)
- `C8R7VcvH` **Ferroparque** (Sin asignar)
- `dX4Rddfn` **Fuentes de Lomas II** (Sin asignar)
- `m9zXfNHe` **Pionera Parque Cerrillos** (Sin asignar)
- `osnL3M1C` **Vista San Martin** (Sin asignar)
- `4Kny8VBw` **Novus Torre G** (Stitchkin)

## ⚠ Proyectos con unidades huérfanas (5)
(unidad tiene `modelo` que no existe en `extra.modelos[].nombre`)

- `G3jWrRoE` **Abdón Cifuentes** — 50/51 huérfanas
- `86YW1rPt` **Centenario I** — 1/28 huérfanas
- `9MubHeQ8` **Tocornal** — 3/9 huérfanas
- `C0xMpK4K` **Eleuterio Ramírez** — 7/19 huérfanas
- `KvRtrtXK` **Novus Torre E** — 6/9 huérfanas

## ⚠ Proyectos con modelos pero NINGUNO con planta_url (6)

- `kUYM4Rl8` **Terratoltén** — 4 modelos sin planta
- `wHL2AUKl` **Terratoltén 2** — 5 modelos sin planta
- `b7Aniv5k` **Rosas 1444** — 5 modelos sin planta
- `72GkWnlW` **Terrazzo** — 6 modelos sin planta
- `UAq8pgxr` **Cáceres** — 3 modelos sin planta
- `5d7qpMgc` **Trinidad III** — 3 modelos sin planta
