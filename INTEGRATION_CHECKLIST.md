# SubMate verification evidence

Verified locally on 2026-10-08 in the existing Windows checkout. Automated tests
use controlled providers and do not establish real Telegram document delivery.

## Automated verification

- 102 tests passed; 78% statement coverage.
- Dependency validation, Ruff lint, formatting, and Pyright passed.
- Movie and TV workflows retain episode coordinates and produce safe filenames.
- Invalid SRT cue structures, times, empty files, archives, and oversized files are rejected.
- Provider failure retains title, language, and choices; Retry is available.
- Telegram upload failure restores choices and warns that delivery can be uncertain.
- Successful upload provides Another subtitle and Search another title.
- Duplicate delivery clicks and stale workflow buttons are rejected.
- Contextual Change language preserves the media and refreshes subtitle results.
- SQLite preferences survive replacement of the repository instance.
- Local polling lock blocks a duplicate token instance and releases on shutdown.

## Live verification

| Check | Result | Evidence |
| --- | --- | --- |
| Telegram credential configuration | Present | Value checked locally without disclosure |
| Telegram target authentication | Blocked | getMe timed out; credential validity and target identity remain unconfirmed |
| TMDb credential configuration | Present | Value checked locally without disclosure |
| TMDb live search | Failed | Provider request failed; see secret-safe live_check status for classification |
| OpenSubtitles configuration | Missing | API key, username, and password still contain placeholders |
| OpenSubtitles authentication/download | Not run | Requires local credentials |
| Real movie SRT delivery to Telegram | Not run | Requires reachable providers, credentials, and user interaction |
| Real episode SRT delivery to Telegram | Not run | Requires reachable providers, credentials, and user interaction |
| Polling process | Not started | Target identity could not be verified; no unrelated processes stopped |
| External deployment | Not performed | Local operation does not provide permanent availability |

Local SQLite preference storage is enabled in the ignored .env. Conversation
state remains in memory and expires after 30 minutes; after restart use /start.

## Telegram acceptance checklist

After credentials/connectivity are verified and one polling process is started:

1. Open @Sub_Mate_bot, send /start, and choose English on first use.
2. Search Inception; select the 2010 movie and a subtitle. Open the delivered SRT.
3. Choose Another subtitle, then Change language; confirm the current movie remains selected.
4. Choose Search another title. Search Breaking Bad, select Season 1 and Episode 1,
   choose a subtitle, and verify a nonempty S01E01-en.srt document arrives.
5. Double-click a subtitle button; confirm only one document is sent. Old buttons
   should explain expiry without changing the new search.
6. If a real download fails, confirm Retry and Search another title work.

Do not store secrets, temporary provider links, user/chat identifiers, or downloaded
subtitles in evidence or recordings. No live delivery is claimed until observed.
