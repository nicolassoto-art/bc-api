"""Diagnóstico: evalúa UNA llamada en error y muestra la excepción (sin datos personales)."""
from __future__ import annotations
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal  # noqa: E402
from app.models.llamada import Llamada  # noqa: E402
from app.services import evaluador_llamadas as ev  # noqa: E402
from app.settings import settings  # noqa: E402
import anthropic  # noqa: E402

print("modelo:", settings.evaluador_modelo, "· sdk anthropic:", anthropic.__version__, "· clave cargada:", bool(settings.anthropic_api_key))
db = SessionLocal()
ll = db.query(Llamada).filter(Llamada.estado == "error").order_by(Llamada.id.desc()).first()
if not ll:
    print("no hay llamadas en error"); sys.exit(0)
print("llamada id", ll.id, "· largo transcripción:", len(ll.transcripcion_texto or ""))
try:
    r = ev.evaluar_transcripcion(ll.transcripcion_texto, ll.setter)
    print("OK, puntaje:", ev.puntaje_total(r))
except Exception as e:
    print("ERROR:", type(e).__name__, str(e)[:500])
    traceback.print_exc(limit=3)
