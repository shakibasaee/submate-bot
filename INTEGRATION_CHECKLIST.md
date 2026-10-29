# SubMate verification evidence

Updated locally on 2026-10-29 in the existing Windows checkout. Automated tests
use controlled providers and do not establish real Telegram document delivery.

## Automated verification

- 211 tests passed; the suite includes independent interface onboarding, safe names, persistence, menu, pagination, provider, and back-navigation coverage.
- Dependency validation, Ruff lint, formatting, and Pyright passed.
- Movie and TV workflows retain episode coordinates and produce safe filenames.
- Invalid SRT cue structures, times, empty files, archives, and oversized files are rejected.
- Temporary provider failure retains title, language, and choices; Retry and Back to subtitle list are available.
- Invalid SRT/unsafe files are excluded for the current flow and are not retried.
- Subtitle lists can return to TV episodes, and episode lists can return to seasons.
- Ambiguous Telegram upload failure retains choices behind an explicit receipt/resend decision; normal retry and stale candidate clicks cannot resend it.
- Successful upload provides Another subtitle and Search another title.
- Duplicate delivery clicks and stale workflow buttons are rejected.
- Contextual Change language preserves the media and refreshes subtitle results.
- SQLite preferences survive replacement of the repository instance.
- Local polling lock blocks a duplicate token instance and releases on shutdown.

## Live verification

Latest review on 2026-10-29:

| Area | Observation |
| --- | --- |
| Automated checks | 211 tests, dependency validation, lint, formatting, type checking and diff whitespace checks passed locally. |
| Telegram connectivity | Latest live check failed with TelegramNetworkError; an independent public-endpoint check failed before HTTP with ClientConnectorError/ConnectionRefusedError. No credential rejection was observed. |
| TMDb connectivity | Latest search check reported network/provider unavailable; the public-endpoint connection also failed before HTTP. |
| Provider download | No fresh movie or episode download was established by this run. Earlier successful downloads below remain historical observations. |
| Telegram receipt | Not observed; requires the user's acceptance test after network access returns. |
| Local execution | Started using the new local launcher; local health responded. One local token lock is held. Local health is not proof of Telegram connectivity. |
| Preferences | SQLite restart persistence tested automatically; PostgreSQL and Redis were not exercised live. |
| Deployment | No external deployment was performed or verified. This computer must remain awake and online. |

The home menu now exposes Search subtitles, Subtitle language, Settings and Help.
Validation distinguishes malformed cues, unsupported content, decoding failures and
unsafe content, without relaxing SRT checks. Legacy decoding uses the selected
subtitle language; Unicode BOM errors cannot silently fall back to a legacy codec.
Logs redact URL/identifier fields and formatted exception messages. The local
launcher adds no scheduled task, service, or external infrastructure.
The observed initial Telegram network failure previously terminated startup. The
process now waits for reconnection in bounded request batches; automated tests
verify recovery after an exhausted batch and immediate failure on invalid credentials.

Earlier observations (not evidence of current connectivity):

| Check | Result | Evidence |
| --- | --- | --- |
| Telegram credential configuration | Present | Value checked locally without disclosure |
| Telegram target authentication | Pass | Live getMe authenticated the target; no webhook configured |
| TMDb credential configuration | Present | Value checked locally without disclosure |
| TMDb live search | Pass | Live Inception search succeeded |
| OpenSubtitles configuration | Missing | API key, username, and password still contain placeholders |
| OpenSubtitles authentication/download | Not run | Requires local credentials |
| SubDL configuration/authentication | Pass | Existing personal account key saved directly to ignored .env; real search returned HTTP 200 with status true |
| SubDL movie download | Pass | Inception (2010), English: real provider SRT downloaded and validated in memory |
| SubDL episode download | Pass | Breaking Bad S01E01, English: exact episode raw SRT downloaded and validated in memory |
| Real movie SRT delivery to Telegram | Not run | Requires reachable providers, credentials, and user interaction |
| Real episode SRT delivery to Telegram | Not run | Requires reachable providers, credentials, and user interaction |
| Polling process | Running locally in live mode | One polling process group; liveness ok and readiness ready; no polling conflict, network error, handler error, or crash observed in startup logs |
| External deployment | Not performed | Local operation does not provide permanent availability |

Local SQLite preference storage is enabled in the ignored .env. Conversation
state remains in memory and expires after 30 minutes; after restart use /start.

## Telegram acceptance checklist

After credentials/connectivity are verified and one polling process is started:

1. Open @Sub_Mate_bot and send /start. On first use choose فارسی 🇮🇷 or English 🇬🇧
   for the interface. Verify your escaped display name, localized welcome, saved
   subtitle preference, and persistent 2x2 home keyboard. Choose Subtitle search
   and select English subtitles separately if needed.
2. Search Inception; select the 2010 movie and a subtitle. Open the delivered SRT.
3. Choose Another subtitle, then Change language; confirm the current movie remains selected.
4. Choose Search another title. Search Breaking Bad, select Season 1 and Episode 1,
   choose a subtitle, and verify a nonempty S01E01-en.srt document arrives.
5. Double-click a subtitle button; confirm only one document is sent. Old buttons
   should explain expiry without changing the new search.
6. If a real download fails, confirm Retry and Search another title work.
7. Use Back to subtitle list after a failure: confirm title, language, and episode
   stay selected. For TV, return to episodes and then seasons; choose a different
   season and episode without starting another title search.
8. Confirm a rejected invalid/unsafe file has no Retry action and does not reappear
   in the same flow. When none remain, verify language, episode, and title controls.
9. Page forwards and backwards through a long list. Verify real page numbers and
   preservation of the page when returning. Check that episode names are shown.
10. Change subtitle language between English and Persian: the selected interface
    language must remain unchanged. Open /settings and change interface language;
    the active movie/episode and subtitle language must remain unchanged.
11. Confirm processing and errors update the selection panel instead of appending
    status messages. After a successful upload verify another-version/language,
    another-episode (TV only), and new-search actions. Help/About must not search their labels.

Do not store secrets, temporary provider links, user/chat identifiers, or downloaded
subtitles in evidence or recordings. No live delivery is claimed until observed.

## Infrastructure verification

SQLite restart behavior is covered by automated tests. Live PostgreSQL and Redis connectivity, fallback recovery, and external deployment were not exercised during this review.

## Historical demo verification - 2026-10-22

This records the earlier demo-only state, superseded by the live provider checks above.

- Enabled DEMO_MODE explicitly in the ignored local .env. Demo captions are original
  samples labeled in /start, candidate buttons, document captions, and SRT content.
- Live Telegram target authentication passed and no webhook was present.
- Real TMDb Inception search and Breaking Bad episode navigation passed.
- The diagnostic command validated generated movie and episode sample SRTs in
  memory. This is NOT evidence of real provider subtitle download or Telegram receipt.
- SubDL adapter automated tests passed for movie and exact episode filtering,
  language checks, raw SRT validation, unsafe links/redirects, quotas, and bounded retries.
- No SubDL API key is configured. Live SubDL downloads remain unverified.
- Demo retry/success/new-search tests passed for movie and episode journeys.
- Production smoke intentionally rejects demo mode. Health exposes mode demo.
- PostgreSQL/Redis and external deployment were not exercised in this update.

Demo-only procedure: /start, search a movie, choose DEMO original sample, receive/open
the SRT. Then choose Another subtitle and the fails-once sample; press Retry and
confirm delivery. Search Breaking Bad, choose S01E01, and repeat. Check that all
files are visibly demos. Switch DEMO_MODE off only after configuring a real provider.

## SubDL setup and live provider verification - 2026-10-28

- Retrieved the existing key from the signed-in SubDL account without displaying
  it. No new key, purchase, paid subscription, push, or external deployment was made.
- Initial live searches succeeded but yielded no application candidates. The
  adapter rejected raw-file links containing an account-key query parameter.
  It now removes that parameter before storage/download while still rejecting
  unknown parameters and unsafe hosts. A regression test covers both boundaries.
- Files with missing/incorrect season coordinates remain excluded. The successful
  TV check used an exact season/episode match; no inference from a pack filename.
- Telegram getMe authenticated the intended bot and no webhook was configured.
  Real TMDb movie search and TV episode navigation passed.
- Both real provider SRT downloads passed validation in memory. No subtitle file,
  temporary provider URL, credential, or chat identifier was saved as evidence.
- Only after these downloads passed, DEMO_MODE was disabled and one local polling
  instance was started. Local health reports ready/live with SubDL configured.
- Dependency validation, Ruff lint/format, Pyright, 127 tests with coverage, and
  git diff whitespace checks passed. The local .env and runtime logs remain ignored.
- Telegram movie/episode document receipt, live PostgreSQL/Redis behavior, and
  external deployment remain unverified. Use the Telegram acceptance checklist above.

## Recovery navigation verification - 2026-10-28

This records the earlier navigation implementation; the interface update below supersedes its UI labels.

- 143 automated tests passed with coverage, including 14 focused navigation cases
  and existing movie/TV, transient failure, retry, successful upload, upload failure,
  lifecycle, preference persistence, and architecture boundary checks.
- Controlled tests verify preserved media/language/episode choices, no extra search
  on Back, invalid-file exclusion across refresh/language/episode changes, empty
  lists, season navigation, English/Persian controls, concurrent actions, and stale
  initial/contextual language pickers and candidate indices.
- Unsupported/malformed download destinations are distinguished from temporary
  link failures and treated as unsafe; URL parsing errors stay behind provider ports.
- Dependency validation, Ruff lint/format, Pyright, and whitespace checks passed.
- These tests use controlled Telegram/provider responses. No new live Telegram
  navigation or document receipt is claimed by this update. The earlier real
  provider downloads above remain separate observations.
- PostgreSQL/Redis and external deployment were not exercised in this update.

## Button interface verification - 2026-10-28

- 169 tests passed with coverage; 26 new UI contracts plus 14 existing focused
  navigation cases cover persistent menu routing, saved-language welcome, all four
  paged lists, previous/next/page counts, episode 65, retained page positions,
  independent subtitle/interface languages, contextual success actions, invalid
  file removal, temporary-error Retry, and stale/duplicate/concurrent actions.
- Strict Telegram doubles verify edits to one panel, separate document delivery,
  upload-failure recovery, progress cancellation cleanup, and fallback behavior
  for uneditable versus unchanged messages and uncertain network failures.
- Lookup failures invalidate their attempt before queued duplicate callbacks can
  repeat a provider request. Download claims precede the visible processing state.
- Dependency validation, Ruff lint/format, Pyright, and whitespace checks passed.
- These are controlled UI/provider tests. No live Telegram menu/navigation or
  document receipt was observed by this update; use the acceptance checklist above.
- Earlier real provider downloads remain separate observations. No paid service,
  push, or external deployment was performed. PostgreSQL/Redis were not exercised.
- Restarted only the verified local SubMate process with the new interface. One
  polling instance was observed; health reported ok/ready in live mode, and startup
  logs showed no polling conflict, network failure, handler error, or crash.
  This local process stops when the computer or process stops.

## Personalized welcome verification - 2026-10-28

- 189 tests passed, including 20 focused welcome/interface tests. First/repeated
  Start, both interface choices, independent subtitle preferences, current-name
  rendering, HTML/control-character safety, generic fallback, stale/competing
  interface callbacks, settings during an active journey, and concurrent-user
  locale isolation passed with controlled Telegram responses.
- The real aiogram dispatcher was exercised with an offline Bot API session:
  first Start, interface callback, saved-language Start, and an English home-menu
  action passed through the actual routing and locale middleware without network calls.
- SQLite legacy-schema compatibility and preferences across repository/application
  replacement passed. The additive schema preserves existing subtitle records;
  neither interface nor subtitle preference storage contains display names.
- PostgreSQL interface reads/writes, schema creation, and independent memory
  fallback were tested with a controlled connection. Live PostgreSQL/Redis and
  external deployment were not tested by this update.
- A bilingual pre-Start profile introduction is prepared in docs/bot-profile.md.
  No public profile metadata was changed. Profile viewing alone does not trigger
  a welcome; only Start, /start, and the explicit interface selection do.
- Live Telegram greeting/menu receipt remains a manual acceptance check. Earlier
  real provider SRT downloads are separate observations, not proof of this UI flow.
- Dependency validation, Ruff lint/format, Pyright, and whitespace checks passed.
  The local SQLite interface table was initialized alongside the existing subtitle
  table without reading preference rows. One updated local polling instance is
  running in live mode with ok/ready health and no startup errors observed.
