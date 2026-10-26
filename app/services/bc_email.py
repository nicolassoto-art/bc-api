"""Diseño único de los correos de BigCapital (14-oct-2026).

Referencia: el correo «Tus reuniones de hoy» del motor (cabecera oscura compacta con el logo, título, cuerpo blanco,
acento verde). Todos los correos del sistema deben salir de aquí: mismo logo, tipografía, colores, espaciados,
tarjetas, pasos, botones y pie. Versión Python; la versión PHP (bc_email.php) produce el mismo HTML.

Uso:
    from bc_email import email_html, p, h2, card, steps, boton, codigo, lista, ruta, porque
    html = email_html("Título", p("Hola, Ana") + card(p("..."), "verde"), preheader="Resumen para la bandeja")
"""
import html as _h

# ── Paleta y medidas (única fuente de verdad) ────────────────────────────────
FONDO = "#eef0f3"      # fondo de la bandeja
TARJETA = "#ffffff"
OSCURO = "#0f1115"     # cabecera y títulos
TEXTO = "#333333"
SUAVE = "#555555"
TENUE = "#8a8a8a"
VERDE = "#7DC242"      # acento de marca
VERDE_TX = "#4f7a1f"   # verde legible sobre blanco/verde claro
VERDE_FONDO = "#f6f8f1"
NARANJA = "#e65100"
NARANJA_FONDO = "#fff8f0"
ROJO = "#c62828"
ROJO_FONDO = "#fdf1f1"
GRIS_FONDO = "#f4f6f9"
LINEA = "#e9ece4"
LOGO = "https://herramientas.bigcapital.cl/logo-bigcapital-white.png"
LOGO_ANCHO = 170
FUENTE = "Arial,Helvetica,sans-serif"
MONO = "'SFMono-Regular',Menlo,Consolas,monospace"
ANCHO = 600
PIE = "BigCapital Inversión Inmobiliaria"
FIRMA_HTML = "Saludos,<br><b>Equipo BigCapital</b>"   # firma de equipo (decisión 22-oct-2026)


def esc(t):
    """Escapa & < > " ' con las mismas entidades que la versión PHP (la salida debe ser idéntica)."""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


# ── Bloques de texto ─────────────────────────────────────────────────────────
def p(texto, suave=False, margen="0 0 14px"):
    """Párrafo. `texto` ya puede traer HTML (<b>, <a>)."""
    c = SUAVE if suave else TEXTO
    return f'<p style="margin:{margen};font-size:15px;line-height:1.6;color:{c};">{texto}</p>'


def h2(texto, icono=""):
    ic = f"{icono} " if icono else ""
    return (f'<div style="margin:22px 0 12px;font-size:12px;font-weight:700;letter-spacing:1.2px;'
            f'text-transform:uppercase;color:{VERDE_TX};">{ic}{esc(texto)}</div>')


def h3(texto, etiqueta_html=""):
    return (f'<div style="margin:6px 0 8px;font-size:16px;font-weight:700;color:{OSCURO};">{texto} {etiqueta_html}</div>')


def lista(items, ordenada=False):
    tag = "ol" if ordenada else "ul"
    li = "".join(f'<li style="margin:0 0 6px;">{i}</li>' for i in items)
    return (f'<{tag} style="margin:0 0 14px;padding-left:20px;font-size:15px;line-height:1.55;color:{TEXTO};">'
            f'{li}</{tag}>')


def porque(texto):
    return (f'<div style="margin-top:8px;font-size:13.5px;line-height:1.5;color:{SUAVE};">'
            f'<b style="color:{VERDE_TX};">Por qué:</b> {texto}</div>')


def ruta(*partes):
    """Ruta de menús: Configuración › Mi perfil › General."""
    sep = f' <span style="color:{TENUE};">&rsaquo;</span> '
    chips = sep.join(
        f'<span style="display:inline-block;background:{GRIS_FONDO};border-radius:6px;padding:2px 8px;margin:2px 0;font-weight:700;color:{OSCURO};'
        f'">{esc(x)}</span>' for x in partes)
    return f'<div style="margin:0 0 10px;font-size:13.5px;line-height:2;">{chips}</div>'


def etiqueta(texto, tono="naranja"):
    fondo, color = {"naranja": ("#fff3e0", NARANJA), "verde": ("#e8f3d9", VERDE_TX), "gris": ("#eceff1", SUAVE),
                    "rojo": ("#fde8e8", ROJO)}[tono]
    return (f'<span style="background:{fondo};color:{color};font-size:11px;font-weight:700;padding:2px 8px;'
            f'border-radius:10px;vertical-align:middle;">{esc(texto)}</span>')


# ── Tarjetas ─────────────────────────────────────────────────────────────────
_TONOS = {"verde": (VERDE_FONDO, VERDE), "naranja": (NARANJA_FONDO, NARANJA), "rojo": (ROJO_FONDO, ROJO),
          "gris": (GRIS_FONDO, "#b0b7c3")}


def card(contenido, tono="verde", titulo=None):
    """Tarjeta con borde de color a la izquierda (como la de «Tu día de hoy»)."""
    fondo, borde = _TONOS[tono]
    tcolor = {"verde": VERDE_TX, "naranja": NARANJA, "rojo": ROJO, "gris": OSCURO}[tono]
    t = (f'<div style="font-size:14px;font-weight:700;color:{tcolor};margin-bottom:6px;">{titulo}</div>'
         if titulo else "")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{fondo};border-left:4px solid {borde};border-radius:10px;margin:0 0 16px;">'
            f'<tr><td style="padding:16px 20px;font-size:14.5px;line-height:1.65;color:{TEXTO};">{t}{contenido}</td></tr></table>')


def codigo(texto, rotulo=None):
    """Caja para una clave o código (monoespaciado)."""
    r = f'<div style="font-size:12px;color:{SUAVE};margin-bottom:3px;">{esc(rotulo)}</div>' if rotulo else ""
    return (f'{r}<div style="display:inline-block;margin:0 0 12px;padding:9px 14px;background:#ffffff;'
            f'border:1px dashed {VERDE};border-radius:8px;font-family:{MONO};font-size:19px;font-weight:700;'
            f'letter-spacing:1px;color:{OSCURO};word-break:break-all;">{texto}</div>')


def dato(rotulo, valor):
    return (f'<div style="font-size:12px;color:{SUAVE};margin-bottom:2px;">{esc(rotulo)}</div>'
            f'<div style="font-size:17px;font-weight:700;color:{OSCURO};margin-bottom:12px;word-break:break-all;">{valor}</div>')


def steps(items):
    """Pasos numerados. items = [(titulo, texto_html, porque_html|None), ...]"""
    filas = []
    for n, it in enumerate(items, 1):
        titulo, texto = it[0], it[1]
        pq = porque(it[2]) if len(it) > 2 and it[2] else ""
        filas.append(
            f'<tr><td width="44" valign="top" style="padding:0 0 16px;"><div style="width:30px;height:30px;line-height:30px;'
            f'border-radius:15px;background:{VERDE};color:{OSCURO};font-weight:700;font-size:14px;text-align:center;">{n}</div></td>'
            f'<td valign="top" style="padding:0 0 16px;font-size:15px;line-height:1.55;color:{TEXTO};">'
            f'<b style="font-size:15.5px;color:{OSCURO};">{titulo}</b><br><span style="color:{SUAVE};">{texto}</span>{pq}</td></tr>')
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 6px;">{"".join(filas)}</table>'


def boton(texto, url):
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 18px;"><tr>'
            f'<td style="background:{VERDE};border-radius:10px;"><a href="{esc(url)}" style="display:inline-block;'
            f'padding:13px 28px;font-size:15px;font-weight:700;color:{OSCURO};text-decoration:none;">{texto}</a></td></tr></table>')


def tabla(encabezados, filas):
    th = "".join(f'<th align="left" style="padding:8px 10px;font-size:12px;color:{SUAVE};text-transform:uppercase;'
                 f'letter-spacing:.5px;border-bottom:2px solid {LINEA};">{esc(x)}</th>' for x in encabezados)
    tr = "".join("<tr>" + "".join(f'<td style="padding:9px 10px;font-size:14px;color:{TEXTO};border-bottom:1px solid {LINEA};">{c}</td>'
                                  for c in f) + "</tr>" for f in filas)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 16px;"><tr>{th}</tr>{tr}</table>'


# ── Estructura general ───────────────────────────────────────────────────────
def email_html(titulo, cuerpo, preheader="", pie_extra="", pie_linea="Si tienes dudas, responde este correo y te ayudamos.", firma=True):
    """Correo completo. `titulo` es el H1 (puede llevar un emoji); `cuerpo` es el HTML de los bloques de arriba.
    `firma=True` agrega «Saludos, Equipo BigCapital» antes del pie; `firma=False` la omite (correos que ya van
    firmados por una persona)."""
    pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{esc(preheader)}</div>'
           if preheader else "")
    extra = (f'<tr><td style="padding:14px 30px 0;color:{TENUE};font-size:13px;line-height:1.6;">{pie_extra}</td></tr>'
             if pie_extra else "")
    sig = (f'<tr><td style="padding:0 30px 18px;font-size:15px;line-height:1.6;color:{TEXTO};">{FIRMA_HTML}</td></tr>'
           if firma else "")
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"></head>'
        f'<body style="margin:0;padding:0;background:{FONDO};">{pre}'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FONDO};padding:28px 12px;'
        f'font-family:{FUENTE};margin:0;"><tr><td align="center">'
        f'<table role="presentation" width="{ANCHO}" cellpadding="0" cellspacing="0" style="background:{TARJETA};'
        f'border-radius:14px;overflow:hidden;max-width:{ANCHO}px;width:100%;box-shadow:0 4px 18px rgba(15,17,21,.06);">'
        f'<tr><td align="center" style="background:{OSCURO};padding:22px;"><img src="{LOGO}" alt="BigCapital" '
        f'width="{LOGO_ANCHO}" style="display:block;max-width:{LOGO_ANCHO}px;border:0;"></td></tr>'
        f'<tr><td style="padding:30px 30px 6px;"><h1 style="margin:0;font-size:23px;line-height:1.25;color:{OSCURO};">{titulo}</h1></td></tr>'
        f'<tr><td style="padding:14px 30px 10px;">{cuerpo}</td></tr>'
        f'{sig}'
        f'{extra}'
        f'<tr><td style="padding:18px 30px 8px;border-top:1px solid #eee;margin-top:10px;color:{TENUE};font-size:13px;line-height:1.6;">'
        f'{pie_linea}</td></tr>'
        f'<tr><td style="padding:2px 30px 26px;color:#b3b3b3;font-size:12px;">{PIE}</td></tr>'
        '</table></td></tr></table></body></html>')
