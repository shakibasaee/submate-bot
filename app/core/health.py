"""Lightweight liveness, readiness, and metrics HTTP server."""

from collections.abc import Awaitable, Callable

import structlog
from aiohttp import web

from app.core.config import Settings
from app.core.monitoring import monitoring

logger = structlog.get_logger(__name__)


class HealthServer:
    """Expose probes without including configuration values or secrets."""

    def __init__(
        self,
        settings: Settings,
        dependency_health: Callable[[], Awaitable[dict[str, str | bool]]],
    ) -> None:
        self.host = settings.health_host
        self.port = settings.health_port
        self.providers_configured = {
            "tmdb": settings.tmdb_api_key is not None
            and not settings.tmdb_api_key.get_secret_value().startswith("replace-"),
            "opensubtitles": settings.opensubtitles_api_key is not None
            and not settings.opensubtitles_api_key.get_secret_value().startswith("replace-"),
        }
        self._dependency_health = dependency_health
        self._runner: web.AppRunner | None = None

    async def live(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def ready(self, _request: web.Request) -> web.Response:
        dependency_health = await self._dependency_health()
        providers_ready = all(self.providers_configured.values())
        ready = dependency_health.pop("ready") and providers_ready
        payload = {
            "status": "ready" if ready else "degraded",
            "dependencies": dependency_health,
            "providers": {
                name: "configured" if configured else "missing"
                for name, configured in self.providers_configured.items()
            },
        }
        return web.json_response(payload, status=200 if ready else 503)

    async def metrics(self, _request: web.Request) -> web.Response:
        return web.Response(text=monitoring.render(), content_type="text/plain")

    async def start(self) -> None:
        app = web.Application()
        app.add_routes(
            [
                web.get("/health/live", self.live),
                web.get("/health/ready", self.ready),
                web.get("/metrics", self.metrics),
            ]
        )
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port, shutdown_timeout=5)
        await site.start()
        logger.info("health_server_started", host=self.host, port=self.port)

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
