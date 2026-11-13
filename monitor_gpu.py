"""monitor_gpu.py - Uso, VRAM y temperatura de la GPU para el HUD (NVIDIA, contadores de Windows o LibreHardwareMonitor)."""
import json
import os
import re
import subprocess
import time

from utilidades import avisar_una_vez

GPU_PREFERIDA = "RX 580"
VRAM_TOTAL_MB_MANUAL = None
_gpu_cache = {"d": None}
_gpu_estado = {"modo": None, "fallos": 0}
_RE_LUID = re.compile(r"luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+")
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _gpu_nvidia():
    try:
        import pynvml
        pynvml.nvmlInit()
        try:
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            u = pynvml.nvmlDeviceGetUtilizationRates(h)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            t = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            nombre = pynvml.nvmlDeviceGetName(h)
            nombre = nombre.decode() if isinstance(nombre, bytes) else nombre
            return {"name": nombre, "util": float(u.gpu), "vram_used": mem.used / 1048576,
                    "vram_total": mem.total / 1048576, "temp": float(t)}
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        pass
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3,
                           creationflags=_NO_WINDOW)
        if r.returncode == 0 and r.stdout.strip():
            n, u, mu, mt, t = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
            return {"name": n, "util": float(u), "vram_used": float(mu), "vram_total": float(mt), "temp": float(t)}
    except Exception:
        pass
    return None


_CLAVES_VIDEO = (r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11cd-be10-08002be10318}",
                 # algunas instalaciones (p. ej. Windows recortado) solo tienen los datos aquí, un nivel más abajo
                 r"SYSTEM\CurrentControlSet\Control\Video")


def _subclaves(raiz):
    import winreg
    for i in range(256):
        try:
            yield winreg.EnumKey(raiz, i)
        except OSError:
            return


def _datos_adaptador(k):
    """(descripción, MB de VRAM) de una clave de adaptador, o None si no los tiene."""
    import winreg
    try:
        desc = str(winreg.QueryValueEx(k, "DriverDesc")[0])
    except OSError:
        return None
    for valor in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
        try:
            v = winreg.QueryValueEx(k, valor)[0]
        except OSError:
            continue
        mem = int.from_bytes(v, "little") if isinstance(v, (bytes, bytearray)) else int(v)
        return (desc, mem / 1048576) if mem else None
    return None


def _adaptadores_registro():
    import winreg
    encontrados = []
    for ruta in _CLAVES_VIDEO:
        try:
            raiz = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta)
        except OSError:
            continue
        with raiz:
            for sub in _subclaves(raiz):
                try:
                    with winreg.OpenKey(raiz, sub) as k:
                        rutas_hijas = [sub] if sub.isdigit() else [f"{sub}\\{h}" for h in _subclaves(k) if h.isdigit()]
                except OSError:
                    continue
                for rel in rutas_hijas:
                    try:
                        with winreg.OpenKey(raiz, rel) as k:
                            datos = _datos_adaptador(k)
                    except OSError:
                        continue
                    if datos:
                        encontrados.append(datos)
        if encontrados:
            break
    return encontrados


def _vram_total_registro():
    try:
        encontrados = _adaptadores_registro()
    except Exception as e:
        avisar_una_vez("gpu-registro", f"No se pudo leer la GPU del registro: {e}")
        return None, None
    if not encontrados:
        return None, None
    preferidas = [e for e in encontrados if GPU_PREFERIDA.lower() in e[0].lower()]
    return (preferidas or sorted(encontrados, key=lambda e: -e[1]))[0]


def _consultar_contadores_wmi():
    import pythoncom
    import wmi
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        motores = [(x.Name, float(x.UtilizationPercentage or 0))
                   for x in c.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()]
        memorias = [(x.Name, float(x.DedicatedUsage or 0))
                    for x in c.Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory()]
        return motores, memorias
    finally:
        pythoncom.CoUninitialize()


def _consultar_contadores_powershell():
    script = ("$e=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | Select-Object Name,UtilizationPercentage);"
              "$m=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory | Select-Object Name,DedicatedUsage);"
              "ConvertTo-Json -Compress -Depth 3 -InputObject @{e=$e;m=$m}")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(r.stderr.strip() or "PowerShell sin salida")
    datos = json.loads(r.stdout)

    def lista(x):
        return x if isinstance(x, list) else ([x] if x else [])
    motores = [(i["Name"], float(i.get("UtilizationPercentage") or 0)) for i in lista(datos.get("e"))]
    memorias = [(i["Name"], float(i.get("DedicatedUsage") or 0)) for i in lista(datos.get("m"))]
    return motores, memorias


def _calcular_gpu(motores, memorias):
    if not motores and not memorias:
        return None
    luid, usada = None, 0.0
    if memorias:
        mejor = max(memorias, key=lambda x: x[1])
        usada = mejor[1]
        h = _RE_LUID.search(mejor[0] or "")
        luid = h.group(0).lower() if h else None
    por_tipo = {}
    for nombre, pct in motores:
        h = _RE_LUID.search(nombre or "")
        if luid and (not h or h.group(0).lower() != luid):
            continue
        t = re.search(r"engtype_(\w+)", nombre or "")
        tipo = t.group(1) if t else "x"
        por_tipo[tipo] = por_tipo.get(tipo, 0.0) + pct
    util = min(100.0, max(por_tipo.values())) if por_tipo else 0.0
    return {"util": util, "vram_used": usada / 1048576}


def _temp_gpu_lhm():
    try:
        import pythoncom
        import wmi
        pythoncom.CoInitialize()
        try:
            for ns in (r"root\LibreHardwareMonitor", r"root\OpenHardwareMonitor"):
                try:
                    sensores = wmi.WMI(namespace=ns).Sensor(SensorType="Temperature")
                except Exception:
                    continue
                for s in sensores:
                    if "gpu" in f"{s.Identifier} {s.Name}".lower() and s.Value is not None:
                        return float(s.Value)
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass
    return None


def _gpu_windows():
    if os.name != "nt":
        return None
    try:
        motores, memorias = _consultar_contadores_wmi()
    except Exception:
        motores, memorias = _consultar_contadores_powershell()
    calc = _calcular_gpu(motores, memorias)
    if not calc:
        return None
    nombre, total = _vram_total_registro()
    if VRAM_TOTAL_MB_MANUAL:
        total = VRAM_TOTAL_MB_MANUAL
    return {"name": nombre or "GPU", "util": calc["util"], "vram_used": calc["vram_used"],
            "vram_total": total, "temp": _temp_gpu_lhm()}


def _leer_gpu():
    orden = [("nvidia", _gpu_nvidia), ("windows", _gpu_windows)]
    if _gpu_estado["modo"]:
        orden.sort(key=lambda x: x[0] != _gpu_estado["modo"])
    for nombre, fn in orden:
        try:
            d = fn()
            if d:
                _gpu_estado.update(modo=nombre, fallos=0)
                return d
        except Exception as e:
            avisar_una_vez(f"gpu-{nombre}", f"Lectura de GPU por '{nombre}' falló (se prueba otro método): {e}")
            continue
    _gpu_estado["fallos"] += 1
    if _gpu_estado["fallos"] >= 3:
        _gpu_estado["modo"] = None
    return None


def _bucle_gpu():
    while True:
        try:
            _gpu_cache["d"] = _leer_gpu()
        except Exception as e:
            avisar_una_vez("gpu-bucle", f"El monitor de GPU falló: {e}")
            _gpu_cache["d"] = None
        time.sleep(2 if _gpu_cache["d"] else 15)
