/* JetBroker · Export snippet v2
   ================================
   Pegá este código en la consola de Chrome (F12 → Console)
   estando LOGUEADO en https://app.jetbrokers.io/catalog

   Filtra: Disponible: Sí + JetStock: No  →  los 83 proyectos del catálogo
   que no están en tu stock interno todavía.

   Al terminar descarga `jb_export_YYYY-MM-DD.json`.
   Luego subí ese archivo en:
     https://herramientas.bigcapital.cl/src/importador/
*/
(async () => {
  const BASE = 'https://app.jetbrokers.io/api';

  // Token de la sesión activa
  const token = localStorage.getItem('broker-storage_broker-user-token');
  if (!token) {
    console.error('❌ No hay token. ¿Estás logueado en https://app.jetbrokers.io ?');
    return;
  }

  const H = {
    'Authorization': `Bearer ${token}`,
    'jet-brokers-version': '7.42.0',
    'device': 'w',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  const get  = url  => fetch(url, { headers: H }).then(r => r.ok ? r.json() : Promise.reject(`${r.status} ${url}`));
  const post = (url, body) => fetch(url, { method:'POST', headers: H, body: JSON.stringify(body) })
                               .then(r => r.ok ? r.json() : Promise.reject(`${r.status} ${url}`));
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // ── Paso 1: todas las unidades disponibles con JetStock: No ──────────────
  console.log('🔍 Paso 1/3 — Obteniendo unidades (Disponible:Sí + JetStock:No)...');
  const PAGE = 30;
  const SEARCH_BODY = {
    modality:'new', stage:null, project:null, developer:null,
    comuna:null, tipology:null, facing:null, discountRate:null,
    bonoPie:null, finalPriceFrom:null, finalPriceTo:null,
    sort:null, unitType:null, jetstock:false, element:0,
  };

  const first = await post(`${BASE}/apartment/catalog-search`, SEARCH_BODY);
  const total = first.count || 0;
  let allUnits = [...(first.elements || [])];
  console.log(`   Total unidades: ${total}`);

  for (let offset = PAGE; offset < total; offset += PAGE) {
    await sleep(600 + Math.random() * 600);
    const page = await post(`${BASE}/apartment/catalog-search`, { ...SEARCH_BODY, element: offset });
    allUnits.push(...(page.elements || []));
    if (offset % 150 < PAGE) console.log(`   Progreso: ${Math.min(offset + PAGE, total)}/${total}`);
  }
  console.log(`   ✓ ${allUnits.length} unidades descargadas`);

  // ── Agrupar unidades por proyecto ────────────────────────────────────────
  const projMap = {};
  for (const u of allUnits) {
    const proj = u.project;
    if (!proj?.id) continue;
    if (!projMap[proj.id]) projMap[proj.id] = { _basic: proj, _units: [] };
    projMap[proj.id]._units.push(u);
  }
  const pids = Object.keys(projMap);
  console.log(`\n📦 Paso 2/3 — Detalle de ${pids.length} proyectos únicos...`);

  // ── Paso 2: detalle completo de cada proyecto ────────────────────────────
  const enriched = [];
  for (let i = 0; i < pids.length; i++) {
    const pid = pids[i];
    await sleep(500 + Math.random() * 800);
    try {
      const detail = await get(`${BASE}/project/${pid}`);
      enriched.push({
        ...detail,
        units: projMap[pid]._units,
        _meta: { exportedAt: new Date().toISOString(), filter: 'disponible:si+jetstock:no' },
      });
      const org = (detail.organization?.name || projMap[pid]._basic.organization?.name || '—');
      console.log(`   [${i+1}/${pids.length}] ${detail.name} · ${org} · ${projMap[pid]._units.length} unidades`);
    } catch(e) {
      console.warn(`   [${i+1}/${pids.length}] ${pid}: ${e}`);
      enriched.push({ ...projMap[pid]._basic, units: projMap[pid]._units, _error: String(e) });
    }
  }

  // ── Paso 3: descargar JSON ───────────────────────────────────────────────
  console.log('\n💾 Paso 3/3 — Generando archivo...');
  const blob = new Blob([JSON.stringify(enriched, null, 2)], { type:'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `jb_export_${new Date().toISOString().slice(0,10)}.json`;
  document.body.appendChild(a); a.click(); a.remove();

  const byOrg = {};
  enriched.forEach(p => { const n = p.organization?.name || '—'; byOrg[n] = (byOrg[n]||0)+1; });
  console.log(`\n✅ ${enriched.length} proyectos exportados. Por inmobiliaria:`);
  Object.entries(byOrg).sort((a,b)=>b[1]-a[1]).forEach(([n,c]) =>
    console.log(`   ${String(c).padStart(4)} · ${n}`)
  );
  console.log('\n📥 Ahora subí el archivo en: https://herramientas.bigcapital.cl/src/importador/');
})();
