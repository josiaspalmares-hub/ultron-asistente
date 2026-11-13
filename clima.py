import requests

def _como_numero(valor, minimo, maximo):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return round(n, 1) if minimo <= n <= maximo else None

def obtener_datos_clima():
    """
    Consulta en tiempo real la temperatura y la humedad con la API gratuita de Open-Meteo.
    Por defecto configurado para Caracas, Venezuela.
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=10.488&longitude=-66.879&current=temperature_2m,relative_humidity_2m,weather_code"
        response = requests.get(url, timeout=5, allow_redirects=False)
        if response.status_code == 200:
            current = response.json().get("current", {})
            temp = _como_numero(current.get("temperature_2m"), -90, 60)
            humedad = _como_numero(current.get("relative_humidity_2m"), 0, 100)
            if temp is not None and humedad is not None:
                return {"temperatura": f"{temp}°C", "humedad": f"{humedad:.0f}%", "estado": "Óptimo"}
    except Exception as e:
        print(f"[ERROR CLIMA]: {e}")

    # Sin conexión o respuesta inválida: NO se inventan datos
    return {"temperatura": "N/D", "humedad": "N/D", "estado": "Sin conexión"}

if __name__ == "__main__":
    datos = obtener_datos_clima()
    print(f"Sensor Ambiental - Temperatura: {datos['temperatura']} | Humedad: {datos['humedad']}")