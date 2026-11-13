import asyncio
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

from playwright.async_api import async_playwright

from seguridad_url import validar_url, resolver_destino
from proxy_seguro import iniciar_proxy_seguro

# Las capturas se guardan junto a main.py, en 'capturas/' (carpeta que tu .gitignore ya protege)
CARPETA_CAPTURAS = Path(__file__).resolve().parent / "capturas"
SALIDA = CARPETA_CAPTURAS / "render_web.png"

# Opcional (DESACTIVADO por defecto): permite inspeccionar archivos .html LOCALES, pero solo dentro de esta carpeta.
# Ejemplo: CARPETA_HTML_LOCAL = Path(__file__).resolve().parent / "inspeccion_local"
CARPETA_HTML_LOCAL = None

TIMEOUT_TOTAL_S = 60
TIMEOUT_NAVEGACION_MS = 25000
_validar = validar_url  # (url) -> (ok, motivo); es un punto de enganche para pruebas

# Un sitio no puede abrir WebSockets / EventSource / WebRTC hacia servicios locales (Playwright no los filtra por ruta)
_SCRIPT_BLOQUEO = """(() => { for (const n of ['WebSocket', 'EventSource', 'RTCPeerConnection', 'webkitRTCPeerConnection']) {
  try { Object.defineProperty(window, n, {value: undefined, configurable: false, writable: false}); } catch (e) {} } })();"""


def _dentro_de(ruta: Path, carpeta: Path) -> bool:
    try:
        ruta, carpeta = ruta.resolve(), carpeta.resolve()
        return carpeta in ruta.parents
    except Exception:
        return False


async def _capturar_render_web(url: str, salida: Path, carpeta_local=None):
    """Captura la página conectándose exclusivamente a través del proxy seguro."""
    loop = asyncio.get_running_loop()
    cache, bloqueados = {}, []

    async def permitido(u: str) -> bool:
        if u.startswith(("data:", "blob:")) or u == "about:blank":
            return True
        if u.startswith("file:"):
            return carpeta_local is not None and _dentro_de(Path(url2pathname(urlsplit(u).path)), carpeta_local)
        if not u.startswith(("http://", "https://")):
            return False
        p = urlsplit(u)
        clave = (p.scheme, p.hostname, p.port)
        if clave not in cache:  # una sola resolución DNS por host y captura
            cache[clave] = await loop.run_in_executor(None, lambda: _validar(u)[0])
        return cache[clave]

    def bloquear(u):
        bloqueados.append(u[:80])

    async def filtrar(route):
        u = route.request.url
        try:
            if not await permitido(u):
                bloquear(u)
                await route.abort("blockedbyclient")
                return
            await route.continue_()  # la red la gestiona el proxy seguro (IP validada y fijada en cada conexión)
        except Exception:
            bloquear(u)
            try:
                await route.abort("failed")
            except Exception:
                pass

    servidor_proxy, puerto_proxy = await iniciar_proxy_seguro(bloqueados)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            chromium_sandbox=True,
            args=["--disable-extensions", "--disable-background-networking", "--disable-quic", "--dns-prefetch-disable"],
            proxy={
                "server": f"http://127.0.0.1:{puerto_proxy}",
                "bypass": "<-loopback>"
            }
        )
        try:
            # Emular pantalla Desktop Full HD (sin descargas ni service workers)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                accept_downloads=False,
                service_workers="block"
            )
            await context.add_init_script(_SCRIPT_BLOQUEO)
            await context.route("**/*", filtrar)
            if hasattr(context, "route_web_socket"):  # Playwright >= 1.48: cierra cualquier WebSocket
                async def cerrar_ws(ws):
                    await ws.close(code=1008, reason="bloqueado por Ultron")
                await context.route_web_socket("**/*", cerrar_ws)
            page = await context.new_page()
            page.set_default_timeout(20000)
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_NAVEGACION_MS)
            if not await permitido(page.url):  # comprobación final tras posibles redirecciones
                raise RuntimeError("la página terminó en un destino no permitido")
            await page.wait_for_timeout(2000)  # Esperar a que carguen animaciones y estilos
            salida.parent.mkdir(parents=True, exist_ok=True)
            alto = int(await page.evaluate("Math.min(document.documentElement.scrollHeight, 12000)"))
            await page.screenshot(path=str(salida), full_page=True, clip={"x": 0, "y": 0, "width": 1920, "height": max(alto, 1080)})
        finally:
            await browser.close()
            servidor_proxy.close()
    return len(bloqueados)


def _inspeccionar(url: str, carpeta_local=None) -> str:
    try:
        n = asyncio.run(asyncio.wait_for(_capturar_render_web(url, SALIDA, carpeta_local), TIMEOUT_TOTAL_S))
        extra = f" ({n} recurso(s) bloqueado(s) por seguridad: redes privadas o destinos no permitidos)" if n else ""
        return f"Éxito: Render visual capturado en 'capturas/{SALIDA.name}'{extra}"
    except asyncio.TimeoutError:
        return f"Error en inspección visual web: la página tardó más de {TIMEOUT_TOTAL_S} s y se canceló."
    except Exception as e:
        return f"Error en inspección visual web: {str(e)[:300]}"


def inspeccionar_pagina_web(url_o_path: str) -> str:
    """Abre un sitio web PÚBLICO (http/https) con Chromium, toma una captura completa y la guarda en capturas/render_web.png.
    Bloquea localhost, IPs privadas, redes internas y esquemas como file://, javascript: o data:."""
    try:
        if not isinstance(url_o_path, str) or not url_o_path.strip():
            return "BLOQUEADO (seguridad): indica una URL o dominio público."
        texto = url_o_path.strip()

        # Archivos .html locales: solo si activaste CARPETA_HTML_LOCAL, y solo dentro de esa carpeta
        if "://" not in texto and texto.lower().endswith(".html"):
            if CARPETA_HTML_LOCAL is None:
                return "BLOQUEADO (seguridad): la inspección de archivos locales está desactivada."
            ruta = Path(texto).expanduser().resolve()
            if not ruta.is_file() or not _dentro_de(ruta, Path(CARPETA_HTML_LOCAL)):
                return "BLOQUEADO (seguridad): solo se pueden inspeccionar archivos .html dentro de la carpeta permitida."
            return _inspeccionar(ruta.as_uri(), Path(CARPETA_HTML_LOCAL))

        tipo, valor = resolver_destino(texto)
        if tipo != "url":
            motivo = valor if tipo == "bloqueado" else "no es una URL ni un dominio válido"
            print(f"[SEGURIDAD] Inspección web bloqueada: {repr(texto)[:80]} ({motivo})")
            return f"BLOQUEADO (seguridad): {motivo}. Solo se inspeccionan sitios web públicos con http/https."
        return _inspeccionar(valor)
    except Exception as e:
        return f"Error en inspección visual web: {e}"


if __name__ == "__main__":
    resultado = inspeccionar_pagina_web("https://apple.com")
    print(resultado)