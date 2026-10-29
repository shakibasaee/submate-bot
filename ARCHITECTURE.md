# Architecture

SubMate follows dependency inversion: source dependencies point toward the domain and
application layers, while concrete services are assembled once in `app/bootstrap.py`.

```mermaid
flowchart LR
    Telegram["Telegram handlers and presenters"] --> UseCases["Application use cases"]
    UseCases --> Domain["Immutable domain models"]
    UseCases --> Ports["Application ports"]
    TMDb["TMDb metadata adapter"] --> Ports
    OpenSubs["OpenSubtitles provider adapter"] --> Ports
    SubDL["SubDL provider adapter"] --> Ports
    Storage["Conversation, preference, cache and limit adapters"] --> Ports
    Bootstrap["Composition root"] --> Telegram
    Bootstrap --> TMDb
    Bootstrap --> OpenSubs
    Bootstrap --> SubDL
    Bootstrap --> Storage
```

## Layer rules

- `app/domain` contains media, language, subtitle, and normalized error concepts. It
  imports no framework, network client, database driver, provider, or Telegram code.
- `app/application` owns workflows and state transitions. It depends only on the
  domain and protocols in `app/application/ports`.
- `app/infrastructure` implements the ports for TMDb, SubDL, OpenSubtitles, Redis,
  PostgreSQL, SQLite preferences, and single-process fallbacks.
- `app/bot` parses Telegram updates and renders structured outcomes. Handlers do not
  construct providers, access databases, choose cache keys, retry calls, rank
  subtitles, or mutate conversation records.
- `app/bootstrap.py` is the only composition root. It constructs one shared
  `aiohttp.ClientSession`, injects every adapter, and owns deterministic shutdown.

## Workflow consistency

Temporary conversations use opaque workflow IDs and expire lazily after 30 minutes.
Durable language preferences live behind a separate repository. Every state-changing
use case acquires a per-user lock, and transitions replace immutable conversation
records. Cancellation replaces the workflow identity, invalidating every old callback.

Subtitle candidates retain both an opaque provider ID and opaque provider file
reference. Telegram callbacks use the workflow, provider, and stored candidate index;
provider URLs never appear in callbacks or logs. SubDL file references retain a
validated download URL with its API-key query removed. Other providers use opaque
file identifiers. References remain private, temporary application state.

Interface and subtitle languages are independent preferences. An uncertain Telegram
upload enters a confirmation state: ordinary candidate clicks and language changes
cannot resend it. Receipt acknowledgement or explicit resend rotates the workflow;
a new search deliberately discards the old attempt. Restart loses temporary
conversations, so cross-restart exactly-once delivery is not claimed.
