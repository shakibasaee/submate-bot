# SubMate

A Telegram bot for finding movie and TV subtitles and receiving them directly in chat. SubMate uses **TMDb** to identify titles and episodes, then searches **OpenSubtitles** for English or Persian subtitles and sends the selected SRT as a Telegram document.

The application runs as a single Python process using Telegram long polling. PostgreSQL and Redis are optional for local development; the included Docker Compose stack provisions both for deployment.

[Quick start](#quick-start) · [Configuration](#configuration) · [Docker Compose](#docker-compose) · [Development](#development) · [Limitations](#current-limitations)

## Features

- **Movie and TV search:** up to five combined TMDb matches, with media type and release year when available.
- **Episode navigation:** choose a series, season, and episode, with Back and Cancel controls. Season 0 / Specials are excluded.
- **English and Persian subtitles:** select a language before searching and optionally persist the preference in PostgreSQL.
- **Ranked subtitle choices:** results prioritize SRT format, then rating and download count, and appear in pages of five.
- **In-memory file delivery:** downloads are limited to 2 MiB and validated as SRT; empty files, archives, and invalid content are rejected. Delivery includes OpenSubtitles attribution and the uploader when supplied.
- **Provider protection:** configurable caching, per-user and global fixed-window rate limits, bounded retries, and normalized provider errors.
- **Operational visibility:** structured JSON logs with sensitive-data redaction, health endpoints, and Prometheus-compatible metrics.

## Quick start

### Prerequisites

- **Python 3.12 or newer.** The CI workflow and Docker image use Python 3.13.
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- A TMDb API key for title search, available through [TMDb API settings](https://www.themoviedb.org/settings/api).
- An OpenSubtitles API key plus account username and password for the full search-and-download workflow.
- Network access to Telegram, TMDb, and OpenSubtitles.

Run the following commands from the repository root. Docker is only needed for the container setup below.

### 1. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Copy the template only if you do not already have a `.env` file.

### 2. Install dependencies

Use the pinned dependency set used by CI and Docker. It includes the development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

Alternatively, to resolve dependencies from the version ranges in `pyproject.toml`:

```bash
python -m pip install -e ".[dev]"
```

### 3. Configure credentials

Edit `.env` and replace the five Telegram, TMDb, and OpenSubtitles credential placeholders.

For a local run without PostgreSQL or Redis, **remove or comment out `DATABASE_URL` and `REDIS_URL`** in the copied template. The template contains localhost connection URLs, but does not start those services. Omit unused settings rather than assigning empty strings.

For local-only health access, set:

```dotenv
HEALTH_HOST=127.0.0.1
```

### 4. Start the bot

```bash
python -m app.main
```

Open your bot in Telegram and send `/start`. Keep only one polling instance running for the bot token; stop the local process before starting the Compose bot.

## Using the bot

1. Send `/start` and choose **English** or **Persian (فارسی)**.
2. Enter a movie or TV title using at least two characters.
3. Select a title. For TV, choose a season and then an episode.
4. Choose a subtitle, or request more results when available.
5. Receive the SRT document with provider attribution.

Use `/start` or `/language` and choose a language again to begin another search.

| Command | Purpose |
| --- | --- |
| `/start` | Reset the current workflow and open the language picker. |
| `/language` | Choose or change the subtitle language and begin a search. |
| `/cancel` | End the current workflow without forgetting its selected language. |
| `/privacy` | Show the privacy, copyright, and provider notice. |
| `/help` | List available commands. |

## Configuration

Settings are defined in [`app/core/config.py`](app/core/config.py). The application reads `.env` from the working directory; environment variables take precedence. Names are case-insensitive and unknown settings are ignored.

### Credentials and services

| Variable | Default | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Required | BotFather token. Missing, blank, or example tokens fail validation. |
| `TMDB_API_KEY` | Unset | Enables movie/TV metadata search. |
| `OPENSUBTITLES_API_KEY` | Unset | Enables the OpenSubtitles provider. |
| `OPENSUBTITLES_USERNAME` | Unset | Account username for authenticated downloads. |
| `OPENSUBTITLES_PASSWORD` | Unset | Account password for authenticated downloads. |
| `DATABASE_URL` | Unset | PostgreSQL connection URL for language preferences. |
| `REDIS_URL` | Unset | Redis connection URL for cache and rate-limit state. |

Only the Telegram token is mandatory at configuration load time. Missing provider credentials disable the corresponding functionality; readiness requires both provider API keys and the OpenSubtitles username/password to be configured.

### Runtime and limits

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Environment label included in startup logs. |
| `LOG_LEVEL` | `INFO` | Logging level. |
| `HEALTH_HOST` | `0.0.0.0` | Health/metrics listener address. |
| `HEALTH_PORT` | `8080` | Listener port; `PORT` is accepted when `HEALTH_PORT` is absent. |
| `TELEGRAM_TASKS_CONCURRENCY_LIMIT` | `100` | Concurrent Telegram polling tasks. |
| `TMDB_CACHE_TTL_SECONDS` | `300` | Metadata cache lifetime. |
| `SUBTITLE_CACHE_TTL_SECONDS` | `120` | Subtitle-search cache lifetime. |
| `USER_SEARCH_LIMIT_PER_MINUTE` | `10` | Per-user limit, applied separately to title and subtitle searches. |
| `GLOBAL_TMDB_LIMIT_PER_MINUTE` | `120` | Global title-search limit. |
| `GLOBAL_SUBTITLE_LIMIT_PER_MINUTE` | `60` | Global subtitle-search limit. |
| `USER_DOWNLOAD_LIMIT_PER_10_MINUTES` | `5` | Per-user download-attempt limit. |
| `GLOBAL_DOWNLOAD_LIMIT_PER_MINUTE` | `20` | Global download-attempt limit. |

All numeric settings listed above must be positive. Application limits do not replace provider quotas.

### Storage and fallback behavior

- **PostgreSQL** stores only Telegram user IDs, subtitle languages, and update timestamps in `user_preferences`. The application creates the table on startup, so the database must already exist and the connecting user needs permission to create the table. There is no migration framework or separate migration command.
- **Redis** stores cached metadata, subtitle search results, and rate-limit counters. Title-search cache keys hash the entered query rather than placing raw query text in the key.
- **Without these services**, preferences, caching, and limits use process memory and disappear on restart.
- **If a service fails during startup**, the bot selects its memory fallback for that process lifetime. Restart after restoring the service to reconnect it.
- **After a successful connection**, PostgreSQL preference operations fall back to memory on handled failures; Redis cache errors become cache misses and rate limits fall back to memory. Preference writes made during an outage are not automatically replayed to PostgreSQL.

Active conversations always remain in memory, even with PostgreSQL and Redis enabled. They expire lazily after 30 minutes without a saved workflow update and are lost on restart.

## Docker Compose

The included [`compose.yaml`](compose.yaml) starts the bot, **PostgreSQL 17**, and **Redis 8** with persistent named volumes. Install Docker with the Compose plugin, then create the production configuration:

```powershell
# Windows PowerShell
Copy-Item .env.production.example .env.production
```

```bash
# Linux / macOS
cp .env.production.example .env.production
chmod 600 .env.production
```

Replace every credential placeholder. Set `POSTGRES_PASSWORD` to a long URL-safe value, such as letters and digits, because Compose inserts it into the database URL. `POSTGRES_USER` and `POSTGRES_DB` default to `subtitle_bot`. The optional `APP_VERSION` value sets the local image tag and build version label; its Compose default is `local`.

Build and start:

```bash
docker compose --env-file .env.production build --pull
docker compose --env-file .env.production up -d
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs --tail=100 bot
```

Compose supplies the internal `DATABASE_URL` and `REDIS_URL` automatically, waits for database health checks, and runs the bot as a non-root user with a read-only root filesystem. PostgreSQL and Redis have no published host ports. The bot's health port is published on host loopback only, at `127.0.0.1:8080` by default.

For a Python process running directly on your host, use separately accessible PostgreSQL/Redis services and configure their URLs; the unmodified Compose stack does not expose its databases to the host.

Stop the stack while retaining data:

```bash
docker compose --env-file .env.production down
```

Adding `--volumes` deletes the persistent database/cache volumes.

## Health checks and deployment

| Endpoint | What it checks |
| --- | --- |
| `GET /health/live` | The HTTP listener is responding. |
| `GET /health/ready` | Attached PostgreSQL/Redis clients are reachable and provider credentials are configured; returns `503` when degraded. |
| `GET /metrics` | Prometheus-compatible process and event counters. |

Readiness does **not** authenticate provider credentials or test Telegram delivery. Services omitted or abandoned for memory fallback at startup are reported as `disabled`, so readiness alone does not guarantee persistent storage is active. Keep health and metrics access on a private network or behind access controls.

With the bot running, inspect health using PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health/live
Invoke-RestMethod http://127.0.0.1:8080/health/ready
```

Or Linux/macOS:

```bash
curl --fail http://127.0.0.1:8080/health/live
curl --fail http://127.0.0.1:8080/health/ready
```

Run the production smoke check from the configured repository environment:

```bash
python -m scripts.production_smoke
```

Or inside the Compose bot:

```bash
docker compose --env-file .env.production exec bot python -m scripts.production_smoke
```

The smoke script constructs the application runtime, checks its attached dependencies and provider configuration, and authenticates with Telegram through `getMe`. It does not call TMDb/OpenSubtitles or send a document. Complete a manual movie and TV-episode search through SRT delivery to verify the full integration.

[`railway.toml`](railway.toml) also configures Dockerfile builds, `/health/ready`, and an on-failure restart policy. Use one replica and supply provider credentials and database URLs through the deployment environment. Railway's `PORT` is supported; leave `HEALTH_PORT` unset when relying on it.

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the VPS/Railway runbooks, backups, restore, upgrades, and rollback, and [`OPERATIONS.md`](OPERATIONS.md) for monitoring and suggested alerts.

## Architecture and technology

SubMate separates domain models, application workflows, Telegram presentation, and external adapters. Dependencies point toward domain/application interfaces; [`app/bootstrap.py`](app/bootstrap.py) assembles the runtime, shares one HTTP session among provider adapters, and owns their shutdown. Architecture tests enforce the layer boundaries.

| Area | Technology |
| --- | --- |
| Runtime and packaging | Python, asyncio, Hatchling |
| Telegram | aiogram 3, long polling |
| HTTP and health server | aiohttp |
| Configuration and logging | pydantic-settings, structlog |
| Persistence and caching | PostgreSQL via Psycopg 3, redis-py, in-memory fallbacks |
| Quality tooling | pytest, pytest-cov, Ruff, Pyright |
| Deployment | Docker, Docker Compose, Railway configuration |

```text
app/
  main.py                 Long-polling entry point and process lifecycle
  bootstrap.py            Dependency construction and cleanup
  domain/                 Media, languages, subtitles, and error models
  application/
    ports/                Provider, metadata, storage, and limit interfaces
    use_cases/            Search, selection, navigation, delivery, cancellation
  bot/                    Telegram handlers, keyboards, and presenters
  infrastructure/         TMDb/OpenSubtitles adapters, persistence, and caching
  core/                   Settings, logging, retries, health, and metrics
scripts/
  production_smoke.py     Runtime and Telegram authentication check
tests/                    Workflow, adapter, security, lifecycle, and config tests
.github/workflows/        Quality workflow
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the dependency diagram and workflow model. Package metadata lives in [`pyproject.toml`](pyproject.toml); exact dependency pins live in [`requirements.lock`](requirements.lock).

## Development

With the virtual environment active and development dependencies installed:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pyright
python -m pip check
```

Generate the coverage reports used by CI:

```bash
python -m pytest --cov=app --cov-report=term-missing --cov-report=xml
```

The [Quality workflow](.github/workflows/quality.yml) runs dependency checks, lint, formatting, type checks, and tests on pull requests and pushes to `main`, then uploads `coverage.xml`. The suite uses test doubles for external integrations; passing it does not establish live-provider or container deployment success.

Use short-lived branches such as `feature/<topic>`, `fix/<topic>`, or `chore/<topic>`, open a pull request to `main`, and pass the Quality checks before merging. Tag reviewed releases using semantic versioning, for example `v0.1.0`.

## Current limitations

- **Single instance:** long polling, conversation storage, and per-user locks are designed for one bot process. Redis does not make multiple bot replicas supported.
- **Delivery recovery is incomplete:** selection consumes the candidate list and enters `DELIVERING`. Provider-download or Telegram-send failures do not restore the choices, and successful delivery does not transition back to title entry. Use `/start` or `/language`, choose a language, and search again. Failed attempts can count toward rate limits.
- **Provider and format scope:** OpenSubtitles is the only implemented subtitle provider; English and Persian are the only selectable languages. Delivery accepts validated SRT content up to 2 MiB, without archive extraction. TV Specials are not listed.
- **Deployment verification is separate:** checked-in container/configuration tests are static checks. Real credentials, provider access, database connectivity, and end-to-end delivery must be validated in the target environment.

## Privacy and security

Keep credentials in environment variables or ignored local environment files. Never commit secrets, downloaded subtitles, local databases, logs, or caches. Search text is sent to TMDb for lookup; subtitle requests use media identifiers, language, and episode coordinates. PostgreSQL persists language preferences rather than search history.

Subtitles remain copyrighted by their respective authors. Deliveries include OpenSubtitles attribution and uploader attribution when available. See [`SECURITY.md`](SECURITY.md) for secret rotation, dependency maintenance, privacy, and operator responsibilities.
