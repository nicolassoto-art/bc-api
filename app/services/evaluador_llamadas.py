"""Evaluación automática de las llamadas de las setters contra el script de agendamiento.

Pauta: "Script telefónico · La llamada que cierra reuniones" (5 pasos, reglas,
escudo de objeciones). Mismo patrón que la evaluación de reuniones del agente GHL:
herramienta forzada, temperatura 0, tope de caracteres y falla sin romper nada.

Flujo: el webhook deja la llamada en `pendiente` cuando llega la transcripción; el
job `evaluar_pendientes` (programador, cada N min, un solo worker) la toma con
FOR UPDATE SKIP LOCKED, la evalúa y la deja en `ok`, `omitida` o `error` (hasta 3
intentos). El puntaje total se calcula en código a partir de los pasos.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.llamada import Llamada
from ..settings import settings
from . import zadarma

log = logging.getLogger(__name__)

VERSION_PAUTA = "v1-2026-10"
MAX_CARACTERES = 60_000
DURACION_MINIMA_S = 60
MAX_INTENTOS = 3
ESPERA_ANTES_DE_EVALUAR = timedelta(minutes=2)   # deja llegar el aviso de fin de llamada
EVALUANDO_COLGADA = timedelta(minutes=30)

PASOS = {   # paso → peso (suma 100)
    "apertura": 15,
    "dolor": 20,
    "propuesta_valor": 20,
    "calificacion": 20,
    "cierre": 25,
}
CASTIGOS = {"nombro_proyecto_en_apertura": 10, "rut_antes_de_agendar": 5}

SISTEMA = """Eres quien evalúa la calidad de las llamadas telefónicas de las setters de BigCapital, \
una empresa chilena de asesoría en inversión inmobiliaria. La setter llama a un cliente que pidió \
información y su única meta es agendar una videollamada de 25-30 minutos con un especialista. \
Evalúas la transcripción contra el script oficial de la empresa.

La transcripción viene separada por canal ("Canal 1", "Canal 2"). Deduce qué canal es la setter \
(quien se presenta como asesora de BigCapital y conduce la llamada) y cuál es el cliente. La \
transcripción es automática y en español de México: tolera errores de reconocimiento en nombres, \
comunas y montos; no los penalices.

SCRIPT OFICIAL (pauta)
Mentalidad: vender sin vender (ganarse la reunión, no vender el departamento); energía y sonrisa \
telefónica; hacer preguntas y escuchar sin interrumpir; no responder todo por teléfono; urgencia real.

Paso 1 · apertura (peso 15): confirma que habla con el cliente y espera respuesta; se presenta con \
nombre y "asesor/a de inversión inmobiliaria de BigCapital"; recuerda que el cliente pidió información \
(comuna o punto de referencia); dice que quiere darle información a su medida. REGLA DURA: jamás \
nombrar el proyecto ni la inmobiliaria. Si el cliente no tiene tiempo, ofrece dos horarios concretos.

Paso 2 · dolor (peso 20): pregunta si ya invirtió antes o sería su primera vez y profundiza \
(qué lo motivó: ingreso extra, patrimonio, algo puntual); preguntas abiertas y silencio para escuchar.

Paso 3 · propuesta_valor (peso 20): explica por qué BigCapital es distinto: busca el proyecto que \
calce con su perfil entre más de 100 edificios; gestiona el crédito hipotecario (tasas, plazos, \
financiamiento) sin costo; busca el primer arrendatario gratis; sin costos ni comisiones; cierra con \
"¿eso te hace sentido?". Natural, no leído como lista.

Paso 4 · calificacion (peso 20): pide permiso ("preguntas rápidas, no más de 2 minutos") y averigua: \
renta líquida mensual y si es fija o variable; contrato indefinido o a plazo y antigüedad; DICOM en \
los últimos 5 años; dividendos o créditos de consumo vigentes y cuánto paga; ahorro para el pie; si \
podría pagar el pie en cuotas y cuánto mensual; si decide solo/a o con alguien más. Sin hacer sentir \
evaluado al cliente.

Paso 5 · cierre (peso 25): resume que tiene buen perfil; propone videollamada de 30 minutos sin \
compromiso para ver 2-3 opciones con números reales; ofrece DOS horarios concretos (no "¿cuándo \
quieres?"); confirma día y hora; avisa que le llegará la invitación al correo y un recordatorio por \
WhatsApp; RECIÉN DESPUÉS de agendar pide el RUT (si duda, no presiona).

Escudo de objeciones (respuestas esperadas):
- "No tengo dinero / no tengo para el pie": hay opciones para financiar el pie (bono pie, cuotas); en \
la reunión se muestra cómo.
- "Ya tengo un corredor": perfecto, compara en paralelo, al final gana el cliente.
- "No tengo tiempo para una reunión": son 25 minutos por videollamada desde donde esté; ofrece dos horarios.
- "Mándame información primero": la información genérica no reemplaza ver su caso; propone la reunión; \
si insiste, por política no se envía información antes de una asesoría.

Si la llamada no llegó a cierto paso (por ejemplo, el cliente cortó), marca ese paso como "no_aplica" \
en vez de puntuarlo en 0, salvo que la setter debió llegar y no lo hizo.

Escribe todo en español de Chile, con tuteo, claro y concreto, sin voseo y sin anglicismos poco \
comunes (usa "cliente", "puntaje", "seguimiento", "reunión"). Las citas de evidencia deben ser \
textuales de la transcripción y breves. Registra tu evaluación con la herramienta."""

_ENUM_CUMPLE = ["si", "parcial", "no", "no_aplica"]
HERRAMIENTA = {
    "name": "registrar_evaluacion",
    "description": "Registra la evaluación de la llamada contra el script.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["resultado_llamada", "pasos", "reglas", "objeciones", "lo_que_hizo_bien", "consejo", "resumen"],
        "properties": {
            "resultado_llamada": {"type": "string", "enum": ["agendo", "reagendar", "no_agendo", "sin_interes", "no_aplica"]},
            "pasos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["paso", "cumple", "puntaje", "evidencia", "comentario"],
                    "properties": {
                        "paso": {"type": "string", "enum": list(PASOS)},
                        "cumple": {"type": "string", "enum": _ENUM_CUMPLE},
                        "puntaje": {"type": "integer", "minimum": 0, "maximum": 100},
                        "evidencia": {"type": "string"},
                        "comentario": {"type": "string"},
                    },
                },
            },
            "reglas": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nombro_proyecto_en_apertura", "rut_antes_de_agendar", "ofrecio_dos_horarios", "aviso_recordatorio_whatsapp"],
                "properties": {
                    "nombro_proyecto_en_apertura": {"type": "boolean"},
                    "rut_antes_de_agendar": {"type": "boolean"},
                    "ofrecio_dos_horarios": {"type": "string", "enum": _ENUM_CUMPLE},
                    "aviso_recordatorio_whatsapp": {"type": "string", "enum": _ENUM_CUMPLE},
                },
            },
            "objeciones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["objecion", "respuesta", "evaluacion"],
                    "properties": {
                        "objecion": {"type": "string"},
                        "respuesta": {"type": "string"},
                        "evaluacion": {"type": "string", "enum": ["bien", "regular", "mal"]},
                    },
                },
            },
            "lo_que_hizo_bien": {"type": "array", "items": {"type": "string"}},
            "consejo": {"type": "string"},
            "resumen": {"type": "string"},
        },
    },
}


def puntaje_total(ev: dict) -> Optional[float]:
    """Promedio ponderado de los pasos aplicables, menos castigos por reglas duras."""
    suma = peso = 0.0
    for p in ev.get("pasos") or []:
        w = PASOS.get(p.get("paso"))
        if not w or p.get("cumple") == "no_aplica":
            continue
        suma += w * max(0, min(100, int(p.get("puntaje", 0))))
        peso += w
    if not peso:
        return None
    total = suma / peso
    reglas = ev.get("reglas") or {}
    for regla, castigo in CASTIGOS.items():
        if reglas.get(regla) is True:
            total -= castigo
    return round(max(0.0, min(100.0, total)), 1)


def motivo_para_omitir(ll: Llamada) -> Optional[str]:
    # Zadarma avisa de las llamadas de TODOS los anexos (también Carolina y Nicolás):
    # solo se evalúan las de las setters configuradas en zadarma_anexos.
    if ll.anexo not in settings.zadarma_anexos_map:
        return "no es un anexo de setter"
    if ll.resultado and ll.resultado != "answered":
        return "no contestada"
    if ll.duracion_s is not None and ll.duracion_s < DURACION_MINIMA_S:
        return "dura menos de 60 s"
    if not (ll.transcripcion_texto or "").strip():
        return "sin transcripción"
    return None


def _cliente():
    import anthropic
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)


def evaluar_transcripcion(texto: str, setter: Optional[str], cliente: Any = None) -> dict:
    """Llama al modelo y devuelve el dict de la evaluación (lanza si falla)."""
    cliente = cliente or _cliente()
    contexto = f"Setter: {setter or 'sin identificar'}\n\nTranscripción:\n{texto[:MAX_CARACTERES]}"
    resp = cliente.messages.create(
        model=settings.evaluador_modelo,
        max_tokens=3000,
        temperature=0,
        system=[{"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}],
        tools=[HERRAMIENTA],
        # Algunos modelos no aceptan forzar la herramienta (tool_choice "tool"/"any"):
        # se deja en "auto" y la instrucción pide registrarla; si no la usa, se reintenta.
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": contexto}],
    )
    for bloque in resp.content:
        if getattr(bloque, "type", None) == "tool_use" and getattr(bloque, "name", None) == HERRAMIENTA["name"]:
            ev = dict(bloque.input)
            if not isinstance(ev.get("pasos"), list):
                raise ValueError("evaluación sin pasos")
            return ev
    raise ValueError("el modelo no registró la evaluación")


def _tomar_pendientes(db: Session, limite: int) -> list[int]:
    corte = datetime.utcnow() - ESPERA_ANTES_DE_EVALUAR
    ids = db.execute(
        select(Llamada.id)
        .where(Llamada.estado == "pendiente", Llamada.updated_at < corte)
        .order_by(Llamada.id)
        .limit(limite)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    if ids:
        db.execute(update(Llamada).where(Llamada.id.in_(ids)).values(estado="evaluando", updated_at=datetime.utcnow()))
    db.commit()
    return list(ids)


def evaluar_llamada(db: Session, ll: Llamada, cliente: Any = None) -> None:
    motivo = motivo_para_omitir(ll)
    if motivo:
        ll.estado = "omitida"
        ll.evaluacion = {"omitida": motivo}
        ll.evaluada_en = datetime.utcnow()
        return
    ll.intentos = (ll.intentos or 0) + 1
    try:
        ev = evaluar_transcripcion(ll.transcripcion_texto, ll.setter, cliente)
    except Exception as e:   # best-effort: la llamada queda guardada y se reintenta
        log.warning("evaluador: falló pbx_call_id=%s intento=%s (%s)", ll.pbx_call_id, ll.intentos, type(e).__name__)
        ll.estado = "error" if ll.intentos >= MAX_INTENTOS else "pendiente"
        return
    ll.evaluacion = ev
    ll.puntaje = puntaje_total(ev)
    ll.version_pauta = VERSION_PAUTA
    ll.evaluada_en = datetime.utcnow()
    ll.estado = "ok"


def evaluar_pendientes(limite: int = 5, cliente: Any = None) -> int:
    """Job del programador. Devuelve cuántas llamadas procesó."""
    if not settings.anthropic_api_key and cliente is None:
        log.info("evaluador: sin ANTHROPIC_API_KEY, no evalúa")
        return 0
    db = SessionLocal()
    try:
        # Rescata las que quedaron en 'evaluando' por un reinicio.
        db.execute(
            update(Llamada)
            .where(Llamada.estado == "evaluando", Llamada.updated_at < datetime.utcnow() - EVALUANDO_COLGADA)
            .values(estado="pendiente")
        )
        db.commit()
        ids = _tomar_pendientes(db, limite)
        for lid in ids:
            ll = db.get(Llamada, lid)
            evaluar_llamada(db, ll, cliente)
            db.commit()
        zadarma.purgar_eventos(db)
        return len(ids)
    except Exception as e:
        db.rollback()
        log.error("evaluador: error del job (%s)", e, exc_info=True)
        return 0
    finally:
        db.close()
