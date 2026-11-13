import threading
import sounddevice as sd
import speech_recognition as sr

_MIC_LOCK = threading.Lock()
MAX_SEGUNDOS = 15

def escuchar_micropath(duracion_segundos: int = 5) -> str:
    """Graba audio del micrófono EN MEMORIA (sin archivos) y lo convierte a texto."""
    try:
        duracion = max(1, min(int(duracion_segundos), MAX_SEGUNDOS))
    except (TypeError, ValueError):
        duracion = 5
    sample_rate = 44100

    if not _MIC_LOCK.acquire(blocking=False):          # un solo uso del micrófono a la vez
        print("⚠️ El micrófono ya está en uso.")
        return ""
    try:
        print("\n🎤 [Ultron escuchando... hable ahora]")
        recording = sd.rec(int(duracion * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()
    except Exception as e:
        print(f"❌ Error al grabar audio: {e}")
        return ""
    finally:
        _MIC_LOCK.release()

    try:
        audio_data = sr.AudioData(recording.tobytes(), sample_rate, 2)
        texto = sr.Recognizer().recognize_google(audio_data, language="es-ES")
        print(f"🗣️ Usted dijo: {texto[:200]}")
        return texto[:500]
    except sr.UnknownValueError:
        print("⚠️ No se logró entender el audio.")
    except Exception as e:
        print(f"❌ Error al procesar audio: {e}")
    return ""

if __name__ == "__main__":
    escuchar_micropath()