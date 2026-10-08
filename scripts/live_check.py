"""Secret-safe live provider checks. Downloads stay in memory and consume quota."""

import asyncio
import json

from aiogram import Bot

from app.bootstrap import build_runtime
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.languages import LanguageCode
from app.domain.models import MediaType, MovieRef, SeriesRef
from app.domain.subtitles import SubtitleQuery
from app.infrastructure.cache.memory import InMemoryCache
from app.infrastructure.metadata.tmdb import TmdbMetadataGateway
from app.infrastructure.providers.opensubtitles import OpenSubtitlesProvider


def report(check: str, status: str) -> None:
    print(json.dumps({"check": check, "status": status}))


async def run() -> None:
    settings = get_settings()
    configure_logging("WARNING")
    configured = True
    for name in (
        "telegram_bot_token",
        "tmdb_api_key",
        "opensubtitles_api_key",
        "opensubtitles_username",
        "opensubtitles_password",
    ):
        secret = getattr(settings, name)
        if (
            secret is None
            or not secret.get_secret_value().strip()
            or secret.get_secret_value().startswith("replace-")
        ):
            report(name.upper(), "missing: enter locally in ignored .env")
            configured = False
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    try:
        identity = await asyncio.wait_for(bot.get_me(), 20)
        report(
            "telegram",
            "authenticated target"
            if identity.username and identity.username.casefold() == "sub_mate_bot"
            else "wrong bot: do not start polling",
        )
        info = await bot.get_webhook_info()
        report("telegram_webhook", "active: polling must not start" if info.url else "absent")
    except Exception as error:
        report("telegram", type(error).__name__)
    finally:
        await bot.session.close()
    runtime = await build_runtime(settings)
    try:
        if settings.tmdb_api_key is None:
            return
        metadata = TmdbMetadataGateway(
            runtime.http_session, settings.tmdb_api_key.get_secret_value(), InMemoryCache()
        )
        try:
            movies = await metadata.search("Inception")
            report("tmdb", "search succeeded" if movies else "empty results")
        except Exception as error:
            status = {
                "TMDb rejected the configured API key or access.": "credentials/access rejected",
                "TMDb is temporarily unavailable": "network/provider unavailable",
                "TMDb request failed": "HTTP request rejected",
            }.get(str(error), type(error).__name__)
            report("tmdb", status)
            return
        if not configured:
            return
        assert settings.opensubtitles_api_key is not None
        assert settings.opensubtitles_username is not None
        assert settings.opensubtitles_password is not None
        provider = OpenSubtitlesProvider(
            runtime.http_session,
            settings.opensubtitles_api_key.get_secret_value(),
            InMemoryCache(),
            username=settings.opensubtitles_username.get_secret_value(),
            password=settings.opensubtitles_password.get_secret_value(),
        )
        movie = next(
            item for item in movies if item.media_type is MediaType.MOVIE and item.year == "2010"
        )
        series_results = await metadata.search("Breaking Bad")
        series_item = next(item for item in series_results if item.media_type is MediaType.TV)
        series = SeriesRef(series_item.external_id, series_item.title, series_item.year)
        episodes = await metadata.episodes(series, 1)
        episode = next(item for item in episodes if item.episode_number == 1)
        for label, media in (
            ("movie", MovieRef(movie.external_id, movie.title, movie.year)),
            ("episode", episode),
        ):
            try:
                choices = await provider.search(SubtitleQuery(media, LanguageCode.ENGLISH))
                candidate = next((item for item in choices if item.format == "srt"), None)
                if candidate is None:
                    report(label, "no SRT candidates")
                    continue
                downloaded = await provider.download(candidate)
                report(
                    label,
                    "authenticated download; validated SRT in memory"
                    if downloaded.content
                    else "empty",
                )
            except Exception as error:
                report(label, type(error).__name__)
    finally:
        await runtime.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as error:
        report("live_check", type(error).__name__)
