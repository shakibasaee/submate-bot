# SubMate

[![Quality](https://github.com/shakibasaee/submate-bot/actions/workflows/quality.yml/badge.svg)](https://github.com/shakibasaee/submate-bot/actions/workflows/quality.yml)

SubMate is a Telegram bot that finds movie and TV subtitles and delivers them
directly in chat. It uses TMDb to identify the exact title or episode, searches
OpenSubtitles for English or Persian subtitles, and sends the selected result as
a validated SRT document.

The application is a typed, asynchronous Python service with explicit domain,
application, Telegram, and infrastructure boundaries. It can run as a lightweight
single process for local use or with PostgreSQL and Redis for a more durable
deployment.

## How it works

1. Start the bot and choose English or Persian.
2. Search for a movie or TV series.
3. Select the matching title. For TV, choose a season and episode.
4. Review ranked subtitle results and request more when available.
5. Select a subtitle and receive a validated `.srt` file in Telegram.

SubMate deliberately excludes TV Specials (Season 0). Subtitle files are downloaded
into memory, validated, and sent without being written to local storage.

## Highlights

- Combined movie and TV search through TMDb
- Season and episode navigation for television series
- English and Persian subtitle selection
- Ranked OpenSubtitles results with pagination
- Authenticated subtitle downloads with bounded token refresh
- SRT validation, archive rejection, and a 2 MiB file limit
- Safe filenames containing season and episode coordinates when relevant
- PostgreSQL-backed language preferences
- Redis-backed caching and rate limiting
- In-memory fallbacks for local development and degraded operation
- Structured JSON logs with credential redaction
- Liveness, readiness, and Prometheus-compatible metrics endpoints
- Docker Compose and Railway deployment configuration

## Current status

The installable baseline passes dependency validation, linting, formatting, static
type checking, and 92 automated tests on Python 3.13. The test suite covers movie
and episode workflows, provider authentication and errors, application lifecycle,
configuration, logging safety, and deployment configuration.

Automated provider tests use controlled test doubles. A green test run does not by
itself prove that live TMDb, OpenSubtitles, Telegram, PostgreSQL, or Redis services
are reachable from a particular deployment. Use the production smoke check and the
manual movie and episode checks described below before treating a deployment as
verified.

Conversation recovery after a failed or successful download is still limited. A
user may need to use `/start` or `/language` to begin another search. See
[Current limitations](#current-limitations) for the exact behavior.

## Quick start

### Requirements

- Python 3.12 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A TMDb API key from [TMDb API settings](https://www.themoviedb.org/settings/api)
- An OpenSubtitles API key, username, and password
- Network access to Telegram, TMDb, and OpenSubtitles

PostgreSQL and Redis are optional when running locally.

### Install

Clone the repository and enter it:

```bash
git clone https://github.com/shakibasaee/submate-bot.git
cd submate-bot
```

Create a virtual environment.

**Windows PowerShell**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

**Linux or macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Install the reviewed dependency set used by CI:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

For development without the lock file, the package can instead resolve the
declared version ranges:

```bash
python -m pip install -e ".[dev]"
```

### Configure

#### Obtain a TMDb API key

SubMate uses TMDb's v3 application authentication. To obtain the correct key:

1. Create or sign in to your [TMDb account](https://www.themoviedb.org/login) from
   a desktop browser.
2. Open **Account settings**, select **API**, and request a developer API key.
3. Accept the TMDb API terms and describe the SubMate application when prompted.
4. Copy the value labelled **API Key (v3 auth)**. SubMate sends this value as the
   `api_key` query parameter; do not substitute the longer API Read Access Token.
5. Store the key only in the ignored local `.env` file or your deployment platform's
   secret store.

TMDb documents the registration process in its official
[Getting Started guide](https://developer.themoviedb.org/docs/getting-started) and
[authentication guide](https://developer.themoviedb.org/docs/authentication-application).
Non-commercial API use is subject to TMDb's terms and attribution requirements.

#### Add the credentials

Open `.env` and replace the credential placeholders:

```dotenv
TELEGRAM_BOT_TOKEN=replace-with-your-bot-token
TMDB_API_KEY=replace-with-your-tmdb-api-key
OPENSUBTITLES_API_KEY=replace-with-your-opensubtitles-api-key
OPENSUBTITLES_USERNAME=replace-with-your-opensubtitles-username
OPENSUBTITLES_PASSWORD=replace-with-your-opensubtitles-password
```

The example file also contains local PostgreSQL and Redis URLs. Remove or comment
out `DATABASE_URL` and `REDIS_URL` unless those services are running and reachable.
For a health endpoint accessible only from the local machine, use:

```dotenv
HEALTH_HOST=127.0.0.1
```

Never commit `.env` or any other file containing credentials.

### Run

```bash
python -m app.main
```

Open the bot in Telegram and send `/start`. Only one polling process should use a
bot token at a time.

To verify the live TMDb path, choose a language and search for `Inception`. A result
showing the movie title and release year confirms that Telegram polling and TMDb
search are working together. This check does not verify subtitle search or delivery;
those require the three OpenSubtitles credentials as well.

## Telegram commands

| Command | Purpose |
| --- | --- |
| `/start` | Reset the current workflow and open the language picker. |
| `/language` | Choose or change the subtitle language. |
| `/cancel` | End the current workflow without forgetting the selected language. |
| `/privacy` | Show the privacy, copyright, and provider notice. |
| `/help` | List the available commands. |

## Configuration

Settings are defined in [`app/core/config.py`](app/core/config.py). SubMate reads
`.env` from the working directory, and process environment variables take
precedence. Setting names are case-insensitive and unknown settings are ignored.

### Credentials and services

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | BotFather token used for Telegram polling. |
| `TMDB_API_KEY` | For search | Enables movie and TV metadata lookup. |
| `OPENSUBTITLES_API_KEY` | For subtitles | Enables subtitle search and provider requests. |
| `OPENSUBTITLES_USERNAME` | For downloads | Authenticates OpenSubtitles downloads. |
| `OPENSUBTITLES_PASSWORD` | For downloads | Authenticates OpenSubtitles downloads. |
| `DATABASE_URL` | No | PostgreSQL connection used for language preferences. |
| `REDIS_URL` | No | Redis connection used for caches and rate limits. |

Only the Telegram token is required while loading configuration. Readiness requires
both provider API keys and the OpenSubtitles username and password.

### Runtime settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Environment label included in logs. |
| `LOG_LEVEL` | `INFO` | Application logging level. |
| `HEALTH_HOST` | `0.0.0.0` | Health and metrics listener address. |
| `HEALTH_PORT` | `8080` | Listener port; `PORT` is accepted when this is absent. |
| `TELEGRAM_TASKS_CONCURRENCY_LIMIT` | `100` | Maximum concurrent Telegram polling tasks. |
| `TMDB_CACHE_TTL_SECONDS` | `300` | TMDb cache lifetime. |
| `SUBTITLE_CACHE_TTL_SECONDS` | `120` | Subtitle-search cache lifetime. |
| `USER_SEARCH_LIMIT_PER_MINUTE` | `10` | Per-user title and subtitle search limit. |
| `GLOBAL_TMDB_LIMIT_PER_MINUTE` | `120` | Process-wide TMDb search limit. |
| `GLOBAL_SUBTITLE_LIMIT_PER_MINUTE` | `60` | Process-wide subtitle search limit. |
| `USER_DOWNLOAD_LIMIT_PER_10_MINUTES` | `5` | Per-user download-attempt limit. |
| `GLOBAL_DOWNLOAD_LIMIT_PER_MINUTE` | `20` | Process-wide download-attempt limit. |

All numeric settings must be positive. Application limits do not replace limits
enforced by external providers.

## Storage and fallback behavior

PostgreSQL stores only Telegram user IDs, selected subtitle languages, and update
timestamps. The preference table is created at startup, so the database must exist
and the configured user must be allowed to create the table.

Redis stores cached TMDb results, cached subtitle results, and rate-limit counters.
Raw title queries are hashed before being used in cache keys.

When PostgreSQL or Redis is omitted, SubMate uses in-memory implementations. If a
configured service fails during startup, the process falls back to memory and must
be restarted after the service is restored to reconnect. Preference writes made
during an outage are not replayed automatically.

Active conversations always remain in process memory. They expire lazily after 30
minutes and do not survive a restart.

## Docker Compose

The included [`compose.yaml`](compose.yaml) runs SubMate with PostgreSQL 17 and
Redis 8. The databases use persistent named volumes and are not exposed on host
ports. The bot runs as a non-root user with a read-only root filesystem.

Create and edit the production environment file:

```powershell
Copy-Item .env.production.example .env.production
```

Then build and start the stack:

```bash
docker compose --env-file .env.production build --pull
docker compose --env-file .env.production up -d
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs --tail=100 bot
```

Stop the stack while retaining stored data:

```bash
docker compose --env-file .env.production down
```

Do not add `--volumes` unless you intend to delete the PostgreSQL and Redis data.
See [`DEPLOYMENT.md`](DEPLOYMENT.md) for VPS and Railway procedures, backups,
restoration, upgrades, and rollback.

## Verification and observability

| Endpoint | Meaning |
| --- | --- |
| `GET /health/live` | The HTTP listener and process are alive. |
| `GET /health/ready` | Dependencies are reachable and provider credentials are configured. |
| `GET /metrics` | Prometheus-compatible counters for process and bot events. |

Keep these endpoints on a private network or behind access controls.

Run the production smoke check from a configured environment:

```bash
python -m scripts.production_smoke
```

The check constructs the real application runtime, checks attached dependencies,
verifies provider configuration, and authenticates with Telegram. It does not call
TMDb or OpenSubtitles and does not send a document.

Complete verification requires two manual Telegram workflows:

1. Search for a movie, choose a subtitle, receive it, and open the SRT.
2. Search for a series, choose a season and episode, receive the subtitle, and
   confirm the filename contains the expected `SxxExx` and language code.

Record results without storing tokens, passwords, temporary provider links, chat
identifiers, or downloaded copyrighted files in the repository. The current
evidence is maintained in [`INTEGRATION_CHECKLIST.md`](INTEGRATION_CHECKLIST.md).

## Architecture

SubMate follows dependency inversion. Domain and application code define the
rules and ports; Telegram, TMDb, OpenSubtitles, PostgreSQL, and Redis are adapters.
[`app/bootstrap.py`](app/bootstrap.py) is the single composition root and owns the
shared HTTP session and deterministic shutdown.

```text
app/
  main.py                 Process lifecycle and Telegram polling
  bootstrap.py            Dependency construction and cleanup
  domain/                 Media, language, subtitle, and error models
  application/
    ports/                Provider, metadata, storage, and rate-limit interfaces
    use_cases/            Search, selection, navigation, delivery, cancellation
  bot/                    Telegram handlers, keyboards, and presenters
  infrastructure/         TMDb, OpenSubtitles, PostgreSQL, Redis, memory adapters
  core/                   Settings, logging, retries, health, and metrics
scripts/
  production_smoke.py     Runtime and Telegram authentication check
tests/                    Unit, integration-style, security, and lifecycle tests
```

Handlers translate Telegram updates and render outcomes; they do not construct
providers, access databases, choose cache keys, or implement business workflows.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the dependency diagram and enforced
layer rules.

## Development

Install the development dependencies, then run the same checks used by CI:

```bash
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pyright
python -m pytest --cov=app --cov-report=term-missing --cov-report=xml
```

The [Quality workflow](.github/workflows/quality.yml) runs these checks for pull
requests and pushes to `main` and uploads the XML coverage report.

Use a short-lived branch, open a pull request to `main`, and merge only after the
Quality workflow passes. Tag reviewed releases using semantic versioning.

## Current limitations

- SubMate supports one polling process. Conversation state and per-user locks are
  process-local, so Redis does not make multiple bot replicas safe.
- Failed provider downloads do not yet restore the previous subtitle choices.
  Successful delivery also leaves the workflow in a delivery state. Use `/start`
  or `/language` to begin another search.
- OpenSubtitles is the only subtitle provider. English and Persian are the only
  selectable languages.
- Only validated SRT content up to 2 MiB is accepted. Archive extraction and
  automatic subtitle synchronization are not supported.
- The container and deployment tests validate configuration statically. Real
  credentials, external providers, databases, restart behavior, and Telegram file
  delivery must still be verified in the target environment.

## Privacy, security, and copyright

Search text is sent to TMDb. Subtitle requests send media identifiers, language,
and episode coordinates to OpenSubtitles. PostgreSQL stores language preferences,
not search history. Logs redact recognized credential fields and patterns.

Keep secrets in ignored environment files or the deployment platform's secret
store. Never commit credentials, downloaded subtitles, databases, caches, or logs.

Subtitles remain copyrighted by their respective authors. Delivered files include
OpenSubtitles attribution and uploader attribution when available. Review
[`SECURITY.md`](SECURITY.md) for dependency maintenance, credential rotation,
privacy, and operator responsibilities.
