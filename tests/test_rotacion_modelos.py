"""Cambio de modelo y de clave sin llamar a Gemini (chats simulados)."""
import httpx
import pytest


class ChatFalso:
    def __init__(self, error=None, texto="ok"):
        self.error, self.texto = error, texto

    def send_message(self, mensaje):
        if self.error:
            raise self.error
        return type("Resp", (), {"text": self.texto})()

    def get_history(self):
        return []


@pytest.fixture
def ia(ultron, monkeypatch):
    """Por modelo: qué error lanza su chat (None = responde bien)."""
    fallos = {}
    monkeypatch.setattr(ultron, "modelo_index", 0)
    monkeypatch.setattr(ultron, "_respaldo_desde", None)
    monkeypatch.setattr(ultron, "guardar_diario_boveda", lambda texto: None)
    monkeypatch.setattr(ultron, "crear_chat", lambda clave, historial=None: ChatFalso(
        fallos.get(ultron.MODELOS[ultron.modelo_index]), f"respuesta de {ultron.MODELOS[ultron.modelo_index]}"))
    monkeypatch.setattr(ultron, "chat", None)
    ultron.chat = ultron.crear_chat("clave")
    return ultron, fallos


@pytest.mark.parametrize("error", [httpx.ReadTimeout(""), RuntimeError("503 UNAVAILABLE"),
                                   RuntimeError("504 DEADLINE_EXCEEDED"), RuntimeError("404 NOT_FOUND")])
def test_pasa_al_siguiente_modelo(ia, error):
    ultron, fallos = ia
    fallos[ultron.MODELOS[0]] = error
    ultron.chat = ultron.crear_chat("clave")
    assert ultron._enviar_mensaje_con_rotacion("hola") == f"respuesta de {ultron.MODELOS[1]}"
    assert ultron.modelo_index == 1 and ultron._respaldo_desde


def test_vuelve_al_principal_tras_el_tiempo(ia):
    ultron, fallos = ia
    fallos[ultron.MODELOS[0]] = RuntimeError("503")
    ultron.chat = ultron.crear_chat("clave")
    ultron._enviar_mensaje_con_rotacion("hola")
    del fallos[ultron.MODELOS[0]]
    ultron._respaldo_desde -= ultron.REINTENTO_PRINCIPAL_S + 1
    assert ultron._enviar_mensaje_con_rotacion("hola") == f"respuesta de {ultron.MODELOS[0]}"
    assert ultron.modelo_index == 0


def test_error_desconocido_no_rota(ia):
    ultron, fallos = ia
    fallos[ultron.MODELOS[0]] = RuntimeError("400 INVALID_ARGUMENT")
    ultron.chat = ultron.crear_chat("clave")
    assert ultron._enviar_mensaje_con_rotacion("hola").startswith("Error en IA")
    assert ultron.modelo_index == 0


def test_cuota_agotada_en_todas_las_claves_cambia_de_modelo(ia):
    ultron, fallos = ia
    fallos[ultron.MODELOS[0]] = RuntimeError("429 RESOURCE_EXHAUSTED quota PerDay")
    ultron.chat = ultron.crear_chat("clave")
    assert ultron._enviar_mensaje_con_rotacion("hola") == f"respuesta de {ultron.MODELOS[1]}"


def test_todo_falla_da_mensaje_claro(ia):
    ultron, fallos = ia
    for m in ultron.MODELOS:
        fallos[m] = RuntimeError("503 UNAVAILABLE")
    ultron.chat = ultron.crear_chat("clave")
    assert ultron._enviar_mensaje_con_rotacion("hola").startswith("❌ No se pudo completar")


def test_cuota_agotada_cambia_de_clave(ia, monkeypatch):
    ultron, fallos = ia
    monkeypatch.setattr(ultron, "current_key_index", 0)
    llamadas = []
    original = ultron.crear_chat

    def crear(clave, historial=None):
        llamadas.append(clave)
        return ChatFalso(RuntimeError("429 quota") if len(llamadas) == 1 else None)
    monkeypatch.setattr(ultron, "crear_chat", crear)
    ultron.chat = crear(ultron.api_keys[0])
    assert ultron._enviar_mensaje_con_rotacion("hola") == "ok"
    assert ultron.current_key_index == 1 % len(ultron.api_keys)
