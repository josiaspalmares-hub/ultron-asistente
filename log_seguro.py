"""log_seguro.py - Enmascara tokens/claves en logging, print() y tracebacks."""
import atexit
import logging
import os
import re
import sys

_PATRONES = (
    re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}"),   # token de bot de Telegram (también dentro de .../bot<TOKEN>/metodo)
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),       # claves de Google / Gemini
)
_NOMBRES_SENSIBLES = ("TOKEN", "API_KEY", "SECRET", "PASSWORD", "MANIFEST_KEY")
_literales = set()


def registrar_secreto(valor) -> None:
    """Añade un valor exacto a enmascarar (por si no encaja con ningún patrón)."""
    valor = str(valor or "").strip().strip("'\"")
    if len(valor) >= 8:
        _literales.add(valor)


def _cargar_secretos_del_entorno() -> None:
    for nombre, valor in os.environ.items():
        if any(s in nombre.upper() for s in _NOMBRES_SENSIBLES):
            registrar_secreto(valor)


def redactar(texto) -> str:
    t = str(texto)
    for lit in sorted(_literales, key=len, reverse=True):
        t = t.replace(lit, "[SECRETO-OCULTO]")
    for patron in _PATRONES:
        t = patron.sub("[SECRETO-OCULTO]", t)
    return t


class FormateadorSeguro(logging.Formatter):
    """Redacta el mensaje ya formateado, incluidos los argumentos y el traceback de excepciones."""
    def format(self, record):
        return redactar(super().format(record))


class _FlujoSeguro:
    """Envuelve stdout/stderr: redacta por líneas completas (print, tracebacks no capturados)."""
    def __init__(self, destino):
        self._d = destino
        self._buf = ""

    def write(self, s):
        if isinstance(s, bytes):
            s = s.decode("utf-8", "replace")
        self._buf += s
        if "\n" in self._buf:
            completas, self._buf = self._buf.rsplit("\n", 1)
            self._d.write(redactar(completas) + "\n")
        return len(s)

    def writelines(self, lineas):
        for l in lineas:
            self.write(l)

    def flush(self):
        if self._buf:
            self._d.write(redactar(self._buf))
            self._buf = ""
        self._d.flush()

    def __getattr__(self, nombre):
        return getattr(self._d, nombre)


def instalar_log_seguro(nivel=logging.INFO) -> None:
    """Llamar UNA vez, al inicio, después de load_dotenv() y ANTES de logging.basicConfig()."""
    _cargar_secretos_del_entorno()
    fmt = FormateadorSeguro("%(asctime)s %(levelname)s %(name)s: %(message)s")

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    if not raiz.handlers:
        raiz.addHandler(logging.StreamHandler(sys.stderr))
    loggers = [raiz] + [l for l in logging.root.manager.loggerDict.values() if isinstance(l, logging.Logger)]
    for lg in loggers:
        for h in lg.handlers:
            h.setFormatter(fmt)

    # Estas librerías registran la URL completa (con el token) a nivel INFO/DEBUG.
    for nombre in ("httpx", "httpcore", "urllib3", "requests", "aiohttp.client"):
        logging.getLogger(nombre).setLevel(logging.WARNING)

    # Windows usa cp1252 cuando la salida no es una consola (archivo, ventana oculta): los emojis tumbarían a Ultron.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")

    if not isinstance(sys.stdout, _FlujoSeguro):
        sys.stdout = _FlujoSeguro(sys.stdout)
    if not isinstance(sys.stderr, _FlujoSeguro):
        sys.stderr = _FlujoSeguro(sys.stderr)
    atexit.register(lambda: (sys.stdout.flush(), sys.stderr.flush()))