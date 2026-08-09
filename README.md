# Subtitle Telegram Bot

A Telegram bot that will search approved subtitle providers and send selected subtitle files.

## Phase 1: run locally

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. Create your local configuration file, unless one was already created for you:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Put the token in `TELEGRAM_BOT_TOKEN` in `.env`.
   Add your TMDb API key as `TMDB_API_KEY` too. Create it from the
   [TMDb API settings](https://www.themoviedb.org/settings/api).
4. Install dependencies and run:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   python -m app.main
   ```

   For a reproducible reviewed environment, install `requirements.lock` first,
   then install the local package without resolving dependencies:

   ```powershell
   python -m pip install -r requirements.lock
   python -m pip install --no-deps -e .
   ```

5. Open the bot in Telegram and send `/start`.

## Commands

`/start` opens a subtitle-language picker. Choose either English or فارسی,
then send the name of a movie or TV series.

TMDb searches return up to five movie and TV matches together. The title buttons
include a type icon and release year where TMDb supplies one.

For TV series, the bot loads available TMDb seasons, deliberately excludes
Specials (Season 0), and then loads the episodes for the selected season. Back
returns to the season picker and Cancel ends the current action.

Add `OPENSUBTITLES_API_KEY` to `.env` to enable subtitle search. The bot shows
ranked, paged OpenSubtitles choices. A selected `.srt` is retrieved through a
temporary provider link, size- and format-validated, sent as a Telegram document,
and deleted from local temporary storage immediately after the send completes.
Archives and non-SRT content are rejected. Delivery messages attribute
OpenSubtitles and the uploader when one is supplied.

## PostgreSQL, Redis, and limits

Set `DATABASE_URL` to persist only Telegram user IDs, selected language, and an
update timestamp in PostgreSQL. Set `REDIS_URL` to cache TMDb results for five
minutes and OpenSubtitles search results for two minutes by default. Cache keys
hash user-entered title queries rather than storing that text in Redis keys.

Redis also applies per-user and process-wide fixed-window limits to title
searches, subtitle searches, and downloads. If Redis is unavailable, API calls
continue without caching and conservative in-process limits remain active. If
PostgreSQL is unavailable, language preferences remain available for the life of
the bot process. All TTLs and limits shown in `.env.example` are configurable.

- `/language` changes the selected subtitle language.
- `/cancel` ends the current title-entry action without forgetting the
  selected language.
- `/privacy` shows the privacy, copyright, and provider-attribution notice.

## Reliability

Logs are structured JSON and redact sensitive fields and credential patterns.
The process exposes `/health/live`, `/health/ready`, and `/metrics` on port 8080
by default. See [OPERATIONS.md](OPERATIONS.md) for alert suggestions and failure
behavior, and [SECURITY.md](SECURITY.md) for dependency updates, secret rotation,
privacy, and copyright responsibilities.

## Production deployment

Production assets include a non-root [Dockerfile](Dockerfile), a PostgreSQL and
Redis [Compose stack](compose.yaml), and Railway config-as-code in
[railway.toml](railway.toml). See [DEPLOYMENT.md](DEPLOYMENT.md) for the small-VPS
runbook, Railway variables, health and Telegram smoke tests, backups, logs,
upgrades, and rollback.

## Checks

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pyright
python -m pytest --cov=app --cov-report=term-missing --cov-report=xml
python -m pip check
```

Never commit `.env`, downloaded subtitles, local databases, logs, or caches; they are
ignored by Git.

## Branches and releases

- `main` is the protected, releasable branch. Direct changes should be avoided.
- Create short-lived branches as `feature/<topic>`, `fix/<topic>`, or
  `chore/<topic>`.
- Open a pull request to `main`; it must pass the Quality workflow before merge.
- Tag approved releases from `main` using semantic versioning, for example `v0.1.0`.
