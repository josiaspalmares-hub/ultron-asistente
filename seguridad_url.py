"""Validación de destinos web contra SSRF y esquemas peligrosos (compartida por main.py e inspeccion_web.py).

Solo se aceptan sitios web PÚBLICOS:
  · Esquema: únicamente http y https (se rechazan file:, javascript:, data:, ftp:, ws:, chrome:, view-source:, etc.).
  · Host: solo NOMBRES DE DOMINIO públicos con TLD real. Se rechazan TODAS las direcciones IP escritas en la URL (v4, v6,
    decimales, hexadecimales, octales, 127.1, [::1]...), 'localhost' y los sufijos internos (.local, .internal, .lan...).
  · DNS: el dominio se resuelve y TODAS sus direcciones deben ser públicas (bloquea 127.x, 10.x, 172.16-31.x, 192.168.x,
    169.254.x —incluida la IP de metadatos cloud—, 100.64.x, IPv6 locales, ::ffff:127.0.0.1, etc.). Esto también frena los
    dominios 'comodín' tipo nip.io que apuntan a IPs privadas.
  · Sin credenciales en la URL (user:pass@), sin barras invertidas ni caracteres de control, puertos solo 80 y 443.
Limitación conocida: entre esta comprobación y la conexión real, un atacante que controle el DNS podría cambiar la respuesta
('DNS rebinding'). Es un riesgo residual bajo; inspeccion_web.py además vuelve a validar cada petición del navegador.
"""
import ipaddress
import re
import socket
import threading
import urllib.parse

PUERTOS_PERMITIDOS = {None, 80, 443}
MAX_LARGO_URL = 2048
TLD_RESERVADOS = {"localhost", "local", "internal", "intranet", "lan", "home", "corp", "localdomain", "arpa", "invalid",
                  "test", "example", "onion", "private", "domain", "host", "router", "gateway"}
_RE_HOST = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9\-]{2,59})")
_RE_ESQUEMA_PELIGROSO = re.compile(
    r"^\s*(javascript|data|file|vbscript|blob|about|chrome|view-source|ftp|mailto|tel|ws|wss|gopher|jar|intent|ms-[a-z\-]+)\s*:", re.I)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_SITE_LOCAL = ipaddress.ip_network("fec0::/10")

def _resolver_dns(host):
    return sorted({i[4][0] for i in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})

def _con_limite(fn, segundos, *args):
    """Ejecuta fn en un hilo con límite de tiempo (getaddrinfo no tiene timeout propio). (ok, valor)."""
    res = {}

    def _t():
        try:
            res["v"] = fn(*args)
        except Exception as e:
            res["e"] = e
    h = threading.Thread(target=_t, daemon=True)
    h.start()
    h.join(segundos)
    return (True, res["v"]) if "v" in res else (False, None)

def ip_publica(texto) -> bool:
    """True solo si la dirección es de Internet público (no privada, local, reservada, multicast ni de traducción)."""
    try:
        ip = ipaddress.ip_address(str(texto).split("%")[0])
    except ValueError:
        return False
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped                                      # ::ffff:127.0.0.1 -> 127.0.0.1
        elif ip in _NAT64:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)         # 64:ff9b::7f00:1 -> 127.0.0.1
    if ip.version == 6 and ip in _SITE_LOCAL:
        return False
    return bool(ip.is_global and not ip.is_multicast)

def validar_url(url, resolver=None):
    """Devuelve (True, url_normalizada) o (False, motivo). 'resolver' (host -> lista de IPs) permite pruebas sin red."""
    if not isinstance(url, str):
        return False, "la URL debe ser texto"
    url = url.strip()
    if not url or len(url) > MAX_LARGO_URL:
        return False, "URL vacía o demasiado larga"
    if re.search(r"[\s\x00-\x1f\x7f\\]", url):
        return False, "la URL contiene espacios, caracteres de control o barras invertidas"
    try:
        p = urllib.parse.urlsplit(url)
        puerto = p.port
    except ValueError:
        return False, "URL mal formada"
    if p.scheme.lower() not in ("http", "https"):
        return False, f"esquema no permitido ('{p.scheme[:20]}'): solo http y https"
    if "@" in p.netloc:
        return False, "no se permiten credenciales dentro de la URL"
    if puerto not in PUERTOS_PERMITIDOS:
        return False, f"puerto no permitido ({puerto}): solo 80 y 443"
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        return False, "la URL no tiene dominio"
    try:
        host = host.encode("idna").decode("ascii")                   # dominios internacionales -> punycode
    except UnicodeError:
        return False, "dominio con caracteres no válidos"
    if not _RE_HOST.fullmatch(host):
        return False, "solo se permiten dominios públicos (no direcciones IP, 'localhost' ni nombres sin dominio real)"
    if host.rsplit(".", 1)[1] in TLD_RESERVADOS:
        return False, "dominio de red interna o reservado"
    ok, ips = _con_limite(resolver or _resolver_dns, 5, host)
    if not ok or not ips:
        return False, "el dominio no se pudo resolver"
    if any(not ip_publica(ip) for ip in ips):
        return False, "el dominio resuelve a una dirección privada, local o reservada (red interna)"
    limpia = urllib.parse.urlunsplit((p.scheme.lower(), host + (f":{puerto}" if puerto else ""), p.path or "/", p.query, ""))
    return True, limpia

def resolver_destino(texto, resolver=None):
    """Interpreta lo que pide el usuario. Devuelve ('url', url_segura) | ('busqueda', url_de_google) | ('bloqueado', motivo)."""
    if not isinstance(texto, str) or not texto.strip():
        return "bloqueado", "destino vacío"
    t = texto.strip()
    if _RE_ESQUEMA_PELIGROSO.match(t):
        return "bloqueado", f"esquema no permitido ('{t.split(':')[0][:20]}'): solo http y https"
    if "://" in t or t.startswith("//"):
        ok, r = validar_url(("https:" + t) if t.startswith("//") else t, resolver)
        return ("url", r) if ok else ("bloqueado", r)
    if "." in t and not re.search(r"\s", t):                         # parece un dominio: "ejemplo.com/ruta"
        ok, r = validar_url("https://" + t, resolver)
        return ("url", r) if ok else ("bloqueado", r)
    return "busqueda", "https://www.google.com/search?q=" + urllib.parse.quote_plus(t[:300])