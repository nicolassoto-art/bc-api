"""Audita y corrige fotos con categoria="Otro" en bc-api.

Un bug histórico del editor de stock interno (ya corregido) dejó fotos de
interior de departamento guardadas con categoria="Otro" en decenas de
proyectos. Este script:

1. Barre todos los proyectos (solo lectura, liviano).
2. Para cada foto con categoria=="Otro" (comparación exacta, nunca toca
   jb-planta*/jb-doc*/otras categorías), la clasifica con visión.
3. Si la clasificación es de confianza alta, aplica un PATCH con SOLO el
   campo categoria (nunca es_principal ni orden — pisarlos rompe la portada).
4. Si el modelo no está seguro, no toca la foto: la reporta para revisión manual.

Modo dry_run: hace todo excepto el PATCH final. Sirve para validar la
clasificación antes de escribir en producción.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field

import httpx

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import anthropic
except ImportError:
    anthropic = None

BC_API_BASE = "https://bc-api.178-105-91-29.nip.io"
BC_API_EMAIL = "nicolas.soto@bigcapital.cl"
MODEL = "claude-sonnet-5"
MAX_IMAGE_SIDE = 1568

CATEGORIAS_VALIDAS = {"Interior", "Fachada", "Áreas comunes", "Entorno"}

SYSTEM_PROMPT = """Clasificas fotos de proyectos inmobiliarios en Chile en una de cuatro categorías.

- Interior: el interior de un departamento o casa. Living, comedor, dormitorio,
  cocina, baño, logia, terraza privada de la unidad. Incluye departamentos piloto
  y renders de interior.
- Fachada: el exterior del edificio visto como volumen completo o parcial, desde
  la calle o desde el aire. Incluye renders de fachada y accesos al edificio.
- Áreas comunes: espacios compartidos del condominio. Piscina, quincho, gimnasio,
  sala multiuso, lobby, coworking, terraza panorámica, juegos infantiles,
  estacionamientos, bodegas.
- Entorno: fotos del barrio o del sector. Calles, parques públicos, comercio,
  metro, mapas, vistas de la ciudad sin el edificio como protagonista.

Reglas:
- Si dudas entre dos categorías, responde "No estoy seguro" con confianza baja.
  Es preferible dejar la foto sin clasificar que ponerle una categoría errada.
- Un plano de planta, un cuadro de precios, un folleto o cualquier imagen que sea
  un documento y no una fotografía o render de un espacio: responde
  "No estoy seguro" y explícalo en la razón.
- No asumas que la foto es de interior. Mira la imagen y decide.
- La razón debe tener menos de 25 palabras."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "categoria": {
            "type": "string",
            "enum": ["Interior", "Fachada", "Áreas comunes", "Entorno", "No estoy seguro"],
        },
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        "razon": {"type": "string"},
    },
    "required": ["categoria", "confianza", "razon"],
    "additionalProperties": False,
}


def es_candidata(categoria: str | None) -> bool:
    """Solo el literal "Otro" (case-insensitive, sin espacios). jb-planta*/jb-doc*
    y cualquier otra categoría desconocida se reportan pero nunca se tocan."""
    cat = (categoria or "").strip()
    if cat.startswith("jb-planta") or cat.startswith("jb-doc"):
        return False
    return cat.lower() == "otro"


@dataclass
class Resultado:
    proyecto_id: str
    imagen_id: str
    url: str
    categoria_antes: str
    categoria_propuesta: str
    confianza: str
    razon: str
    aplicado: bool = False
    http_status: int | None = None
    error: str | None = None


def login(client: httpx.Client, password: str) -> str:
    r = client.post(
        f"{BC_API_BASE}/auth/login",
        json={"email": BC_API_EMAIL, "password": password},
        timeout=15.0,
    )
    r.raise_for_status()
    jwt = r.json()["access_token"]
    print(f"::add-mask::{jwt}")
    return jwt


def health_check(client: httpx.Client, retries: int = 10, wait_s: float = 3.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            r = client.get(f"{BC_API_BASE}/health", timeout=10.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if attempt < retries:
            time.sleep(wait_s)
    raise SystemExit("bc-api no respondió 200 en /health tras los reintentos")


def listar_proyectos(client: httpx.Client) -> list[dict]:
    r = client.get(f"{BC_API_BASE}/proyectos", timeout=30.0)
    r.raise_for_status()
    return r.json()


def listar_imagenes(client: httpx.Client, proyecto_id: str) -> list[dict]:
    r = client.get(f"{BC_API_BASE}/proyectos/{proyecto_id}/imagenes", timeout=20.0)
    r.raise_for_status()
    return r.json()


def descargar_y_preparar_imagen(client: httpx.Client, url_relativa: str) -> tuple[str, str]:
    r = client.get(f"{BC_API_BASE}{url_relativa}", timeout=30.0)
    r.raise_for_status()
    contenido = r.content
    mime = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()

    if Image is not None and mime in ("image/jpeg", "image/png", "image/webp"):
        try:
            img = Image.open(io.BytesIO(contenido))
            if max(img.size) > MAX_IMAGE_SIDE:
                img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
                buf = io.BytesIO()
                fmt = "JPEG" if mime == "image/jpeg" else img.format or "PNG"
                img.convert("RGB").save(buf, format=fmt, quality=85)
                contenido = buf.getvalue()
                mime = "image/jpeg" if fmt == "JPEG" else mime
        except Exception:
            pass  # si Pillow falla, se manda la imagen original tal cual

    return base64.b64encode(contenido).decode("ascii"), mime


def clasificar(ai_client, b64_data: str, mime: str) -> dict:
    resp = ai_client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": b64_data},
                    },
                    {"type": "text", "text": "Clasifica esta foto de un proyecto inmobiliario."},
                ],
            }
        ],
        tools=[
            {
                "name": "clasificacion",
                "description": "Devuelve la clasificación de la foto",
                "input_schema": RESPONSE_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": "clasificacion"},
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("El modelo no devolvió una clasificación estructurada")


def aplicar_patch(client: httpx.Client, proyecto_id: str, imagen_id: str, categoria: str) -> int:
    r = client.patch(
        f"{BC_API_BASE}/proyectos/{proyecto_id}/imagenes/{imagen_id}",
        json={"categoria": categoria},
        timeout=20.0,
    )
    r.raise_for_status()
    return r.status_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-fotos", type=int, default=250)
    parser.add_argument("--solo-proyecto", default="")
    parser.add_argument("--out", default="auditoria_fotos.jsonl")
    args = parser.parse_args()

    password = os.environ.get("BC_API_PASSWORD")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not password:
        raise SystemExit("Falta BC_API_PASSWORD en el entorno")
    if not anthropic_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno")
    if anthropic is None:
        raise SystemExit("Falta el paquete 'anthropic' — agrégalo a requirements.txt")

    ai_client = anthropic.Anthropic(api_key=anthropic_key, max_retries=4)

    with httpx.Client(headers={"Accept": "application/json"}) as client:
        print("Health check...")
        health_check(client)

        print("Login...")
        jwt = login(client, password)
        client.headers["Authorization"] = f"Bearer {jwt}"

        print("Listando proyectos...")
        proyectos = listar_proyectos(client)
        if args.solo_proyecto:
            proyectos = [p for p in proyectos if p["id"] == args.solo_proyecto]
            if not proyectos:
                raise SystemExit(f"Proyecto '{args.solo_proyecto}' no encontrado")
        print(f"{len(proyectos)} proyecto(s) a barrer.")

        candidatas: list[tuple[str, dict]] = []
        reportadas_otras: list[dict] = []
        for p in proyectos:
            try:
                imgs = listar_imagenes(client, p["id"])
            except httpx.HTTPError as e:
                print(f"  ! error listando imágenes de {p['id']}: {e}", file=sys.stderr)
                continue
            for img in imgs:
                if es_candidata(img.get("categoria")):
                    candidatas.append((p["id"], img))

        print(f"Barrido completo: {len(candidatas)} foto(s) en categoría 'Otro'.")

        if not candidatas:
            resumen = "Sin hallazgos: ninguna foto en categoría 'Otro'."
            print(resumen)
            escribir_summary(resumen, [])
            return 0

        truncadas = 0
        if len(candidatas) > args.max_fotos:
            truncadas = len(candidatas) - args.max_fotos
            candidatas = candidatas[: args.max_fotos]
            print(f"Tope max_fotos={args.max_fotos} aplicado: {truncadas} foto(s) quedan pendientes para la próxima corrida.")

        resultados: list[Resultado] = []
        for i, (proyecto_id, img) in enumerate(candidatas, 1):
            print(f"[{i}/{len(candidatas)}] {proyecto_id} / {img['id']} ({img['url']})")
            try:
                b64_data, mime = descargar_y_preparar_imagen(client, img["url"])
                clas = clasificar(ai_client, b64_data, mime)
            except Exception as e:
                resultados.append(Resultado(
                    proyecto_id=proyecto_id, imagen_id=img["id"], url=img["url"],
                    categoria_antes=img.get("categoria", ""), categoria_propuesta="",
                    confianza="", razon="", error=str(e),
                ))
                print(f"  ! error: {e}", file=sys.stderr)
                continue

            categoria_propuesta = clas.get("categoria", "")
            confianza = clas.get("confianza", "")
            razon = clas.get("razon", "")

            res = Resultado(
                proyecto_id=proyecto_id, imagen_id=img["id"], url=img["url"],
                categoria_antes=img.get("categoria", ""),
                categoria_propuesta=categoria_propuesta, confianza=confianza, razon=razon,
            )

            aplicable = categoria_propuesta in CATEGORIAS_VALIDAS and confianza == "alta"
            if aplicable and not args.dry_run:
                try:
                    res.http_status = aplicar_patch(client, proyecto_id, img["id"], categoria_propuesta)
                    res.aplicado = True
                    time.sleep(0.15)
                except httpx.HTTPError as e:
                    res.error = str(e)
                    print(f"  ! error aplicando PATCH: {e}", file=sys.stderr)
            elif aplicable and args.dry_run:
                res.aplicado = False  # dry-run: se marca la intención pero no se escribe
            else:
                reportadas_otras.append({"proyecto_id": proyecto_id, "imagen_id": img["id"],
                                          "categoria_propuesta": categoria_propuesta,
                                          "confianza": confianza, "razon": razon})

            resultados.append(res)
            print(f"    -> {categoria_propuesta} (confianza={confianza}) aplicado={res.aplicado}")

        with open(args.out, "w", encoding="utf-8") as f:
            for r in resultados:
                f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")

        n_aplicadas = sum(1 for r in resultados if r.aplicado)
        n_dudosas = len(reportadas_otras)
        n_errores = sum(1 for r in resultados if r.error)

        resumen = (
            f"{'[DRY RUN] ' if args.dry_run else ''}"
            f"{n_aplicadas} foto(s) {'clasificarían' if args.dry_run else 'corregidas'}, "
            f"{n_dudosas} sin clasificar con confianza alta (revisión manual), "
            f"{n_errores} error(es), "
            f"{truncadas} pendiente(s) por tope de corrida."
        )
        print(resumen)
        escribir_summary(resumen, resultados, reportadas_otras, args.dry_run)

    return 0


def escribir_summary(resumen: str, resultados: list, dudosas: list | None = None, dry_run: bool = False) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    dudosas = dudosas or []
    lines = ["# Auditoría de fotos · categoría \"Otro\"", "", resumen, ""]
    if resultados:
        lines.append("| Proyecto | Imagen | Antes | Propuesta | Confianza | Aplicado |")
        lines.append("|---|---|---|---|---|---|")
        for r in resultados:
            rd = r.__dict__ if hasattr(r, "__dict__") else r
            lines.append(
                f"| {rd.get('proyecto_id','')} | {rd.get('imagen_id','')} | "
                f"{rd.get('categoria_antes','')} | {rd.get('categoria_propuesta','')} | "
                f"{rd.get('confianza','')} | {'sí' if rd.get('aplicado') else 'no'} |"
            )
    if dudosas:
        lines.append("")
        lines.append("## Requieren revisión manual")
        for d in dudosas:
            lines.append(f"- `{d['proyecto_id']}` / `{d['imagen_id']}`: {d['razon']} (confianza {d['confianza']})")
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
