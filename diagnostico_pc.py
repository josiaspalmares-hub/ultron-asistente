import psutil
import re

def _limpio(texto, largo=40) -> str:
    return re.sub(r"[`*_\[\]\x00-\x1f\x7f]", "", str(texto))[:largo]

def obtener_diagnostico_pc() -> str:
    """Obtiene métricas en tiempo real del hardware de la PC: uso de CPU, memoria RAM, discos y top de procesos activos."""
    try:
        # 1. Métrica de procesador (CPU)
        cpu_usage = psutil.cpu_percent(interval=1)
        cpu_cores = psutil.cpu_count(logical=False)
        cpu_threads = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        freq_actual = f"{round(cpu_freq.current / 1000, 2)} GHz" if cpu_freq else "N/A"

        # 2. Métrica de Memoria RAM
        ram = psutil.virtual_memory()
        ram_total_gb = round(ram.total / (1024**3), 2)
        ram_used_gb = round(ram.used / (1024**3), 2)
        ram_percent = ram.percent

        # 3. Almacenamiento (Discos / M.2)
        discos_info = []
        for partition in psutil.disk_partitions():
            if 'fixed' in partition.opts and 'remote' not in partition.opts:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total_gb = round(usage.total / (1024**3), 2)
                    used_gb = round(usage.used / (1024**3), 2)
                    percent = usage.percent
                    discos_info.append(f"Disco {_limpio(partition.device)} ({_limpio(partition.mountpoint)}): {used_gb} GB / {total_gb} GB ({percent}% usado)")
                except Exception:
                    pass

        # 4. Top 5 Procesos con mayor consumo de RAM
        procesos = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                procesos.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        top_ram = sorted(procesos, key=lambda p: p['memory_percent'] or 0, reverse=True)[:5]
        top_ram_str = "\n".join([f"  - {_limpio(p['name'])} (PID: {p['pid']}): {round(p['memory_percent'] or 0, 1)}% RAM" for p in top_ram])

        reporte = (
            f"=== REPORTE DE RENDIMIENTO DEL SISTEMA EN TIEMPO REAL ===\n\n"
            f"💻 PROCESADOR (CPU):\n"
            f"  - Uso actual: {cpu_usage}%\n"
            f"  - Frecuencia: {freq_actual}\n"
            f"  - Núcleos / Hilos: {cpu_cores} físicos / {cpu_threads} lógicos\n\n"
            f"🧠 MEMORIA RAM:\n"
            f"  - Consumo: {ram_used_gb} GB de {ram_total_gb} GB ({ram_percent}% usado)\n\n"
            f"💾 ALMACENAMIENTO:\n"
            f"  " + "\n  ".join(discos_info) + "\n\n"
            f"⚡ TOP 5 PROCESOS QUE MÁS RAM CONSUMEN:\n"
            f"{top_ram_str}"
        )
        return reporte

    except Exception as e:
        return f"Error al generar el diagnóstico de hardware: {e}"

if __name__ == "__main__":
    print(obtener_diagnostico_pc())