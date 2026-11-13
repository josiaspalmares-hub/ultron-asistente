"""utilidades.py - Funciones pequeñas que comparten main.py, agente_shell.py y boveda_rag.py."""
import threading
import time
import unicodedata


def norm(t) -> str:
    """Minúsculas y sin acentos, conservando la longitud."""
    return "".join(unicodedata.normalize("NFD", c)[0] for c in str(t)).lower()


_avisados = set()


def avisar_una_vez(clave, mensaje, log=print):
    """Registra un fallo repetitivo (bucles de sondeo) solo la primera vez para no inundar la consola."""
    if clave not in _avisados:
        _avisados.add(clave)
        log(mensaje)


def con_timeout(fn, timeout, *args):
    """Ejecuta fn(*args) en un hilo con tope de tiempo. Devuelve (ok, valor o mensaje de error)."""
    res = {}

    def _t():
        try:
            res["v"] = fn(*args)
        except Exception as e:
            res["e"] = e
    h = threading.Thread(target=_t, daemon=True)
    h.start()
    h.join(timeout)
    if h.is_alive():
        return False, f"tardó más de {timeout} s (sigue ejecutándose en segundo plano)"
    if "e" in res:
        return False, f"{type(res['e']).__name__}: {res['e']}"
    return True, res.get("v")


def lanzar_supervisado(nombre, fn, log=print, espera_s=5.0, max_espera_s=300.0):
    """Corre fn en un hilo de fondo y la relanza si se cae, esperando cada vez más (hasta max_espera_s).
    Si fn termina sin error, el hilo termina."""
    def _supervisor():
        espera = espera_s
        while True:
            try:
                fn()
                return
            except Exception as e:
                log(f"[{nombre}] se detuvo por {type(e).__name__}: {e}. Reintento en {espera:.0f} s")
                time.sleep(espera)
                espera = min(espera * 2, max_espera_s)
    hilo = threading.Thread(target=_supervisor, name=nombre, daemon=True)
    hilo.start()
    return hilo
