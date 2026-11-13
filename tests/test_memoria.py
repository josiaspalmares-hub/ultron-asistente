"""Memoria de la bóveda en el system prompt: tope, aviso de notas que no caben y recarga al cambiar."""
import pytest


@pytest.fixture
def wiki(ultron, tmp_path, monkeypatch):
    carpeta = tmp_path / "boveda" / "wiki"
    carpeta.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return carpeta


def test_aviso_cuando_no_cabe_todo(ultron, wiki, monkeypatch):
    monkeypatch.setattr(ultron, "_MAX_MEMORIA_TOTAL", 3000)
    for n in range(4):
        (wiki / f"nota{n}.md").write_text(f"nota {n} " + "x" * 1500, encoding="utf-8")
    texto = ultron.cargar_memoria_boveda()
    assert "nota3.md" in texto.split("NO CABEN COMPLETAS")[1]
    assert "buscar_en_boveda" in texto


def test_sin_aviso_si_cabe_todo(ultron, wiki):
    (wiki / "corta.md").write_text("Goldhour", encoding="utf-8")
    texto = ultron.cargar_memoria_boveda()
    assert "Goldhour" in texto and "NO CABEN" not in texto


def test_recarga_cuando_cambia_una_nota(ultron, wiki, monkeypatch):
    creados = []
    monkeypatch.setattr(ultron, "crear_chat", lambda clave, historial=None: creados.append(1) or None)
    monkeypatch.setattr(ultron, "chat", None)
    (wiki / "a.md").write_text("primera versión", encoding="utf-8")
    monkeypatch.setattr(ultron, "_firma_memoria", ultron.firma_memoria_boveda())
    ultron._refrescar_memoria_si_cambio()
    assert not creados
    (wiki / "a.md").write_text("segunda versión con el dato nuevo", encoding="utf-8")
    ultron._refrescar_memoria_si_cambio()
    assert creados and "dato nuevo" in ultron.system_prompt
