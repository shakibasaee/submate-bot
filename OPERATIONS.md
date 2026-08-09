# Reliability and monitoring

## Health and metrics

The bot serves the following endpoints on `HEALTH_HOST:HEALTH_PORT` (default
`0.0.0.0:8080`):

- `GET /health/live` returns 200 while the process event loop is serving HTTP.
- `GET /health/ready` checks configured Redis and PostgreSQL connections and
  confirms both provider API keys are configured. It returns 503 when degraded.
- `GET /metrics` returns Prometheus-compatible process, error, quota, rate-limit,
  crash, rejection, and delivery counters.

Do not expose `/metrics` publicly without network access controls. A reverse
proxy, platform health checker, or Prometheus instance should access it over a
private network.

## Suggested alerts

- Critical: `/health/live` fails for two consecutive minutes.
- Critical: `subtitle_bot_crashes_total` increases.
- Warning: `/health/ready` returns 503 for five minutes.
- Warning: `subtitle_bot_provider_errors_total` rises above 10 in 10 minutes.
- Warning: `subtitle_bot_provider_quota_errors_total` increases at all; lower
  rate limits or inspect the provider plan before retrying traffic.
- Warning: Redis/PostgreSQL dependency errors or Telegram delivery errors exceed
  five in 10 minutes.

Logs are one-line JSON on stdout. Search by the `event`, `level`, `component`, or
pseudonymous `user_ref` fields. Never add raw messages, queries, tokens, or
connection URLs to event fields.

## Failure behavior

Telegram polling, TMDb, OpenSubtitles, Redis, and PostgreSQL use bounded timeouts
and retries with exponential backoff. Authentication, validation, quota, and
unsafe-file failures are not blindly retried. Redis failures become cache misses
with in-process limits; PostgreSQL preference failures fall back to process
memory. Users receive concise retry guidance without internal error details.
