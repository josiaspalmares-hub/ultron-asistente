"""proxy_seguro.py - Proxy local que cierra el 'DNS rebinding' de inspeccion_web.py.

Chromium sale a Internet SOLO a través de este proxy. Por cada conexión (la página, cada redirección, imágenes, scripts...):
  1) resuelve el dominio UNA sola vez,
  2) valida el dominio y TODAS las IPs con seguridad_url (solo dominios públicos / IPs públicas, solo puertos 80 y 443),
  3) conecta a esa IP ya validada (nunca vuelve a resolver el nombre) y deja pasar los bytes (TLS de extremo a extremo).
Así no hay ventana entre 'comprobar' y 'conectar': un dominio que cambia su DNS a 127.0.0.1 no llega a conectarse.
"""
import asyncio
import re
import socket
from urllib.parse import urlsplit

from seguridad_url import validar_url

PUERTOS = {80, 443}
_RE_HOST = re.compile(r"[A-Za-z0-9.\-]{1,253}")
_METODOS_HTTP = {"GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"}
_CABECERAS_PROXY = (b"proxy-connection", b"connection", b"keep-alive", b"proxy-authorization", b"upgrade")
TIMEOUT_CABECERA_S = 15
TIMEOUT_CONEXION_S = 10
MAX_CONEXIONES = 64
_R403 = b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
_R400 = b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
_R502 = b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"


async def _resolver_y_validar(host, puerto, resolver_dns):
    """Devuelve la lista de IPs (todas públicas) o [] si el destino no está permitido."""
    if puerto not in PUERTOS or not _RE_HOST.fullmatch(host):
        return []
    try:
        infos = await asyncio.wait_for(resolver_dns(host, puerto), 5)
    except Exception:
        return []
    ips = sorted({i[4][0] for i in infos})
    ok, _ = validar_url(f"https://{host}", resolver=lambda h: ips)   # reglas de dominio + todas las IPs públicas
    return ips if ok else []


async def _abrir(ips, puerto):
    ultimo = None
    for ip in ips:                                   # IP literal: asyncio no vuelve a resolver nada
        try:
            return await asyncio.wait_for(asyncio.open_connection(ip, puerto), TIMEOUT_CONEXION_S)
        except Exception as e:
            ultimo = e
    raise ultimo or OSError("sin destino")


async def _tuberia(origen, destino):
    try:
        while True:
            datos = await origen.read(65536)
            if not datos:
                break
            destino.write(datos)
            await destino.drain()
    except Exception:
        pass
    finally:
        try:
            destino.close()
        except Exception:
            pass


async def _responder(cw, datos):
    try:
        cw.write(datos)
        await cw.drain()
    except Exception:
        pass
    finally:
        cw.close()


async def _manejar(cr, cw, bloqueados, resolver_dns, limite):
    async with limite:
        try:
            cabecera = await asyncio.wait_for(cr.readuntil(b"\r\n\r\n"), TIMEOUT_CABECERA_S)
            linea, *cabeceras = cabecera[:-4].split(b"\r\n")
            metodo, objetivo, version = linea.decode("latin-1").split(" ", 2)
            metodo = metodo.upper()
            if metodo == "CONNECT":
                host, _, p = objetivo.rpartition(":")
                puerto, tls, ruta = (int(p) if p.isdigit() else 0), True, ""
            else:
                u = urlsplit(objetivo)
                if metodo not in _METODOS_HTTP or u.scheme != "http" or not u.hostname:
                    return await _responder(cw, _R400)
                host, puerto, tls = u.hostname, (u.port or 80), False
                ruta = (u.path or "/") + (("?" + u.query) if u.query else "")
        except Exception:
            return await _responder(cw, _R400)

        ips = await _resolver_y_validar(host.lower(), puerto, resolver_dns)
        if not ips:
            bloqueados.append(f"{host}:{puerto}"[:80])
            return await _responder(cw, _R403)
        try:
            sr, sw = await _abrir(ips, puerto)
        except Exception:
            return await _responder(cw, _R502)

        if tls:
            cw.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            # Forma de origen + 'Connection: close' (una petición por conexión, sin reutilizar el túnel)
            filtradas = [c for c in cabeceras if c.split(b":", 1)[0].strip().lower() not in _CABECERAS_PROXY]
            sw.write(f"{metodo} {ruta} {version}\r\n".encode("latin-1")
                     + b"\r\n".join(filtradas + [b"Connection: close"]) + b"\r\n\r\n")
        await asyncio.gather(_tuberia(cr, sw), _tuberia(sr, cw))


async def iniciar_proxy_seguro(bloqueados, resolver_dns=None):
    """Arranca el proxy en 127.0.0.1 (puerto aleatorio). Devuelve (servidor, puerto)."""
    loop = asyncio.get_running_loop()
    resolver_dns = resolver_dns or (lambda h, p: loop.getaddrinfo(h, p, type=socket.SOCK_STREAM))
    limite = asyncio.Semaphore(MAX_CONEXIONES)
    servidor = await asyncio.start_server(lambda r, w: _manejar(r, w, bloqueados, resolver_dns, limite), "127.0.0.1", 0)
    return servidor, servidor.sockets[0].getsockname()[1]