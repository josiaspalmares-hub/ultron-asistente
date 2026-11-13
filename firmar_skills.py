"""firmar_skills.py - Genera y firma skills_seguras_ultron/manifest.json (SHA-256 + HMAC).
Ejecútalo SOLO después de revisar a mano el contenido de cada habilidad."""
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
CARPETA = (BASE / "skills_seguras_ultron").resolve()
MAX_BYTES = 64 * 1024


def firma_manifiesto(archivos: dict, clave: str) -> str:
    payload = json.dumps(archivos, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hmac.new(clave.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def main() -> int:
    load_dotenv(BASE / ".env")
    clave = os.environ.get("ULTRON_MANIFEST_KEY", "").strip()
    if len(clave) < 32:
        print("Falta ULTRON_MANIFEST_KEY (mín. 32 caracteres) en tu .env. Genera una con:\n"
              '  python -c "import secrets; print(secrets.token_hex(32))"')
        return 1
    if not CARPETA.is_dir():
        print(f"No existe la carpeta {CARPETA}")
        return 1

    archivos = {}
    for p in sorted(CARPETA.rglob("*.md")):
        real = p.resolve()
        if p.is_symlink() or not real.is_relative_to(CARPETA):
            print(f"  [OMITIDO] enlace simbólico o fuera de la carpeta: {p.name}")
            continue
        datos = real.read_bytes()
        if len(datos) > MAX_BYTES:
            print(f"  [OMITIDO] demasiado grande (> {MAX_BYTES} bytes): {p.name}")
            continue
        rel = real.relative_to(CARPETA).as_posix()
        archivos[rel] = hashlib.sha256(datos).hexdigest()
        print(f"  {archivos[rel][:16]}…  {rel}  ({len(datos)} bytes)")

    if not archivos:
        print("No hay habilidades .md que firmar.")
        return 1
    if input("\n¿Revisaste TODAS estas habilidades y confirmas que son de confianza? (escribe SI): ").strip() != "SI":
        print("Cancelado; no se escribió nada.")
        return 1

    manifiesto = {"version": 1, "archivos": archivos, "firma": firma_manifiesto(archivos, clave)}
    (CARPETA / "manifest.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"\nManifiesto firmado con {len(archivos)} habilidad(es).")
    return 0


if __name__ == "__main__":
    sys.exit(main())