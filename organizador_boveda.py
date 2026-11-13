import os
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime

_LOCK = threading.Lock()
MAX_BYTES_DIARIO = 200_000   # de cada diario solo se lee el final
MAX_CHARS_WIKI = 15_000      # tamaño total de la wiki: se conserva lo MÁS RECIENTE


def _neutralizar_encabezados(texto: str) -> str:
    # Evita que una línea del diario imite '### Registro:' u otros encabezados de la wiki
    return "\n".join(("\\" + l) if l.lstrip().startswith("#") else l for l in texto.splitlines())


def organizar_boveda_memoria() -> str:
    """Analiza los registros diarios en 'boveda/raw' y los consolida organizadamente en 'boveda/wiki'."""
    if not _LOCK.acquire(blocking=False):
        return "Ya hay una organización de la bóveda en curso."
    tmp = None
    try:
        carpeta_raw = Path("boveda/raw")
        carpeta_wiki = Path("boveda/wiki")
        carpeta_wiki.mkdir(parents=True, exist_ok=True)

        if not carpeta_raw.is_dir():
            return "No hay carpeta 'boveda/raw' para procesar."

        archivos = [a for a in sorted(carpeta_raw.glob("diario_*.md")) if a.is_file() and not a.is_symlink()]
        if not archivos:
            return "No se encontraron diarios en 'boveda/raw'."

        bloques, total = [], 0
        for diario in reversed(archivos):                       # del más nuevo al más viejo
            try:
                with open(diario, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    f.seek(max(0, f.tell() - MAX_BYTES_DIARIO))
                    texto = _neutralizar_encabezados(f.read().decode("utf-8", errors="replace").strip())
            except Exception as e:
                print(f"Error leyendo {diario.name}: {e}")
                continue
            if not texto:
                continue
            bloque = f"### Registro: {diario.name}\n{texto}\n"
            if total + len(bloque) > MAX_CHARS_WIKI:
                resto = MAX_CHARS_WIKI - total - 60
                if resto > 200:                                  # lo que quepa del final (lo más reciente) de este diario
                    bloques.append(f"### Registro: {diario.name} (parcial)\n{texto[-resto:]}\n")
                break
            bloques.append(bloque)
            total += len(bloque)

        if not bloques:
            return "Los diarios de la bóveda están vacíos."
        bloques.reverse()                                        # orden cronológico

        archivo_wiki = carpeta_wiki / "conocimiento_general.md"
        encabezado = (f"# BASE DE CONOCIMIENTO DE ULTRON\n"
                      f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Escritura atómica: nadie lee nunca un archivo a medias
        fd, tmp = tempfile.mkstemp(dir=carpeta_wiki, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(encabezado + "\n".join(bloques))
        for intento in range(3):                                 # en Windows, replace falla si alguien lo tiene abierto
            try:
                os.replace(tmp, archivo_wiki)
                tmp = None
                break
            except PermissionError:
                time.sleep(0.2)
        else:
            return "Error al organizar la bóveda: el archivo está en uso; inténtalo de nuevo."

        return f"Éxito: Bóveda organizada. Se procesaron {len(archivos)} diario(s) en '{archivo_wiki.name}'."

    except Exception as e:
        return f"Error al organizar la bóveda: {e}"
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        _LOCK.release()


if __name__ == "__main__":
    print(organizar_boveda_memoria())