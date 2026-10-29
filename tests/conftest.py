"""Keep automated tests independent of the operator's local credentials and mode."""

import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolate_local_dotenv(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
