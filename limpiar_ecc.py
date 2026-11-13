import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # los emojis no tumban el script fuera de una consola

# ==============================================================================
# 🛡️ SCRIPT DE AUDITORÍA Y FILTRADO DE SEGURIDAD AUTOMÁTICO PARA ECC
# ==============================================================================

# Carpeta ECC-main descomprimida: la de Descargas del usuario actual, o la que se pase como argumento
RUTA_ORIGEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "ECC-main"
CARPETA_DESTINO = Path(__file__).resolve().parent / "skills_seguras_ultron"

# Lenguajes/Tecnologías no deseadas que serán descartadas
PALABRAS_CLAVE_IGNORAR = [
    "rust", "fsharp", "gan", "go-build", "php", "ruby", "cplusplus", "cpp",
    "java", "kotlin", "swift", "dotnet", "csharp", "elixir", "haskell", "perl"
]

# Extensiones ejecutables o de código ejecutable eliminadas por seguridad
EXTENSIONES_PELIGROSAS = [
    ".exe", ".dll", ".bin", ".sh", ".bat", ".cmd", ".ps1", ".vbs", ".so", ".dylib"
]

def auditar_y_limpiar():
    if not RUTA_ORIGEN.exists():
        print("❌ No se encontró la carpeta en: " + str(RUTA_ORIGEN))
        print("Verifica que la carpeta 'ECC-main' esté descomprimida en Descargas.")
        return

    CARPETA_DESTINO.mkdir(exist_ok=True)
    
    conservados = 0
    eliminados = 0
    reporte = []

    print("=" * 60)
    print("🔍 INICIANDO AUDITORÍA DE SEGURIDAD EN 'ECC-main'")
    print("📂 Origen: " + str(RUTA_ORIGEN))
    print("📁 Destino: " + str(CARPETA_DESTINO.resolve()))
    print("=" * 60)

    for ruta_archivo in RUTA_ORIGEN.rglob("*"):
        if ruta_archivo.is_dir():
            continue

        nombre_lower = ruta_archivo.name.lower()
        extension = ruta_archivo.suffix.lower()

        # 1. Filtro de seguridad: Descartar ejecutables de inmediato
        if extension in EXTENSIONES_PELIGROSAS:
            eliminados += 1
            reporte.append("[ELIMINADO - EJECUTABLE] " + str(ruta_archivo.relative_to(RUTA_ORIGEN)))
            continue

        # 2. Filtro de irrelevancia: Descartar habilidades de lenguajes no usados
        if any(keyword in nombre_lower for keyword in PALABRAS_CLAVE_IGNORAR):
            eliminados += 1
            reporte.append("[ELIMINADO - TECNOLOGÍA NO USADA] " + str(ruta_archivo.relative_to(RUTA_ORIGEN)))
            continue

        # 3. Conservar documentación y habilidades Markdown (.md) y configuraciones (.json, .yaml)
        if extension in [".md", ".json", ".yaml", ".yml"]:
            subcarpeta_relativa = ruta_archivo.parent.relative_to(RUTA_ORIGEN)
            destino_final_dir = CARPETA_DESTINO / subcarpeta_relativa
            destino_final_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(ruta_archivo, destino_final_dir / ruta_archivo.name)
            conservados += 1
            reporte.append("[CONSERVADO - SEGURO] " + str(ruta_archivo.relative_to(RUTA_ORIGEN)))

    archivo_reporte = "reporte_auditoria_seguridad.txt"
    with open(archivo_reporte, "w", encoding="utf-8") as f:
        f.write("\n".join(reporte))

    print("\n" + "=" * 60)
    print("✅ AUDITORÍA Y FILTRADO COMPLETADOS CON ÉXITO")
    print("📦 Archivos seguros conservados: " + str(conservados))
    print("🗑️ Archivos descartados/filtrados: " + str(eliminados))
    print("📄 Reporte generado en: " + archivo_reporte)
    print("📁 Habilidades seguras en: " + str(CARPETA_DESTINO.resolve()))
    print("=" * 60)

if __name__ == "__main__":
    auditar_y_limpiar()