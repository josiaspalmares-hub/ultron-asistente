"""Ejecución de comandos de consola con LISTA BLANCA estricta y AUTO-REFLEXIÓN agéntica.

Seguridad (anti-inyección de comandos):
  · Solo se ejecutan comandos de DIAGNÓSTICO incluidos en COMANDOS (lista blanca). Cualquier otro se rechaza.
  · Se bloquean el encadenado (& | ;), la redirección (< >), la expansión de variables (% $ ^ ! `) y los saltos de línea.
  · Nunca se usa shell=True: el comando se ejecuta como lista de argumentos (cmd /c solo para los internos de cmd.exe,
    con todos sus argumentos ya validados).
  · Los argumentos de cada comando se validan uno a uno (p. ej. 'ipconfig' solo admite /all; 'ping' solo -4, -6, -n 1..10).
  · No existe ningún parámetro con el que el modelo pueda saltarse la lista (se eliminó 'confirmado').

Auto-reflexión: si un comando permitido falla (código de retorno distinto de 0 o tiempo agotado), la IA recibe el comando,
el código de retorno, stdout y stderr, analiza la causa y propone una corrección, que pasa por la MISMA validación y se
reintenta de forma autónoma (máx. MAX_REINTENTOS veces), siempre con límites de tiempo.
"""
import ipaddress
import json
import os
import re
import shlex
import subprocess
import time

from utilidades import con_timeout

MAX_REINTENTOS = 2
TIMEOUT_COMANDO_S = 20
TIMEOUT_REFLEXION_S = 25
PRESUPUESTO_TOTAL_S = 80
MAX_LARGO_COMANDO = 300
MAX_ARGUMENTOS = 12
_reflexionar = None          # callable(prompt: str) -> str ; lo inyecta main.py con una consulta aislada a Gemini
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# Caracteres que permiten encadenar, redirigir o expandir: se rechazan en cualquier parte del comando
_RE_PROHIBIDOS = re.compile(r"[&|;<>^%$`!\r\n\x00]")
# Un argumento solo puede tener letras, números y estos signos (rutas, flags y hosts)
_RE_ARGUMENTO = re.compile(r"[\w\-./\\:@*?,=+ ()~#]{1,200}")


def _host_valido(h):
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return bool(re.fullmatch(r"(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?", h or ""))


# ── Validadores de argumentos (devuelven None si todo está bien, o el motivo del rechazo) ─────────────
def _libre(args):
    return None


def _nada(args):
    return None if not args else "este comando no admite argumentos"


def _solo(*permitidos):
    ok = {p.lower() for p in permitidos}

    def validar(args):
        malo = next((a for a in args if a.lower() not in ok), None)
        return None if malo is None else f"argumento no permitido '{malo}' (admitidos: {', '.join(sorted(ok))})"
    return validar


def _un_host(args):
    return None if len(args) == 1 and _host_valido(args[0]) else "se requiere exactamente un host o IP válido"


def _val_ping(args):
    i = 0
    while i < len(args) - 1:
        if args[i] in ("-4", "-6"):
            i += 1
        elif args[i] == "-n" and i + 1 < len(args) - 1 and args[i + 1].isdigit() and 1 <= int(args[i + 1]) <= 10:
            i += 2
        else:
            return "ping solo admite -4, -6, -n <1-10> y un host"
    return None if args and _host_valido(args[-1]) else "host no válido"


_GIT_SUBCOMANDOS = {"status", "log", "branch"}
_GIT_ARGS = {"--oneline", "--short", "-s", "-b", "--stat", "--graph", "--decorate", "-a", "-v"}


def _val_git(args):
    if not args or args[0] not in _GIT_SUBCOMANDOS:
        return f"git solo admite: {', '.join(sorted(_GIT_SUBCOMANDOS))}"
    malo = next((a for a in args[1:] if a not in _GIT_ARGS and not re.fullmatch(r"-\d{1,3}", a)), None)
    return None if malo is None else f"argumento de git no permitido '{malo}'"


# nombre -> (tipo, validador). 'cmd' = comando interno de cmd.exe; 'exe' = ejecutable independiente.
COMANDOS = {
    "dir": ("cmd", _libre), "echo": ("cmd", _libre), "ver": ("cmd", _nada), "vol": ("cmd", _libre),
    "ipconfig": ("exe", _solo("/all")), "ping": ("exe", _val_ping), "nslookup": ("exe", _un_host),
    "tracert": ("exe", _un_host), "tasklist": ("exe", _solo("/svc", "/v")), "whoami": ("exe", _solo("/all", "/groups")),
    "hostname": ("exe", _nada), "systeminfo": ("exe", _nada), "getmac": ("exe", _solo("/v")),
    "netstat": ("exe", _solo("-a", "-n", "-o", "-an", "-ano", "-e", "-s", "-r")), "git": ("exe", _val_git),
}


def _argv(nombre, tipo, args):
    """Lista de argumentos para subprocess (sin shell)."""
    return ["cmd", "/c", nombre, *args] if tipo == "cmd" else [nombre, *args]


def validar(comando):
    """Devuelve (argv, None) si el comando está permitido, o (None, motivo_del_rechazo)."""
    if not isinstance(comando, str) or not comando.strip():
        return None, "comando vacío"
    if len(comando) > MAX_LARGO_COMANDO:
        return None, f"comando demasiado largo (máx. {MAX_LARGO_COMANDO} caracteres)"
    if _RE_PROHIBIDOS.search(comando):
        return None, "contiene caracteres de encadenado, redirección o expansión (& | ; < > ^ % $ ` !) o saltos de línea"
    try:
        partes = shlex.split(comando.strip(), posix=False)
    except ValueError:
        return None, "comillas sin cerrar"
    tokens = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in partes]
    if not tokens or len(tokens) > MAX_ARGUMENTOS + 1:
        return None, f"demasiados argumentos (máx. {MAX_ARGUMENTOS})"
    for t in tokens:
        if not _RE_ARGUMENTO.fullmatch(t):
            return None, f"argumento con caracteres no permitidos: {t[:40]!r}"
    nombre = tokens[0].lower()
    if nombre.endswith(".exe"):
        nombre = nombre[:-4]
    if nombre not in COMANDOS:
        return None, f"'{tokens[0]}' no está en la lista blanca"
    tipo, validador = COMANDOS[nombre]
    error = validador(tokens[1:])
    if error:
        return None, error
    return _argv(nombre, tipo, tokens[1:]), None


def configurar(reflexionar):
    """Inyecta la función que consulta a la IA (prompt -> texto). Sin ella solo se devuelve el diagnóstico estructurado."""
    global _reflexionar
    _reflexionar = reflexionar


def _ejecutar(argv, timeout=None):
    timeout = TIMEOUT_COMANDO_S if timeout is None else timeout      # se lee al ejecutar: la constante es configurable
    t0 = time.time()
    try:
        r = subprocess.run(argv, shell=False, capture_output=True, text=True, errors="replace", timeout=timeout,
                           encoding="oem" if os.name == "nt" else "utf-8", creationflags=_NO_WINDOW)
        return {"rc": r.returncode, "out": (r.stdout or "").strip(), "err": (r.stderr or "").strip(),
                "timeout": False, "seg": time.time() - t0}
    except subprocess.TimeoutExpired as e:
        txt = lambda b: (b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")).strip()
        return {"rc": None, "out": txt(e.stdout), "err": f"Tiempo agotado tras {timeout} s", "timeout": True, "seg": timeout}
    except Exception as e:
        return {"rc": -1, "out": "", "err": f"No se pudo ejecutar: {e}", "timeout": False, "seg": time.time() - t0}


def _ok(r):
    return r["rc"] == 0 and not r["timeout"]


def _recorte(t, n=700):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…(recortado)"


def _parsear_json(texto):
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return {}
    bruto = m.group(0)
    for candidato in (bruto, re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", bruto)):       # 2.º intento: rutas de Windows sin escapar (C:\x)
        try:
            return json.loads(candidato)
        except Exception:
            continue
    return {}


def _analizar(comando, r, objetivo, intentos):
    """Pide a la IA el análisis del fallo. Devuelve dict(causa, comando_corregido, desistir) o {}."""
    if _reflexionar is None:
        return {}
    previos = "\n".join(f"- {c}" for c, _ in intentos)
    prompt = (
        "Eres un ingeniero experto en Windows (CMD). Un comando falló y debes corregirlo.\n"
        f"Objetivo del usuario: {objetivo or '(no indicado)'}\n"
        f"Comando ejecutado: {comando}\n"
        f"Código de retorno: {r['rc']}{' (TIEMPO AGOTADO)' if r['timeout'] else ''}\n"
        f"Salida estándar: {_recorte(r['out'])}\nError estándar: {_recorte(r['err'])}\n"
        f"Comandos ya intentados:\n{previos}\n\n"
        f"Solo está permitido usar estos comandos: {', '.join(sorted(COMANDOS))}. Sin encadenar (& | ;), sin redirigir (< >) "
        "y sin variables (% $). Analiza la causa real del fallo (ruta, argumento, sintaxis, host...). "
        'Responde SOLO un JSON: {"causa": "explicación breve en español", "comando_corregido": "un único comando '
        'permitido y distinto a los ya intentados", "desistir": false}. Pon "desistir": true y comando_corregido vacío si el '
        "fallo no se puede resolver con otro comando permitido."
    )
    ok, v = con_timeout(_reflexionar, TIMEOUT_REFLEXION_S, prompt)
    return _parsear_json(v) if ok and v else {"causa": f"(la IA no pudo analizar el fallo: {v})"}


def ejecutar_comando_terminal(comando: str, objetivo: str = "") -> str:
    """Ejecuta un comando de DIAGNÓSTICO de Windows desde una lista blanca: dir, echo, ver, vol, ipconfig /all,
    ping, nslookup, tracert, tasklist, whoami, hostname, systeminfo, getmac, netstat y git status/log/branch.
    No admite encadenar (& | ;), redirigir (< >) ni variables (% $). Si falla, el sistema analiza el error con la IA y
    reintenta con un comando corregido (hasta 2 veces) antes de responder.
    comando: un único comando permitido. objetivo: qué se quiere lograr (mejora la corrección automática)."""
    inicio = time.time()
    argv, motivo = validar(comando)
    if argv is None:
        return (f"BLOQUEADO: {motivo}. Solo se permiten comandos de diagnóstico de la lista blanca: "
                f"{', '.join(sorted(COMANDOS))}. No se permite encadenar, redirigir ni expandir variables. "
                "Informa al Sr. Josias; no intentes eludir esta restricción.")
    intentos, actual = [], comando
    for n in range(1, MAX_REINTENTOS + 2):
        r = _ejecutar(argv)
        intentos.append((actual, r))
        if _ok(r):
            cuerpo = _recorte(r["out"] or r["err"] or "Comando ejecutado sin salida.", 1500)
            if n == 1:
                return f"Consola (código 0):\n{cuerpo}"
            return f"ÉXITO tras corregir el comando automáticamente ({n} intentos). Comando final: {actual}\n{cuerpo}"
        if n > MAX_REINTENTOS or time.time() - inicio > PRESUPUESTO_TOTAL_S:
            break
        analisis = _analizar(actual, r, objetivo, intentos)
        intentos[-1] = (actual, dict(r, analisis=analisis.get("causa", "")))
        nuevo = (analisis.get("comando_corregido") or "").strip()
        if analisis.get("desistir") or not nuevo or nuevo in [c for c, _ in intentos]:
            break
        nuevo_argv, motivo = validar(nuevo)          # la corrección pasa por la MISMA lista blanca
        if nuevo_argv is None:
            intentos[-1][1]["analisis"] += f" (la corrección propuesta '{nuevo[:60]}' fue rechazada por la lista blanca: {motivo})"
            break
        actual, argv = nuevo, nuevo_argv
    lineas = []
    for i, (c, r) in enumerate(intentos, 1):
        estado = "tiempo agotado" if r["timeout"] else f"código {r['rc']}"
        lineas.append(f"{i}) {c}  ->  {estado}. Error: {_recorte(r['err'] or r['out'], 300)}")
        if r.get("analisis"):
            lineas.append(f"   Análisis: {r['analisis']}")
    return (f"FALLÓ tras {len(intentos)} intento(s) automático(s).\n" + "\n".join(lineas) +
            "\nINSTRUCCIÓN: explica al Sr. Josias la causa con claridad. Solo reintenta si tienes una estrategia "
            "realmente distinta a los intentos anteriores.")