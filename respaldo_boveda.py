"""respaldo_boveda.py - Copia cifrada de boveda/ para poder subirla a GitHub sin exponer la memoria de Ultron.

La bóveda nunca va a git en claro (.gitignore). Este módulo la empaqueta en un zip, la cifra con Fernet (AES + HMAC)
usando ULTRON_BOVEDA_KEY del .env y la deja en respaldo/boveda.enc, que sí se respalda.
Sin esa clave el archivo no se puede abrir: guárdala también fuera de esta PC.

Uso:
    python respaldo_boveda.py                    cifra la bóveda (crea la clave en .env si no existe)
    python respaldo_boveda.py --restaurar        descifra respaldo/boveda.enc en boveda_restaurada/
"""
import hashlib
import io
import os
import sys
import zipfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
BOVEDA = BASE / "boveda"
ARCHIVO_CIFRADO = BASE / "respaldo" / "boveda.enc"
HUELLA = BOVEDA / ".huella_respaldo"            # local e ignorada: evita un commit nuevo si la bóveda no cambió
NOMBRE_CLAVE = "ULTRON_BOVEDA_KEY"
_FECHA_FIJA = (2020, 1, 1, 0, 0, 0)              # zip idéntico para el mismo contenido


def _clave(crear=False):
    load_dotenv(BASE / ".env")
    clave = os.environ.get(NOMBRE_CLAVE, "").strip()
    if clave or not crear:
        return clave
    clave = Fernet.generate_key().decode()
    with open(BASE / ".env", "a", encoding="utf-8") as f:
        f.write(f"\n# Clave del respaldo cifrado de la bóveda: guárdala también fuera de esta PC\n{NOMBRE_CLAVE}={clave}\n")
    os.environ[NOMBRE_CLAVE] = clave
    return clave


def _archivos_boveda():
    return sorted(p for p in BOVEDA.rglob("*")
                  if p.is_file() and not p.is_symlink() and p != HUELLA and not p.name.startswith(".indice_rag"))


def _empaquetar() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in _archivos_boveda():
            info = zipfile.ZipInfo(p.relative_to(BOVEDA).as_posix(), _FECHA_FIJA)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    return buf.getvalue()


def cifrar_boveda(crear_clave=False) -> str:
    """Actualiza respaldo/boveda.enc si la bóveda cambió. Devuelve un mensaje corto con el resultado."""
    if not BOVEDA.is_dir():
        return "Bóveda: no existe la carpeta boveda/, nada que respaldar."
    clave = _clave(crear=crear_clave)
    if not clave:
        return f"Bóveda: sin {NOMBRE_CLAVE} en el .env; ejecuta 'python respaldo_boveda.py' una vez para crearla."
    datos = _empaquetar()
    huella = hashlib.sha256(datos).hexdigest()
    if ARCHIVO_CIFRADO.exists() and HUELLA.exists() and HUELLA.read_text().strip() == huella:
        return "Bóveda: sin cambios desde el último respaldo cifrado."
    ARCHIVO_CIFRADO.parent.mkdir(exist_ok=True)
    ARCHIVO_CIFRADO.write_bytes(Fernet(clave.encode()).encrypt(datos))
    HUELLA.write_text(huella)
    return f"Bóveda: respaldo cifrado actualizado ({len(_archivos_boveda())} archivos)."


def restaurar_boveda(destino=BASE / "boveda_restaurada") -> str:
    """Descifra respaldo/boveda.enc en 'destino' (nunca sobrescribe boveda/ directamente)."""
    clave = _clave()
    if not clave:
        return f"Falta {NOMBRE_CLAVE} en el .env: cópiala desde donde la guardaste."
    try:
        datos = Fernet(clave.encode()).decrypt(ARCHIVO_CIFRADO.read_bytes())
    except InvalidToken:
        return "La clave no corresponde a este respaldo (o el archivo está dañado)."
    destino = Path(destino)
    with zipfile.ZipFile(io.BytesIO(datos)) as z:
        for nombre in z.namelist():
            real = (destino / nombre).resolve()
            if not real.is_relative_to(destino.resolve()):
                return f"Respaldo rechazado: ruta peligrosa dentro del zip ({nombre})."
        z.extractall(destino)
    return f"Bóveda restaurada en {destino} ({len(z.namelist())} archivos). Revísala y cópiala a boveda/."


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(restaurar_boveda() if "--restaurar" in sys.argv else cifrar_boveda(crear_clave=True))
