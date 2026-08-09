# Deployment and ongoing operations

The stable long-term deployment is one bot container plus PostgreSQL and Redis.
Run exactly one bot replica: Telegram long polling and the current in-process
conversation state are not designed for multiple replicas.

## Production container

The image installs the reviewed `requirements.lock`, runs as UID/GID 10001,
uses a read-only root filesystem under Compose, writes temporary subtitles only
to `/tmp`, and exposes the Phase 8 health server. Secrets are runtime environment
variables and never Docker build arguments or image layers.

## Docker Compose on a small VPS

Recommended baseline: a supported Linux distribution, Docker Engine with the
Compose plugin, 1 GB RAM, one CPU, encrypted provider storage, automatic OS
security updates, and SSH key authentication. The bot uses outbound Telegram and
provider HTTPS connections; the health port binds to loopback and need not be
opened in the firewall.

1. Copy the production environment template and replace every placeholder:

   ```bash
   cp .env.production.example .env.production
   chmod 600 .env.production
   ```

   Use a long URL-safe PostgreSQL password containing letters and digits. Compose
   places it in `DATABASE_URL`; reserved URL characters must otherwise be
   percent-encoded. Never commit `.env.production`.

2. Build, start, and inspect the three services:

   ```bash
   docker compose --env-file .env.production build --pull
   docker compose --env-file .env.production up -d
   docker compose --env-file .env.production ps
   docker compose --env-file .env.production logs --tail=100 bot
   ```

   Compose provisions PostgreSQL and Redis with named volumes, waits for their
   health checks, and starts the bot with `restart: unless-stopped`. PostgreSQL is
   authoritative; Redis AOF improves restart behavior but Redis remains
   disposable cache/rate-limit state.

3. Verify production health and real Telegram authentication:

   ```bash
   curl --fail http://127.0.0.1:8080/health/live
   curl --fail http://127.0.0.1:8080/health/ready
   docker compose --env-file .env.production exec bot \
     python -m scripts.production_smoke
   ```

4. Open the bot in Telegram and perform the real user test: send `/start`, select
   both languages in turn, search a known movie and TV episode, select an SRT,
   confirm the document and attribution arrive, and check that no temporary file
   remains:

   ```bash
   docker compose --env-file .env.production exec bot \
     sh -c 'find /tmp -maxdepth 1 -name "subtitle-*.srt" -print'
   ```

   The final command should print nothing.

## Railway

Railway detects the root `Dockerfile`; `railway.toml` selects the Dockerfile
builder, `/health/ready`, a five-minute deployment-health timeout, and an
on-failure restart policy.

1. Create an empty Railway project and add managed PostgreSQL and Redis services.
   Managed databases are preferred there because Railway provides connection
   variables, backups, and operational dashboards.
2. Add this GitHub repository as one service and keep it at one replica.
3. Add these secret variables to the bot service:

   ```text
   TELEGRAM_BOT_TOKEN
   TMDB_API_KEY
   OPENSUBTITLES_API_KEY
   APP_ENV=production
   LOG_LEVEL=INFO
   HEALTH_HOST=0.0.0.0
   ```

4. Add Railway reference variables rather than copying credentials:

   ```text
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   ```

   Adjust `Postgres` and `Redis` if the Railway service names differ. Railway
   injects `PORT`; the application accepts it automatically for the health
   listener. Generate a public domain so Railway can reach the health endpoint.
5. Deploy from the dashboard or with `railway up`, inspect deploy logs, confirm
   `/health/ready` is 200, then open a Railway shell and run:

   ```bash
   python -m scripts.production_smoke
   ```

6. Complete the same manual Telegram `/start` through delivery test described
   above. Railway deployment health checks run during deployment only, so use an
   external uptime monitor for continuous `/health/live` monitoring.

## Logs and monitoring

Docker logs are bounded to five 10 MB JSON files per service:

```bash
docker compose --env-file .env.production logs -f --tail=200 bot
docker compose --env-file .env.production logs --since=30m postgres redis
curl http://127.0.0.1:8080/metrics
```

On Railway, use the service Logs and Metrics views and an external monitor. Apply
the alert thresholds in `OPERATIONS.md`. Investigate rising provider quota,
dependency error, crash, and Telegram delivery counters before increasing limits.

## PostgreSQL backups and restore

Create a daily custom-format backup, copy it off the VPS, encrypt it, and test a
restore regularly:

```bash
mkdir -p backups
docker compose --env-file .env.production exec postgres \
  pg_dump -U subtitle_bot -d subtitle_bot -Fc -f /tmp/subtitle-bot.dump
docker compose --env-file .env.production cp \
  postgres:/tmp/subtitle-bot.dump ./backups/subtitle-bot-$(date +%F).dump
docker compose --env-file .env.production exec postgres \
  rm -f /tmp/subtitle-bot.dump
```

Keep at least seven daily and four weekly encrypted copies on separate storage.
Redis does not require backup because it contains reconstructable cache and limit
state. Railway users should enable and periodically verify managed PostgreSQL
backups through the database service.

Restore only during an announced maintenance window:

```bash
docker compose --env-file .env.production stop bot
docker compose --env-file .env.production cp \
  ./backups/CHOSEN.dump postgres:/tmp/restore.dump
docker compose --env-file .env.production exec postgres \
  pg_restore -U subtitle_bot -d subtitle_bot --clean --if-exists /tmp/restore.dump
docker compose --env-file .env.production exec postgres rm -f /tmp/restore.dump
docker compose --env-file .env.production start bot
curl --fail http://127.0.0.1:8080/health/ready
```

## Upgrade and rollback

Before every upgrade, make a PostgreSQL backup, record the running Git commit and
image ID, review `SECURITY.md`, and run the full test suite. Then:

```bash
git fetch --tags
git checkout <reviewed-release-tag>
docker compose --env-file .env.production build --pull
docker compose --env-file .env.production up -d
curl --fail http://127.0.0.1:8080/health/ready
docker compose --env-file .env.production exec bot python -m scripts.production_smoke
```

For an application rollback, check out the recorded known-good tag/commit,
rebuild, start, and repeat both smoke checks. Restore PostgreSQL only if the
release changed data incompatibly; unnecessary database rollback risks losing
new preferences. On Railway, choose the previous successful deployment and use
Redeploy/Rollback, then repeat readiness and Telegram tests.

## Incident shutdown

To stop bot traffic without deleting data:

```bash
docker compose --env-file .env.production stop bot
```

To stop the entire stack while retaining named volumes:

```bash
docker compose --env-file .env.production down
```

Never add `--volumes` unless a verified backup exists and permanent database
deletion is explicitly intended.
