"""habilidades.py - Carga habilidades (.md) de skills_seguras_ultron SOLO si coinciden con el manifiesto firmado."""
import hashlib
import hmac
import json
import os
import re
from collections import Counter
from pathlib import Path

from utilidades import norm as _norm

_SKILLS_DIR = "skills_seguras_ultron"
_MAX_SKILL_BYTES = 64 * 1024
_MAX_SKILL_CHARS = 15000


def _alias_habilidad(rel: str) -> str:
    # casi todas las habilidades se llaman SKILL.md: su nombre real es el de la carpeta
    p = Path(rel)
    return (p.parent.name if p.name.lower() == "skill.md" else p.stem).lower()


def _prioridad_habilidad(rel: str):
    # primero las de esta PC (claude_pc) y las rutas más cortas; las copias de ECC para otros editores al final
    return (not rel.startswith("claude_pc/"), rel.startswith("."), rel.count("/"), rel)


def _firma_manifiesto(archivos: dict, clave: str) -> str:
    payload = json.dumps(archivos, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hmac.new(clave.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _cargar_manifiesto_skills(carpeta: Path) -> dict:
    clave = os.environ.get("ULTRON_MANIFEST_KEY", "").strip()
    if len(clave) < 32:
        raise PermissionError("falta ULTRON_MANIFEST_KEY (mín. 32 caracteres) en el .env; habilidades deshabilitadas.")
    ruta = carpeta / "manifest.json"
    if not ruta.is_file():
        raise PermissionError("no existe manifest.json; ejecuta firmar_skills.py tras revisar tus habilidades.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        archivos, firma = datos["archivos"], str(datos["firma"])
    except Exception:
        raise PermissionError("manifest.json ilegible o con formato inválido.")
    if not isinstance(archivos, dict) or not hmac.compare_digest(_firma_manifiesto(archivos, clave), firma):
        raise PermissionError("la firma del manifiesto no es válida: posible alteración.")
    return archivos


def cargar_habilidad(nombre_habilidad: str) -> str:
    """Carga una habilidad de 'skills_seguras_ultron' SOLO si su SHA-256 coincide con el manifiesto firmado."""
    try:
        carpeta = Path(_SKILLS_DIR).resolve()
        if not carpeta.is_dir():
            return "❌ La carpeta 'skills_seguras_ultron' no existe."

        prog_clean = str(nombre_habilidad).lower().strip().replace(".md", "")
        if not re.fullmatch(r"[\w\- ]{1,60}", prog_clean):
            return "Bloqueado (seguridad): nombre de habilidad inválido."

        try:
            archivos = _cargar_manifiesto_skills(carpeta)
        except PermissionError as e:
            print(f"[SEGURIDAD] Habilidades bloqueadas: {e}")
            return f"Bloqueado (seguridad): {e}"

        candidatos = sorted((r for r in archivos if prog_clean in _alias_habilidad(r)), key=_prioridad_habilidad)
        exactos = [r for r in candidatos if _alias_habilidad(r) == prog_clean]
        elegidos = exactos or candidatos
        if not elegidos:
            return f"No se encontró ninguna habilidad firmada que coincida con '{str(nombre_habilidad)[:40]}'."

        rel = elegidos[0]
        real = (carpeta / rel).resolve()
        esperado = archivos[rel]
        if (not isinstance(esperado, str) or not real.is_relative_to(carpeta) or real.suffix.lower() != ".md"
                or not real.is_file() or real.stat().st_size > _MAX_SKILL_BYTES):
            return "Bloqueado (seguridad): archivo de habilidad no válido."

        datos = real.read_bytes()   # se lee UNA vez: el hash y el contenido cargado son exactamente los mismos bytes
        if not hmac.compare_digest(hashlib.sha256(datos).hexdigest(), esperado.lower()):
            print(f"[SEGURIDAD] Hash distinto, habilidad NO cargada: {rel}")
            return f"Bloqueado (seguridad): '{rel}' fue modificada desde que se firmó el manifiesto."

        texto = datos.decode('utf-8', errors='replace')
        recorte = "\n[... recortado ...]" if len(texto) > _MAX_SKILL_CHARS else ""
        return f"✅ Habilidad '{_alias_habilidad(rel)}' ({rel}) verificada y cargada:\n\n{texto[:_MAX_SKILL_CHARS]}{recorte}"
    except Exception as e:
        return f"Error al cargar habilidad: {e}"


def listar_habilidades(filtro: str = "") -> str:
    """Lista los nombres de las habilidades firmadas que se pueden cargar con cargar_habilidad.
    'filtro' busca por nombre o carpeta (ej. 'diseno-web', 'video', 'seo', 'goldhour'). Sin filtro muestra las categorías."""
    try:
        archivos = _cargar_manifiesto_skills(Path(_SKILLS_DIR).resolve())
    except PermissionError as e:
        return f"Bloqueado (seguridad): {e}"
    skills = sorted({(Path(r).parent.as_posix(), _alias_habilidad(r)) for r in archivos
                     if Path(r).name.lower() == "skill.md"})
    f = _norm(filtro).strip()
    if not f:
        categorias = Counter(p.split("/")[1] if p.startswith("claude_pc/") else "ecc (programación y agentes)"
                             for p, _ in skills)
        return (f"Hay {len(skills)} habilidades. Categorías: "
                + ", ".join(f"{c} ({n})" for c, n in sorted(categorias.items()))
                + ". Usa un filtro para ver los nombres.")
    hallados = sorted({n for p, n in skills if f in n or f in _norm(p)})
    if not hallados:
        return f"No hay habilidades que coincidan con '{str(filtro)[:40]}'."
    return f"{len(hallados)} habilidades: " + ", ".join(hallados[:150])
