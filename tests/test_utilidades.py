import threading
import time

from log_seguro import redactar
from utilidades import avisar_una_vez, con_timeout, lanzar_supervisado, norm


def test_norm_quita_acentos_y_conserva_largo():
    assert norm("Canción ÁÉÍ") == "cancion aei"
    assert len(norm("ñandú")) == len("ñandú")


def test_con_timeout_devuelve_valor_error_y_tiempo_agotado():
    assert con_timeout(lambda x: x * 2, 1, 21) == (True, 42)
    ok, msg = con_timeout(lambda: 1 / 0, 1)
    assert not ok and "ZeroDivisionError" in msg
    ok, msg = con_timeout(time.sleep, 0.1, 2)
    assert not ok and "tardó más" in msg


def test_avisar_una_vez_solo_registra_la_primera():
    vistos = []
    for _ in range(3):
        avisar_una_vez("prueba-unica", "fallo", log=vistos.append)
    assert vistos == ["fallo"]


def test_lanzar_supervisado_relanza_tras_un_fallo():
    llamadas, listo = [], threading.Event()

    def trabajo():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("caída simulada")
        listo.set()
    lanzar_supervisado("prueba", trabajo, log=lambda m: None, espera_s=0.01)
    assert listo.wait(2) and len(llamadas) == 2


def test_redactar_oculta_claves_de_google_y_telegram():
    texto = "clave AIza" + "x" * 35 + " bot 123456789:" + "A" * 35
    limpio = redactar(texto)
    assert "AIza" not in limpio and "123456789:" not in limpio
