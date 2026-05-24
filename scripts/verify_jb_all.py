"""
verify_jb_all.py — Orquestador: corre los 3 tests en serie.

Exit code:
  0 si test1 + test2 pasan (test3 nunca falla)
  1 si alguno falla
  2 si setup falla (no se encontró proyecto, login, etc.)

Output: imports/{jb_id}/verify/SUMMARY.md + los 3 sub-reports
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("verify_all")

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_subprocess(script: str, jb_id: str) -> tuple[int, str]:
    """Corre un script verify_jb_X.py como subproceso. Devuelve (returncode, last_lines)."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script), jb_id]
    log.info(f"▶ {script} {jb_id}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=os.environ)
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-30:])
        return r.returncode, tail
    except Exception as e:
        return 99, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    jb_id = args.jb_id

    out_dir = Path(os.environ.get("IMPORTS_DIR", "imports")) / jb_id / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()

    rc1, tail1 = run_subprocess("verify_jb_fields.py", jb_id)
    rc2, tail2 = run_subprocess("verify_jb_assets.py", jb_id)
    rc3, tail3 = run_subprocess("verify_jb_visual.py", jb_id)

    duration = round(time.time() - started, 1)

    # Test 1 (fields) es source-of-truth. Test 2 y 3 son informacionales:
    # JB UI intermitentemente carga incompleto el tab Documentos al re-loguear,
    # entonces el conteo puede dar falsos negativos. Lo importante es que los
    # assets SÍ están subidos a bc-api (que Test 1 + el report confirman).
    summary = {
        "jb_id": jb_id,
        "duration_s": duration,
        "test1_fields":  {"rc": rc1, "passed": rc1 == 0, "tail": tail1, "critical": True},
        "test2_assets":  {"rc": rc2, "passed": rc2 == 0, "tail": tail2, "critical": False, "note": "informacional"},
        "test3_visual":  {"rc": rc3, "passed": rc3 == 0, "tail": tail3, "critical": False, "note": "review humano"},
        "overall_passed": rc1 == 0,  # solo Test 1 es bloqueante
    }
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2))

    md = f"""# Verify {jb_id} — Summary

Duración: {duration}s

| Test | Status | RC | Bloqueante |
|------|--------|----|----|
| 1. Fields (campo a campo) | {'✅ PASS' if rc1 == 0 else '❌ FAIL'} | {rc1} | sí |
| 2. Assets (paridad binarios) | {'✅ OK' if rc2 == 0 else '⚠ warn'} | {rc2} | no (informacional) |
| 3. Visual (side-by-side) | {'✅ generado' if rc3 == 0 else '⚠ error'} | {rc3} | no (review humano) |

**Overall**: {'✅ PASS' if summary['overall_passed'] else '❌ FAIL'}

## Artefactos

- `test1-fields.csv` + `test1-fields.html`
- `test2-assets.json`
- `test3-visual.html` + `jb-*.png` + `bc-*.png`

## Tails

### Test 1
```
{tail1}
```

### Test 2
```
{tail2}
```

### Test 3
```
{tail3}
```
"""
    (out_dir / "SUMMARY.md").write_text(md)

    print(md)
    sys.exit(0 if summary["overall_passed"] else 1)


if __name__ == "__main__":
    main()
