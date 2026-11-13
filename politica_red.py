"""politica_red.py - Control estricto de destinos para ping y auditorías de red."""
import ipaddress
import os
import re
import socket
import threading
import time
from collections import deque
from seguridad_url import ip_publica, _con_limite

def _cargar_lan():
    redes = []
    # Ejemplo en .env: ULTRON_LAN_PERMITIDA="192.168.1.1,192.168.1.40/30"
    for t in os.environ.get("ULTRON_LAN_PERMITIDA", "").split(","):
        t = t.strip()
        if not t:
            continue
        try:
            r = ipaddress.ip_network(t, strict=False)
            if r.version == 4 and r.prefixlen >= 28:
                redes.append(r)
        except ValueError:
            pass
    return redes

_LAN = _cargar_lan()
_hist = deque()
_lock = threading.Lock()

def evaluar_objetivo(host: str):
    """Devuelve (ip_str, None) si el destino está permitido, o (None, motivo_error)."""
    host = (host or "").strip()
    if not host:
        return None, "destino vacío"
        
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"(?=.{1,253}$)([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}", host):
            return None, "formato de dominio o IP no válido"
        ok, ips = _con_limite(lambda h: sorted({i[4][0] for i in socket.getaddrinfo(h, None, socket.AF_INET)}), 5, host)
        if not ok or not ips:
            return None, "no se pudo resolver el dominio"
        if len(set(ips)) != 1 and not all(ip_publica(i) for i in ips):
            return None, "resolución de IP ambigua o mixta"
        ip = ipaddress.ip_address(ips[0])

    if ip.version != 4:
        return None, "solo se admite protocolo IPv4"

    if ip.is_loopback:
        pass  # 127.0.0.1 / localhost permitido
    elif ip_publica(str(ip)):
        pass  # IPs públicas de Internet permitidas
    elif not any(ip in r for r in _LAN):
        return None, "red privada no autorizada en ULTRON_LAN_PERMITIDA"

    with _lock:
        ahora = time.time()
        while _hist and ahora - _hist[0][0] > 600:
            _hist.popleft()
        if sum(1 for t, _ in _hist if ahora - t < 60) >= 6:
            return None, "límite superado: máximo 6 pings por minuto"
        
        privadas_distintas = {i for _, i in _hist if not ip_publica(i)}
        if not ip_publica(str(ip)):
            privadas_distintas.add(str(ip))
        if len(privadas_distintas) > 3:
            return None, "alerta de escaneo: demasiados destinos privados distintos"
            
        _hist.append((ahora, str(ip)))

    return str(ip), None