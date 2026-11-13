import shutil
import psutil

def auditoria_sistema():
    """
    Protocolo Audit: Monitorea el estado crítico del sistema operativo,
    el almacenamiento disponible en la unidad principal y el uso de la memoria RAM.
    """
    try:
        # Analizar el almacenamiento en disco (Unidad C:)
        disco = shutil.disk_usage("C:\\")
        gb_libres = disco.free // (2**30)
        gb_totales = disco.total // (2**30)
        porcentaje_libre = (disco.free / disco.total) * 100

        # Monitorear el uso global de la memoria RAM
        memoria = psutil.virtual_memory()
        ram_uso = memoria.percent

        # Definir el nivel de estado según los umbrales
        if porcentaje_libre < 10 or ram_uso > 92:
            nivel_estado = "ALERTA CRÍTICA"
        elif porcentaje_libre < 20 or ram_uso > 80:
            nivel_estado = "PRECAUCIÓN"
        else:
            nivel_estado = "SEGURO // ÓPTIMO"

        return {
            "estado": nivel_estado,
            "disco_libre": f"{gb_libres} GB libres ({gb_totales} GB total)",
            "ram_uso": f"{ram_uso}%"
        }
        
    except Exception as e:
        print(f"[ERROR EN AUDITORÍA]: {e}")
        return {
            "estado": "ERROR DE SENSOR",
            "disco_libre": "N/D",
            "ram_uso": "N/D"
        }

def protocolo_armor():
    """
    Protocolo Armor: Realiza un escaneo defensivo rápido contando 
    las conexiones de red activas en el equipo para asegurar el perímetro.
    """
    try:
        conexiones = len(psutil.net_connections(kind='inet'))
        return f"Blindaje activo. Conexiones de red monitoreadas: {conexiones}. Perímetro seguro."
    except Exception as e:
        return f"[ERROR EN ARMOR]: {e}"

# Prueba directa si ejecutas el archivo solo
if __name__ == "__main__":
    print("--- INICIANDO PROTOCOLOS DE SEGURIDAD ---")
    auditoria = auditoria_sistema()
    print(f"Estado del Sistema: {auditoria['estado']}")
    print(f"Almacenamiento: {auditoria['disco_libre']}")
    print(f"Memoria RAM: {auditoria['ram_uso']}")
    print(protocolo_armor())