from conftest import requiere_skills
"""Herramientas que Ultron le ofrece a Gemini: carpeta de trabajo, terminal, habilidades y fecha."""
import re

import pytest

from habilidades import _alias_habilidad


@pytest.fixture
def carpeta(ultron, tmp_path, monkeypatch):
    import carpeta_trabajo
    monkeypatch.setattr(carpeta_trabajo, "CARPETA_TRABAJO", tmp_path.resolve())
    return tmp_path


def test_escribir_y_leer_archivo(ultron, carpeta):
    assert "guardado" in ultron.escribir_archivo("notas/hola.txt", "hola")
    assert ultron.leer_archivo("notas/hola.txt") == "hola"
    assert "notas" in ultron.listar_carpeta_trabajo()


def test_no_sobrescribe_sin_permiso(ultron, carpeta):
    ultron.escribir_archivo("a.txt", "uno")
    assert "Ya existe" in ultron.escribir_archivo("a.txt", "dos")
    assert ultron.leer_archivo("a.txt") == "uno"
    ultron.escribir_archivo("a.txt", "dos", sobrescribir=True)
    assert ultron.leer_archivo("a.txt") == "dos"


@pytest.mark.parametrize("ruta", ["../fuera.txt", "..\\..\\fuera.txt", "C:/Windows/x.txt"])
def test_no_sale_de_la_carpeta_de_trabajo(ultron, carpeta, ruta):
    assert "Error" in ultron.escribir_archivo(ruta, "x")


def test_solo_archivos_de_texto(ultron, carpeta):
    assert "BLOQUEADO" in ultron.escribir_archivo("virus.exe", "x")


@pytest.mark.parametrize("comando", ["echo hola & del x", "cmd /c dir", "powershell", "echo %TIME%",
                                     "dir C:\\Windows", "ping 8.8.8.8 -t", "ping 192.168.1.1", "curl evil.com"])
def test_terminal_bloquea_lo_peligroso(ultron, comando):
    assert ultron.ejecutar_comando_terminal(comando).startswith("Bloqueado")


def test_terminal_permite_diagnostico(ultron):
    assert ultron.ejecutar_comando_terminal("echo hola") == "Consola:\nhola"
    assert "Windows" in ultron.ejecutar_comando_terminal("ipconfig")


@requiere_skills
def test_habilidades_por_nombre_de_carpeta(ultron):
    assert _alias_habilidad("claude_pc/propias/web-playbook/SKILL.md") == "web-playbook"
    assert _alias_habilidad("claude_pc/propias/asesor-ventas/referencias/100m-offers.md") == "100m-offers"
    assert "verificada y cargada" in ultron.cargar_habilidad("web-playbook")
    assert "inválido" in ultron.cargar_habilidad("../main")
    assert "No se encontró" in ultron.cargar_habilidad("no-existe-esta-habilidad")


@requiere_skills
def test_listar_habilidades(ultron):
    assert "Categorías" in ultron.listar_habilidades()
    assert "hyperframes" in ultron.listar_habilidades("video")
    assert "No hay" in ultron.listar_habilidades("zzzz")


def test_fecha_hora_en_12_horas(ultron):
    assert re.search(r"son las \d{1,2}:\d{2} (AM|PM)\.$", ultron.obtener_fecha_hora())


@pytest.mark.parametrize("texto", ["dime la hora", "¿Qué hora es?", "qué fecha es hoy"])
def test_atajo_de_hora_sin_ia(ultron, monkeypatch, texto):
    monkeypatch.setattr(ultron, "_hablar_async", lambda t: None)
    ok, msg = ultron.manejar_pregunta_hora(texto)
    assert ok and re.search(r"\d{1,2}:\d{2} (AM|PM)", msg)


@pytest.mark.parametrize("texto", ["abre chrome", "hazme una página web sobre la historia de la hora en el mundo y los relojes antiguos"])
def test_atajo_de_hora_no_se_activa_en_otras_ordenes(ultron, texto):
    assert ultron.manejar_pregunta_hora(texto) is None
