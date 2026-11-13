from cryptography.fernet import Fernet

import respaldo_boveda as rb


def _preparar(tmp_path, monkeypatch, clave):
    boveda = tmp_path / "boveda"
    (boveda / "wiki").mkdir(parents=True)
    (boveda / "wiki" / "nota.md").write_text("Goldhour negro mate y oro", encoding="utf-8")
    monkeypatch.setattr(rb, "BOVEDA", boveda)
    monkeypatch.setattr(rb, "HUELLA", boveda / ".huella_respaldo")
    monkeypatch.setattr(rb, "ARCHIVO_CIFRADO", tmp_path / "respaldo" / "boveda.enc")
    monkeypatch.setattr(rb, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv(rb.NOMBRE_CLAVE, clave)
    return boveda


def test_cifra_restaura_y_no_repite(tmp_path, monkeypatch):
    boveda = _preparar(tmp_path, monkeypatch, Fernet.generate_key().decode())
    assert "actualizado" in rb.cifrar_boveda()
    assert b"Goldhour" not in rb.ARCHIVO_CIFRADO.read_bytes()
    assert "sin cambios" in rb.cifrar_boveda()
    destino = tmp_path / "restaurada"
    assert "restaurada" in rb.restaurar_boveda(destino)
    assert (destino / "wiki" / "nota.md").read_text(encoding="utf-8") == "Goldhour negro mate y oro"
    (boveda / "wiki" / "nota.md").write_text("cambio", encoding="utf-8")
    assert "actualizado" in rb.cifrar_boveda()


def test_clave_equivocada_no_abre(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, Fernet.generate_key().decode())
    rb.cifrar_boveda()
    monkeypatch.setenv(rb.NOMBRE_CLAVE, Fernet.generate_key().decode())
    assert "no corresponde" in rb.restaurar_boveda(tmp_path / "x")


def test_sin_clave_no_cifra(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, "")
    assert "sin ULTRON_BOVEDA_KEY" in rb.cifrar_boveda()
