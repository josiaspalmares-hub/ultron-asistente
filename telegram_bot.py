import os
import hmac
import io
import secrets
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
from pathlib import Path
from datetime import datetime
import telebot
import sys
from dotenv import load_dotenv
from log_seguro import instalar_log_seguro

# 1. Configurar encoding y cargar el archivo .env primero
sys.stdout.reconfigure(encoding='utf-8')
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# 2. Registrar el enmascarador de secretos en los logs
instalar_log_seguro()

# Las credenciales viven SOLO en el archivo .env (nunca en el código):
#   TELEGRAM_BOT_TOKEN=...            TELEGRAM_ALLOWED_USER_ID=...
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")

if TOKEN:
    TOKEN = TOKEN.strip().replace('"', '').replace("'", "")
if ALLOWED_ID:
    ALLOWED_ID = ALLOWED_ID.strip().replace('"', '').replace("'", "")

if not TOKEN or not ALLOWED_ID:
    print("❌ Falta TELEGRAM_BOT_TOKEN o TELEGRAM_ALLOWED_USER_ID en el archivo .env. El bot no se inicia "
          "(sin usuario autorizado cualquiera podría apagar tu PC).")
    sys.exit(1)

import pyautogui
from diagnostico_pc import obtener_diagnostico_pc
from git_autonomo import ejecutar_git_autonomo
from organizador_boveda import organizar_boveda_memoria

bot = telebot.TeleBot(TOKEN)

# ==========================================
# 🔒 VARIABLES Y UTILIDADES DE SEGURIDAD
# ==========================================
_SYS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_EDAD_MENSAJE_S = 60      # ignora órdenes viejas (cola de Telegram tras un reinicio, o repeticiones)
CONFIRMACION_TTL_S = 30
_pendiente, _pendiente_lock = {}, threading.Lock()

def es_usuario_autorizado(message) -> bool:
    # Fail-closed: usuario autorizado + chat PRIVADO con ese usuario + mensaje reciente
    try:
        if not ALLOWED_ID or message.from_user is None:
            return False
        if (str(message.from_user.id) != str(ALLOWED_ID) or message.chat.type != "private"
                or str(message.chat.id) != str(ALLOWED_ID)):
            print(f"[SEGURIDAD] Orden rechazada (user_id={message.from_user.id}, chat={message.chat.type})")
            return False
        return (time.time() - message.date) <= MAX_EDAD_MENSAJE_S
    except Exception:
        return False

def _ejecutar_sistema(exe: str, *args) -> int:
    return subprocess.run([os.path.join(_SYS32, exe), *args], timeout=10, creationflags=_SIN_VENTANA).returncode

def _pedir_confirmacion(message, accion: str, aviso: str):
    codigo = f"{secrets.randbelow(10**6):06d}"
    with _pendiente_lock:
        _pendiente.clear()
        _pendiente.update(accion=accion, codigo=codigo, expira=time.time() + CONFIRMACION_TTL_S)
    bot.reply_to(message, f"⚠️ {aviso}\nPara confirmar envía: /confirmar {codigo}\n(caduca en {CONFIRMACION_TTL_S} s)")

# ==========================================
# 🤖 HANDLERS DEL BOT
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not es_usuario_autorizado(message):
        return
    panel = (
        "🤖 SISTEMAS DE ULTRON REMOTO ACTIVOS\n\n"
        "Comandos disponibles:\n"
        "📌 /pc - Diagnóstico de hardware en tiempo real (CPU, RAM, Discos)\n"
        "📸 /captura - Captura de pantalla actual de la PC\n"
        "📂 /boveda - Organizar registros diarios en la Bóveda\n"
        "🔄 /git - Ejecutar respaldo automático a GitHub\n"
        "🔒 /bloquear - Bloquear la sesión de Windows\n"
        "🛑 /apagar - Apagar la PC (requiere confirmación)\n"
        "🔄 /reiniciar - Reiniciar la PC (requiere confirmación)\n"
        "✅ /confirmar - Confirmar acciones críticas (apagado/reinicio)\n"
        "❌ /cancelar_apagado - Cancelar apagado/reinicio en curso"
    )
    bot.reply_to(message, panel)

@bot.message_handler(commands=['pc'])
def cmd_diagnostico(message):
    if not es_usuario_autorizado(message): return
    bot.reply_to(message, "⏳ Leyendo métricas del hardware...")
    reporte = obtener_diagnostico_pc()
    bot.send_message(message.chat.id, f"```\n{reporte}\n```", parse_mode="Markdown")

@bot.message_handler(commands=['boveda'])
def cmd_boveda(message):
    if not es_usuario_autorizado(message): return
    res = organizar_boveda_memoria()
    bot.reply_to(message, f"🧠 {res}")

@bot.message_handler(commands=['git'])
def cmd_git(message):
    if not es_usuario_autorizado(message): return
    bot.reply_to(message, "⏳ Ejecutando respaldo remoto en GitHub...")
    res = ejecutar_git_autonomo("Respaldo solicitado vía Telegram Bot")
    bot.reply_to(message, f"📦 {res}")

@bot.message_handler(commands=['captura'])
def cmd_captura(message):
    if not es_usuario_autorizado(message): return
    try:
        buf = io.BytesIO()                       # en memoria: no queda ningún archivo en disco
        pyautogui.screenshot().save(buf, format="PNG")
        buf.seek(0)
        buf.name = "captura.png"
        bot.send_photo(message.chat.id, buf, caption="📸 Captura de pantalla en tiempo real.")
    except Exception as e:
        print(f"[bot] Error en /captura: {type(e).__name__}")   # el detalle puede incluir la URL con el token
        bot.reply_to(message, "❌ No se pudo tomar o enviar la captura.")

@bot.message_handler(commands=['bloquear'])
def cmd_bloquear(message):
    if not es_usuario_autorizado(message): return
    ok = _ejecutar_sistema("rundll32.exe", "user32.dll,LockWorkStation") == 0
    bot.reply_to(message, "🔒 Estación de trabajo bloqueada." if ok else "❌ No se pudo bloquear.")

@bot.message_handler(commands=['apagar'])
def cmd_apagar(message):
    if not es_usuario_autorizado(message): return
    _pedir_confirmacion(message, "apagar", "Vas a APAGAR la PC.")

@bot.message_handler(commands=['reiniciar'])
def cmd_reiniciar(message):
    if not es_usuario_autorizado(message): return
    _pedir_confirmacion(message, "reiniciar", "Vas a REINICIAR la PC.")

@bot.message_handler(commands=['confirmar'])
def cmd_confirmar(message):
    if not es_usuario_autorizado(message): return
    partes = (message.text or "").split()
    with _pendiente_lock:
        p = dict(_pendiente)
        _pendiente.clear()                       # un solo intento: el código no se reutiliza
    if (not p or time.time() > p["expira"] or len(partes) != 2
            or not hmac.compare_digest(partes[1].encode(), p["codigo"].encode())):
        bot.reply_to(message, "❌ Confirmación inválida o caducada.")
        return
    flag = "/s" if p["accion"] == "apagar" else "/r"
    if _ejecutar_sistema("shutdown.exe", flag, "/t", "10") == 0:
        bot.reply_to(message, f"🛑 Confirmado: {p['accion']} en 10 s. Usa /cancelar_apagado para abortar.")
    else:
        bot.reply_to(message, "❌ No se pudo programar la acción.")

@bot.message_handler(commands=['cancelar_apagado'])
def cmd_cancelar_apagado(message):
    if not es_usuario_autorizado(message): return
    ok = _ejecutar_sistema("shutdown.exe", "/a") == 0
    bot.reply_to(message, "✅ Secuencia cancelada." if ok else "No había ningún apagado o reinicio pendiente.")

if __name__ == "__main__":
    print("🚀 Servidor Telegram de Ultron activo y esperando órdenes...")
    bot.infinity_polling(skip_pending=True)