import subprocess, time
TARGETS = [
    ("CGFo7vDQ", "Matta"),
    ("G3jWrRoE", "Abdón Cifuentes"),
    ("zkp4Z7HH", "Alto Buzeta"),
    ("vWkZk19n", "Bandera 1060"),
]
ok, fail = 0, 0
for i, (jb_id, n) in enumerate(TARGETS, 1):
    print(f"[{i}/{len(TARGETS)}] {time.strftime('%H:%M')} {jb_id} ({n})")
    subprocess.run(["gh","workflow","run","import-jb.yml","-f",f"jb_id={jb_id}"])
    time.sleep(10)
    rid = subprocess.check_output(["gh","run","list","--workflow=import-jb.yml","--limit","1","--json","databaseId","-q",".[0].databaseId"]).decode().strip()
    for _ in range(40):
        time.sleep(30)
        if subprocess.check_output(["gh","run","view",rid,"--json","status","-q",".status"]).decode().strip() == "completed": break
    concl = subprocess.check_output(["gh","run","view",rid,"--json","conclusion","-q",".conclusion"]).decode().strip()
    if concl == "success": ok += 1; print(f"  ✅ {time.strftime('%H:%M')}")
    else: fail += 1; print(f"  ❌ {concl}")
    time.sleep(15)
print(f"\n{ok}/{len(TARGETS)} OK")
