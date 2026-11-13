import os
import tempfile
import threading
from pathlib import Path

from gtts import gTTS
from playsound import playsound
from log_seguro import redactar

_CARPETA_VOZ = Path(__file__).resolve().parent / "cache_voz"
_VOZ_LOCK = threading.Lock()                     # un solo audio a la vez
MAX_CHARS_VOZ = 500

def hablar(texto):
    """Sintetizador de voz basado en Google TTS para Ultron (texto acotado y sin secretos, archivo temporal único)."""
    texto = redactar(" ".join(str(texto or "").split()))[:MAX_CHARS_VOZ]
    if not texto:
        return
    archivo_temp = None
    try:
        _CARPETA_VOZ.mkdir(exist_ok=True)
        with _VOZ_LOCK:
            fd, archivo_temp = tempfile.mkstemp(prefix="ultron_tts_", suffix=".mp3", dir=_CARPETA_VOZ)
            os.close(fd)
            gTTS(text=texto, lang='es', slow=False).save(archivo_temp)
            if os.path.getsize(archivo_temp) > 0:
                playsound(archivo_temp)
            else:
                print(f"[AVISO VOZ]: {texto}")
    except Exception as e:
        print(f"[ERROR EN MÓDULO DE VOZ]: {redactar(e)}")
        print(f"[VOZ TEXTO]: {texto}")
    finally:
        if archivo_temp:
            try:
                os.remove(archivo_temp)
            except OSError:
                pass

if __name__ == "__main__":
    hablar("Sistemas operativos al cien por ciento. Escuchando sus órdenes, Sr. Josias.")