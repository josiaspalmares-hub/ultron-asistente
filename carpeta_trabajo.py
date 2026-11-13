"""carpeta_trabajo.py - Archivos de texto que Ultron crea y lee, encerrados en su carpeta de trabajo."""
import os
from pathlib import Path

CARPETA_TRABAJO = Path(os.getenv("ULTRON_CARPETA", "").strip()
                       or Path.home() / "Documents" / "Ultron_Trabajo").resolve()
_EXT_TEXTO = {".txt", ".md", ".csv", ".json", ".html", ".css", ".js", ".py", ".xml", ".yaml", ".yml", ".log"}
_MAX_BYTES = 1_000_000


def _ruta_trabajo(ruta: str) -> Path:
    """Resuelve 'ruta' dentro de la carpeta de trabajo; rechaza todo lo que salga de ella."""
    destino = (CARPETA_TRABAJO / (ruta or "").strip().lstrip("\\/")).resolve()
    if destino != CARPETA_TRABAJO and CARPETA_TRABAJO not in destino.parents:
        raise ValueError(f"solo puedo trabajar dentro de {CARPETA_TRABAJO}")
    return destino


def escribir_archivo(ruta: str, contenido: str, sobrescribir: bool = False) -> str:
    """Crea un archivo de texto (.txt, .md, .csv, .json, .html, .py...) dentro de la carpeta de trabajo de Ultron.
    'ruta' es relativa a esa carpeta y puede incluir subcarpetas (ej. 'goldhour/hawas_malibu.txt').
    Solo reemplaza un archivo existente si 'sobrescribir' es True."""
    try:
        destino = _ruta_trabajo(ruta)
        if destino.suffix.lower() not in _EXT_TEXTO:
            return f"BLOQUEADO: solo creo archivos de texto ({', '.join(sorted(_EXT_TEXTO))})."
        datos = (contenido or "").encode("utf-8")
        if len(datos) > _MAX_BYTES:
            return "BLOQUEADO: el contenido supera 1 MB."
        if destino.exists() and not sobrescribir:
            return f"Ya existe '{destino.relative_to(CARPETA_TRABAJO)}'. Pide permiso al usuario antes de reemplazarlo."
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
        return f"Archivo guardado en {destino}"
    except Exception as e:
        return f"Error al escribir el archivo: {e}"


def leer_archivo(ruta: str) -> str:
    """Lee un archivo de texto de la carpeta de trabajo de Ultron. 'ruta' es relativa a esa carpeta."""
    try:
        origen = _ruta_trabajo(ruta)
        if not origen.is_file():
            return f"No existe el archivo '{ruta}' en la carpeta de trabajo."
        if origen.suffix.lower() not in _EXT_TEXTO:
            return "BLOQUEADO: solo leo archivos de texto."
        texto = origen.read_text(encoding="utf-8", errors="replace")
        return texto[:20000] + ("\n[... recortado ...]" if len(texto) > 20000 else "")
    except Exception as e:
        return f"Error al leer el archivo: {e}"


def listar_carpeta_trabajo(subcarpeta: str = "") -> str:
    """Lista archivos y subcarpetas de la carpeta de trabajo de Ultron (o de una subcarpeta suya)."""
    try:
        carpeta = _ruta_trabajo(subcarpeta)
        CARPETA_TRABAJO.mkdir(parents=True, exist_ok=True)
        if not carpeta.is_dir():
            return f"No existe la carpeta '{subcarpeta}'."
        items = sorted(carpeta.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))[:200]
        if not items:
            return f"La carpeta {carpeta} está vacía."
        return f"Contenido de {carpeta}:\n" + "\n".join(
            f"[carpeta] {p.name}" if p.is_dir() else f"{p.name} ({p.stat().st_size} bytes)" for p in items)
    except Exception as e:
        return f"Error al listar la carpeta: {e}"
