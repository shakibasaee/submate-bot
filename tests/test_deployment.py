"""Static production-deployment configuration tests."""

import tomllib
from pathlib import Path

import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_railway_config_uses_dockerfile_healthcheck_and_restart_policy() -> None:
    config = tomllib.loads((ROOT / "railway.toml").read_text(encoding="utf-8"))

    assert config["build"] == {"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"}
    assert config["deploy"]["healthcheckPath"] == "/health/ready"
    assert config["deploy"]["restartPolicyType"] == "ON_FAILURE"
    assert config["deploy"]["restartPolicyMaxRetries"] == 10


def test_compose_provisions_bot_postgres_redis_health_and_persistence() -> None:
    config = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = config["services"]

    assert set(services) == {"bot", "postgres", "redis"}
    assert services["bot"]["restart"] == "unless-stopped"
    assert services["bot"]["read_only"] is True
    assert services["bot"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["bot"]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert services["postgres"]["volumes"] == ["postgres-data:/var/lib/postgresql/data"]
    assert services["redis"]["volumes"] == ["redis-data:/data"]
    assert set(config["volumes"]) == {"postgres-data", "redis-data"}


def test_dockerfile_runs_non_root_and_contains_no_secret_values() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'CMD ["python", "-m", "app.main"]' in dockerfile
    assert "TELEGRAM_BOT_TOKEN=" not in dockerfile
    assert "TMDB_API_KEY=" not in dockerfile
    assert "OPENSUBTITLES_API_KEY=" not in dockerfile


def test_railway_port_variable_controls_health_listener() -> None:
    settings = Settings(
        telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz",
        PORT=9090,
    )

    assert settings.health_port == 9090
