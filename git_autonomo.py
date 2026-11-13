import os
import re
import subprocess
from datetime import datetime
import threading

from respaldo_boveda import cifrar_boveda

# Patrón ampliado: reconoce assignments (=) y pares clave-valor (:) con o sin comillas
_PATRON_SECRETO_AMPLIO = re.compile(
    r'(?i)(api[_-]?key|token|secret|password|passwd|clave|credential)\w*["\']?\s*[:=]\s*["\'][A-Za-z0-9_\-:./+]{16,}["\']'
)

def contiene_secretos_locales(texto: str) -> bool:
    """Detecta claves sensibles tanto en formato archivo .env (llave=valor) 
    como en pares JSON, YAML o diccionarios ('llave': 'valor')."""
    if not isinstance(texto, str):
        return False
    return bool(_PATRON_SECRETO_AMPLIO.search(texto))

# Rutas que JAMÁS deben subirse al repositorio. El respaldo se CANCELA si el .gitignore no las protege.
PROTEGIDOS = (".env", "capturas/", "boveda/", "logs/", "cache_voz/")
# Lo único que se respalda (por extensión). Capturas, audios, logs, etc. quedan fuera aunque no estén ignorados.
RESPALDAR = (".gitignore", "*.py", "*.html", "*.md", "*.txt", "*.json", "respaldo/boveda.enc")

_RX_ARCHIVOS_PROHIBIDOS = re.compile(r"(^|/)(\.env(\..*)?|id_rsa.*|.*\.(pem|key|pfx|p12|pkl))$", re.I)
_RX_SECRETOS = [re.compile(p) for p in (
    r"\d{8,10}:[A-Za-z0-9_\-]{30,}",                                        # token de bot de Telegram
    r"AIza[0-9A-Za-z_\-]{35}",                                              # API key de Google / Gemini
    r"\bsk-[A-Za-z0-9]{20,}", r"\bhf_[A-Za-z0-9]{30,}",                     # OpenAI / HuggingFace
    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"""(?i)(api[_-]?key|token|secret|passw(or)?d)\w*\s*=\s*['"][A-Za-z0-9_\-:./+]{16,}['"]""")]
_ENTORNO = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}          # git nunca se queda esperando credenciales en segundo plano

_GIT_LOCK = threading.Lock()


def _git(*args, timeout=30, check=False):
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout, check=check,
                          env=_ENTORNO, encoding="utf-8", errors="replace")


def _archivos_con_secretos():
    """Revisa lo que está en el área de preparación (staging). Devuelve SOLO nombres de archivo, nunca el secreto."""
    nombres = [n for n in _git("diff", "--cached", "--name-only", timeout=60).stdout.splitlines() if n.strip()]
    hallados = [n for n in nombres if _RX_ARCHIVOS_PROHIBIDOS.search(n)]
    archivo = None
    for linea in _git("diff", "--cached", "-U0", "--no-color", timeout=60).stdout.splitlines():
        if linea.startswith("+++ b/"):
            archivo = linea[6:]
        elif linea.startswith("+") and not linea.startswith("+++") and archivo and archivo not in hallados:
            if any(rx.search(linea) for rx in _RX_SECRETOS):
                hallados.append(archivo)
    return hallados


def _ejecutar_git_autonomo_interno(mensaje_commit: str = "") -> str:
    """Ejecuta git add (selectivo), git commit y opcionalmente git push si existe un repositorio remoto.
    Se cancela si el .gitignore no protege los secretos o si se detecta un secreto en los cambios."""
    try:
        # 0. ¿Estamos dentro de un repositorio?
        if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return "Error: esta carpeta no es un repositorio Git."

        # 1. Ninguna ruta protegida puede estar ya rastreada por Git (si lo está, .gitignore no sirve de nada)
        rastreados = _git("ls-files", "--", *[p.rstrip("/") for p in PROTEGIDOS]).stdout.split()
        if rastreados:
            return (f"Respaldo CANCELADO (seguridad): Git ya rastrea {len(rastreados)} archivo(s) protegido(s) "
                    f"(p. ej. '{rastreados[0]}'). Ejecuta: git rm -r --cached <ruta> y vuelve a intentarlo.")

        # 2. El .gitignore debe proteger los secretos y los datos privados (lo comprueba el propio Git)
        desprotegidos = [p for p in PROTEGIDOS if _git("check-ignore", "-q", "--", p).returncode != 0]
        if desprotegidos:
            return ("Respaldo CANCELADO (seguridad): tu .gitignore no protege: " + ", ".join(desprotegidos) +
                    ". Añádelos a .gitignore y vuelve a intentarlo.")

        # 3. La bóveda viaja solo cifrada (respaldo/boveda.enc); si no hay clave, se respalda el resto igual
        estado_boveda = cifrar_boveda()
        print(estado_boveda)

        # ¿Hay cambios pendientes?
        if not _git("status", "--porcelain").stdout.strip():
            return "Git: No hay cambios pendientes para respaldar."

        # 4. Preparar SOLO lo respaldable (nunca 'git add .')
        _git("add", "-u", check=True)
        for patron in RESPALDAR:
            _git("add", "--", patron)            # uno por uno: si un patrón no coincide con nada, Git devuelve 128 y se ignora
        if _git("diff", "--cached", "--quiet").returncode == 0:
            return "Git: No hay cambios respaldables (los archivos pendientes están fuera de la lista de respaldo)."

        # 5. Antes de confirmar: ningún secreto en lo preparado
        secretos = _archivos_con_secretos()
        if secretos:
            _git("reset", "-q")                                     # deja todo sin preparar
            return ("Respaldo CANCELADO (seguridad): posible secreto o archivo sensible en: " + ", ".join(secretos[:5]) +
                    ". Quítalo del código (usa .env) y vuelve a intentarlo.")

        # 6. Mensaje de commit (sin caracteres de control, longitud acotada)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base = re.sub(r"[\x00-\x1f\x7f]+", " ", mensaje_commit or "").strip()[:200]
        mensaje_commit = f"{base} ({timestamp})" if base else f"Actualización autónoma de Ultron ({timestamp})"

        # 7. Crear commit local
        _git("commit", "-m", mensaje_commit, check=True, timeout=60)

        # 8. Verificar si existe servidor remoto (GitHub)
        if _git("remote").stdout.strip():
            push_res = _git("push", timeout=60)
            if push_res.returncode == 0:
                return f"Éxito: Cambios respaldados localmente y subidos a GitHub ('{mensaje_commit}')."
            return f"Éxito: Respaldo local realizado ('{mensaje_commit}'). Sin conexión remota."
        return f"Éxito: Respaldo local completado con éxito. Commit: '{mensaje_commit}'."

    except FileNotFoundError:
        return "Error: Git no está instalado o no se encuentra en las variables de entorno."
    except subprocess.TimeoutExpired:
        return "Error: Git tardó demasiado en responder; la operación se canceló."
    except subprocess.CalledProcessError as e:
        return f"Error en comandos de Git: {e}"
    except Exception as e:
        return f"Error en Git autónomo: {e}"


def ejecutar_git_autonomo(mensaje_commit: str = "") -> str:
    """Respalda el código en Git (selectivo, con revisión de secretos). Solo un respaldo a la vez."""
    if not _GIT_LOCK.acquire(blocking=False):
        return "Git: ya hay un respaldo en curso; inténtalo en unos segundos."
    try:
        return _ejecutar_git_autonomo_interno(mensaje_commit)
    finally:
        _GIT_LOCK.release()


if __name__ == "__main__":
    print(ejecutar_git_autonomo())