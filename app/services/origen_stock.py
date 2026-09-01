"""Etiqueta de origen para los eventos de stock del timeline — bc-api · 2026-09-01

Responde dos preguntas que ANTES estaban mezcladas en una sola decisión
(el email del usuario autenticado), y esa mezcla era el bug:

  1. ¿La carga es automática o la subió una persona?  -> depende de QUIÉN llama
  2. ¿De qué fuente salió el dato?                    -> depende de QUÉ proyecto es

Bug que esto corrige (reportado 2026-09-01 sobre edificio-carrera-capital):
el timeline de un proyecto de Ingevec decía "Actualización automática
(scraper MNK · PlanOk)". Doblemente falso: no es el scraper de MNK, y
Ingevec no usa PlanOk sino ecore.cl. Causa raíz: casi todos los scrapers
autentican contra bc-api con la MISMA cuenta de servicio compartida
(`mnk-scraper@bigcapital.cl`, creada en su momento para MNK), así que la rama
por email rotulaba TODO el sistema como MNK/PlanOk — unos 65 proyectos de
5 inmobiliarias distintas.

Además: `_es_auto` se derivaba del PREFIJO del texto
(`_origen.startswith("Actualización automática")`). Eso ataba comportamiento
real —supresión del evento de timeline y del correo "Stock actualizado" en
corridas sin cambios, y el flag `origen_auto` que consume el informe diario—
a una cadena de texto con tildes. Acá el booleano se decide por quién llama y
el texto se compone después, así que ya no se puede romper editando un string.
"""
from __future__ import annotations

import unicodedata
from typing import Optional, Tuple


def _norm(s: Optional[str]) -> str:
    """Normaliza para usar como clave: sin tildes, minúsculas, espacios colapsados.

    Así "AJ URBANA", "AJ Urbana" y "  aj  urbana " caen en la misma entrada.
    Mismo criterio que ya usa daily_report.py para agrupar por inmobiliaria.
    """
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


# Fuente real del stock por inmobiliaria (clave normalizada con _norm).
# Solo se consulta cuando YA se decidió que la carga es automática — una
# persona que sube un Excel a mano nunca hereda la plataforma.
#
# Verificado leyendo el código de cada scraper (2026-09-01). Las inmobiliarias
# SIN scraper (Iroyal, CISS, Prohabit, Itrio, Ileon, Origen, INSIGNE, Vitalia,
# Olimpia) NO llevan entrada a propósito: su stock lo sube una persona y debe
# seguir diciendo "Carga de Excel de stock".
FUENTE_POR_INMOBILIARIA = {
    "ingevec":                     "scraper Ingevec · ecore.cl",
    "euroinmobiliaria":            "scraper Euro · Mobysuite",
    "ecasa":                       "scraper Ecasa · InverAPP",
    "maestra":                     "scraper Maestra · Maestranet/Excel",
    "aj urbana":                   "sync AJ Urbana · planilla de Drive",
    "stitchkin":                   "scraper Stitchkin · Google Sheets",
    "inmobiliaria larrain prieto": "scraper Larrain Prieto · PlanOk",
    "mnk":                         "scraper MNK · PlanOk",
    "vellatrix":                   "scraper Vellatrix · Excel por correo",
    "inmobiliaria las palmas":     "scraper Las Palmas · Excel de Drive",
}

# Orígenes explícitos aceptados vía ?origen=. WHITELIST, no passthrough:
# si fuera libre, cualquier llamador podría mandar ?origen=x y silenciar el
# evento de timeline y el correo. Un valor no registrado se ignora y se cae
# a la decisión por email (exactamente el comportamiento anterior).
ORIGENES = {
    "jb_importer": "Actualización automática (JetBrokers · scraper)",
    # AJ Urbana sincroniza desde una planilla de Drive con un script propio en
    # el VPS (/opt/bigcapital-tests/sync_aj_to_bcapi.py) que autentica con una
    # cuenta PERSONAL, no de servicio. Sin este origen explícito sus 9 proyectos
    # caen en la rama manual: quedan rotulados "Carga de Excel de stock" como si
    # los hubiera subido alguien a mano, se guardan con origen_auto=False (el
    # informe diario los cuenta como actividad de una persona) y se saltean la
    # supresión anti-spam, mandando un correo "Stock actualizado" por cada sync.
    "aj_urbana": "Actualización automática (sync AJ Urbana · planilla de Drive)",
}

# Prefijos de cuentas de servicio conocidas.
_PREFIJOS_AUTO = ("mnk-scraper", "maestra-scraper", "jb-scraper", "sistema")


def es_cuenta_automatica(email: Optional[str]) -> bool:
    """True si el email corresponde a una cuenta de servicio/scraper.

    Decide SOLO automático vs manual. La plataforma ya no se deduce del email
    (esa era la causa raíz del bug): eso sale del proyecto o del origen explícito.
    """
    e = (email or "").lower()
    return e.startswith(_PREFIJOS_AUTO) or "scraper" in e or "importer" in e


def etiqueta_origen(
    origen: Optional[str],
    email: Optional[str],
    inmobiliaria: Optional[str],
) -> Tuple[str, bool]:
    """Devuelve (texto_para_el_timeline, es_automatico).

    Precedencia: origen explícito registrado > mapa por inmobiliaria > genérico.

    El booleano NO se deriva del texto — se decide por quién llama. Quien toque
    esto: NO volver a calcular `es_automatico` con un startswith sobre el texto;
    de ese booleano cuelgan la supresión del evento de timeline, la del correo
    "Stock actualizado" y el flag `origen_auto` del informe diario.
    """
    registrado = ORIGENES.get((origen or "").strip().lower())
    if registrado:
        return registrado, True

    if es_cuenta_automatica(email):
        fuente = FUENTE_POR_INMOBILIARIA.get(_norm(inmobiliaria)) or "scraper"
        return "Actualización automática ({})".format(fuente), True

    return "Carga de Excel de stock", False
