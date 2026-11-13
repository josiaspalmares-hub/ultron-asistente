"""Las pruebas importan main.py una sola vez (necesita el .env con claves; no llama a Gemini)."""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Sin .env (por ejemplo, recién descargado de GitHub) las pruebas usan claves falsas: nunca llaman a Gemini ni a Telegram.
if not (RAIZ / ".env").exists():
    os.environ.setdefault("GEMINI_API_KEY", "AIzaSyClaveFalsaSoloParaPruebas000000000")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:ClaveFalsaSoloParaPruebasDeTelegram00")
    os.environ.setdefault("TELEGRAM_ALLOWED_USER_ID", "111111111")

# Las skills son copias privadas y no vienen en el repositorio público
requiere_skills = pytest.mark.skipif(
    not (RAIZ / "skills_seguras_ultron").exists(), reason="sin la carpeta skills_seguras_ultron"
)


@pytest.fixture(scope="session")
def ultron():
    import main
    return main
