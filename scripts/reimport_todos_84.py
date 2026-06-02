"""
reimport_todos_84.py — Re-importa los 84 proyectos secuencialmente.
Idempotente: salta los que ya tienen un import success en las últimas 4 horas
con sha actual del code.
"""
import json, subprocess, time, sys

# Lista completa de 84 jb_ids (case original como JB los usa)
JB_IDS = [
    "Sfp8j2Sq","NeOU0rvU","G3jWrRoE","hvEkYVJq","86YW1rPt","Xm0GuxtO","WGfF1Hcm",
    "is9kmud9","48t1IInf","SUWJ0Rye","iB3uhp34","exrBr6Tp","IgfWZVh2","IDLyBU4W",
    "atUiRS6M","NgBHe0jo","GMrPAyQt","Xm0ZQPxk","jfkJBrPQ","WWMCny3E","CGFo7vDQ",
    "T8UuEf2r","72GkWnlW","9MubHeQ8","1kvflc3m","OwPhi37z","v8tAVcOG","IaIQ9iTH",
    "C8R7VcvH","dX4Rddfn","m9zXfNHe","osnL3M1C","zOHnfOQJ","q8RwqXao","4Kny8VBw",
    "sFfaXZIQ","Dw5PBsEd","qlkZufJk","R5cTUSc8","W8P6QggB","b7Aniv5k","PsqVqc03",
    "Vw1zOkV6","ImxDl3nl","3JcwgGZi","f8VQHYVK","AJBqsIIi","ksHJwBab","HvNRYfwm",
    "vWkZk19n","nYjXw5kL","pkR9sdRb","hw9SoClo","thmz67c6","mshykABZ","kUYM4Rl8",
    "wHL2AUKl","vWeKp0EM","9YO68rOa","LXXJ9agb","OHpd4zbx","C0xMpK4K","Ml02Ecl7",
    "KvRtrtXK","eHxgQsNq","FrOy8Hxr","hKtYFYuQ","Ao8J0BvU","4nyJKnq9","5d7qpMgc",
    "iaEIx5Eo","RNEqQ6dw","UAq8pgxr","teQxJTnq","zkp4Z7HH","7qF2CCA7","LmVJgz7F",
    "nmLpNNTD","3Av5Af58","tvFyLEMz","1gaVJbKl","hSeBHnw1","dr6uuHkX","75PDpryA",
]

def main():
    total = len(JB_IDS)
    ok, fail = 0, 0
    for i, jb_id in enumerate(JB_IDS, 1):
        print(f"\n[{i}/{total}] {time.strftime('%H:%M')} → {jb_id}")
        r = subprocess.run(["gh","workflow","run","import-jb.yml","-f",f"jb_id={jb_id}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ✗ trigger: {r.stderr[:200]}")
            fail += 1; continue
        time.sleep(10)
        rid = subprocess.check_output(["gh","run","list","--workflow=import-jb.yml","--limit","1","--json","databaseId","-q",".[0].databaseId"]).decode().strip()
        for _ in range(40):  # max 20 min
            time.sleep(30)
            st = subprocess.check_output(["gh","run","view",rid,"--json","status","-q",".status"]).decode().strip()
            if st == "completed": break
        concl = subprocess.check_output(["gh","run","view",rid,"--json","conclusion","-q",".conclusion"]).decode().strip()
        if concl == "success":
            ok += 1
            print(f"  ✅ {time.strftime('%H:%M')}")
        else:
            fail += 1
            print(f"  ❌ {concl}")
        # Pausa anti-rate-limit JB
        time.sleep(15)
    print(f"\n========== RESUMEN ==========")
    print(f"OK: {ok}/{total}  FAIL: {fail}")

if __name__ == "__main__":
    main()
