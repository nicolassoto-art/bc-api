"""Re-importa los 7 proyectos puntuales con huérfanas/sin planta."""
import subprocess, time

TARGETS = [
    ("72GkWnlW", "Terrazzo"),
    ("G3jWrRoE", "Abdón Cifuentes"),
    ("C0xMpK4K", "Eleuterio Ramírez"),
    ("KvRtrtXK", "Novus Torre E"),
    ("9MubHeQ8", "Tocornal"),
    ("86YW1rPt", "Centenario I"),
    ("jfkJBrPQ", "Froilan Roa"),
]

ok, fail = 0, 0
for i, (jb_id, nombre) in enumerate(TARGETS, 1):
    print(f"\n[{i}/{len(TARGETS)}] {time.strftime('%H:%M')} → {jb_id} ({nombre})")
    r = subprocess.run(["gh","workflow","run","import-jb.yml","-f",f"jb_id={jb_id}"], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ✗ trigger: {r.stderr[:200]}"); fail += 1; continue
    time.sleep(10)
    rid = subprocess.check_output(["gh","run","list","--workflow=import-jb.yml","--limit","1","--json","databaseId","-q",".[0].databaseId"]).decode().strip()
    print(f"  RUN: {rid}")
    for _ in range(40):
        time.sleep(30)
        st = subprocess.check_output(["gh","run","view",rid,"--json","status","-q",".status"]).decode().strip()
        if st == "completed": break
    concl = subprocess.check_output(["gh","run","view",rid,"--json","conclusion","-q",".conclusion"]).decode().strip()
    if concl == "success":
        ok += 1; print(f"  ✅ {time.strftime('%H:%M')}")
    else:
        fail += 1; print(f"  ❌ {concl}")
    time.sleep(15)

print(f"\n========== {ok}/{len(TARGETS)} OK ==========")
