# Reglas del proyecto

## ☁️ Sesiones en la nube — leer primero (09-oct-2026)

Estas reglas mandan sobre cualquier otra de este archivo cuando la sesión corre en la nube (Claude Code en
la web) y no en el Mac de Nicolás. Lo que dicen más abajo sobre «publicar SIEMPRE», `git publicar`,
`deploy.sh`, SSH, Chrome real o rutas `/Users/nicolas/...` vale solo en su Mac.

- **No publiques en `main`.** Trabaja en una rama (`claude/<tema>`), abre una solicitud de cambio (PR) y
  Nicolás la une. Un push a `main` puede desplegar a producción sin que nadie lo revise.
- **Sin SSH, sin claves y sin despliegues** (`deploy.sh`, `wrangler deploy`, FTP, copiar archivos al
  servidor). Nunca escribas ni repitas credenciales, ni en archivos ni en mensajes.
- **No toques datos de producción ni borres para siempre** sin un OK de Nicolás que nombre la acción.
- **Pruebas:** no hay Chrome real con su sesión. Prueba con Playwright y escribe en la solicitud de cambio
  «no probado en Chrome real». Nunca digas «listo» sin haber ejecutado el código o la calculadora.
- **Datos de prueba:** nombres genéricos («Prueba Interna»). Jamás las palabras «Claude», «IA» o «bot» en
  nada que pueda llegar a un cliente por WhatsApp, correo o SMS.
- **Idioma:** español chileno neutro con tuteo (tú). Nunca voseo argentino: ninguna forma verbal de segunda
  persona terminada en -ás, -és o -ís (usa tienes, puedes, quieres, haz, mira, escribe...). Evita los
  anglicismos poco populares: di «cliente», «etapa», «puntaje», «embudo», «seguimiento», «panel»,
  «oportunidad», «inasistencia». Excepciones: WhatsApp, GHL, BigCapital, UF, Nova, Gmail. Vale para el
  chat, la interfaz, los correos, los prompts y las plantillas.
- **Fechas** en palabras en textos y tablas («jueves 8 de octubre del 2026»); dd/mm/aaaa solo en campos
  para escribir.
- **Plata:** nunca `input type=number` (coma decimal); ejecuta la calculadora, no solo la leas.
