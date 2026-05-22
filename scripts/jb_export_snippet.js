/* JetBroker · Export snippet (uso humano-asistido)
   ===================================================
   Pegá este código en la consola de Chrome (F12 → Console)
   estando LOGUEADO en https://app.jetbrokers.io.

   Llama los mismos endpoints que la UI de JetBroker usa cuando
   navegás por tus proyectos (no es scraping, es tu propia sesión).
   Te descarga un archivo `jb_export.json` con todos tus proyectos
   visibles + sus unidades.

   Después corrés:
     python scripts/import_from_jetbroker.py \
       --input ~/Downloads/jb_export.json \
       --org "Larraín Prieto" \
       --bcapi-url https://bc-api.178-105-91-29.nip.io \
       --bcapi-email nicolas.soto@bigcapital.cl \
       --bcapi-pass-file ~/.bcapi-admin-pass \
       --dry-run
*/
(async () => {
  const API = 'https://api.jetbrokers.io';

  // Helper: fetch con credenciales (usa tu cookie de sesión actual)
  const get = (url) => fetch(url, { credentials: 'include' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${url}`)));

  console.log('1) Listando proyectos visibles...');
  // Probar endpoints hasta encontrar el que devuelve la lista
  let projects = null;
  for (const path of [
    '/api/projects', '/api/v1/projects', '/api/me/projects',
    '/api/broker/projects', '/api/catalog/projects',
  ]) {
    try {
      const data = await get(API + path);
      projects = Array.isArray(data) ? data
        : (data.data || data.projects || data.items || data.results);
      if (Array.isArray(projects)) {
        console.log(`   ✓ ${path} → ${projects.length} proyectos`);
        break;
      }
    } catch(e) { console.log(`   · ${path} → ${e.message}`); }
  }

  if (!projects) {
    console.error('No pude listar proyectos. Tu sesión puede estar expirada o JB cambió endpoints.');
    return;
  }

  console.log(`\n2) Tomando detalle + unidades de ${projects.length} proyectos...`);
  console.log('   (esto puede tomar varios minutos · podés pausar el script cerrando la tab)');

  const enriched = [];
  for (let i = 0; i < projects.length; i++) {
    const p = projects[i];
    const pid = p.id;
    try {
      // Detalle (puede que ya venga en la lista; lo refrescamos)
      const detail = await get(`${API}/api/project/${pid}`);
      // Units
      const unitsRaw = await get(`${API}/api/project/${pid}/units`).catch(() => []);
      const units = Array.isArray(unitsRaw) ? unitsRaw : (unitsRaw.data || []);
      enriched.push({ ...detail, units });
      console.log(`   [${i+1}/${projects.length}] ${detail.name} · ${units.length} unidades`);
    } catch(e) {
      console.warn(`   [${i+1}/${projects.length}] ${p.name || pid}: ${e.message}`);
      enriched.push({ ...p, units: [], _error: e.message });
    }
    // Pequeña pausa humana entre proyectos (1-3s aleatorio)
    await new Promise(r => setTimeout(r, 1000 + Math.random() * 2000));
  }

  console.log('\n3) Generando archivo de descarga...');
  const blob = new Blob([JSON.stringify(enriched, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `jb_export_${new Date().toISOString().slice(0,10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();

  // Resumen por organization
  const byOrg = {};
  enriched.forEach(p => {
    const n = (p.organization?.name || p.organization || '—').toString();
    byOrg[n] = (byOrg[n] || 0) + 1;
  });
  console.log('\n✓ Descargado. Resumen por inmobiliaria:');
  Object.entries(byOrg).sort((a,b) => b[1] - a[1]).forEach(([n, c]) => {
    console.log(`   ${String(c).padStart(4)} · ${n}`);
  });
})();
