# Ultron · asistente personal para Windows

Asistente de escritorio con voz, hecho en Python sobre la API de Gemini. Habla, escucha, controla tareas de la PC y responde también por Telegram, con la seguridad como prioridad.

## Qué hace

- **Voz y HUD**: escucha órdenes por micrófono, responde hablando y muestra un panel con clima, CPU, RAM y GPU en vivo.
- **Bot de Telegram**: el mismo asistente desde el teléfono, solo para el ID de Telegram del dueño.
- **Memoria propia**: apuntes en Markdown con búsqueda por relevancia (BM25), respaldados en GitHub **cifrados**.
- **Herramientas**: diagnóstico de la PC, archivos en una carpeta de trabajo cerrada, consola con lista blanca de comandos, inspección de páginas web.
- **Habilidades firmadas**: solo carga instrucciones (.md) cuyo SHA-256 coincide con un manifiesto firmado con HMAC.
- **Rotación de claves y modelos** de Gemini cuando se agota la cuota gratis.

## Seguridad

- Consola con lista blanca y auto-reflexión: si un comando no está permitido, lo explica en vez de intentar saltarse la regla.
- Protección contra SSRF y DNS rebinding al abrir páginas (`seguridad_url.py`, `proxy_seguro.py`).
- Ping y auditorías de red solo hacia destinos permitidos (`politica_red.py`).
- Claves enmascaradas en logs, errores y tracebacks (`log_seguro.py`).
- 470 pruebas automáticas que no gastan cuota de Gemini.

## Correrlo

Probado con Python 3.12 en Windows.

```sh
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # y llena tus claves
.venv\Scripts\python main.py
```

Pruebas: `.venv\Scripts\python -m pip install -r requirements-dev.txt` y luego `.venv\Scripts\python -m pytest`.

> Las habilidades (`skills_seguras_ultron/`) y la memoria del dueño no vienen en este repositorio: son privadas.

**Tecnología:** Python · Google Gemini (google-genai) · pyTelegramBotAPI · pywebview · Playwright · cryptography · pytest
