# SubMate baseline and integration evidence

Last reconciled 2026-09-24. This checklist distinguishes automated tests from live
delivery and records only evidence that was actually observed.

## Baseline

- [x] Inspect `main` (`c898a20`) and `codex/recover-mvp` (`4b37454`).
- [x] Identify the default-branch CI failure: a Windows editable path in
  `requirements.lock` prevents Linux installation (Actions run `32502340980`).
- [x] Review recovery changes: portable installation, current composition-root
  smoke check, authenticated provider downloads, episode IDs, and provider tests.
- [x] Install locked dependencies and the editable package in a fresh Python
  3.13.3 virtual environment on Windows; `pip check` passes.
- [x] Ruff lint/format and Pyright pass.
- [x] Automated suite: 92 tests pass, including movie and episode application
  delivery, provider authentication/error contracts, and smoke lifecycle checks.
  These use fakes and do not prove live provider or Telegram delivery.
- [x] Recovery PR #2 passed hosted Quality checks and was merged as `bcc7fb3`.
- [x] Default-branch Quality run `35624502885` passed after the merge.
- [x] Re-run the complete local gate on 2026-09-24: locked dependencies are
  consistent, Ruff lint/format and Pyright pass, and 92 tests pass with 77%
  statement coverage.

## Live integration (pending credentials and a test chat)

Use a dedicated test bot with one polling process. Keep credentials in an ignored
`.env`; never copy tokens, passwords, temporary download URLs, or personal chat
details into this checklist, recordings, or logs.

1. Configure Telegram, TMDb, and OpenSubtitles credentials using the README.
2. Run `python -m scripts.production_smoke`. This checks composition, configured
   dependencies, and Telegram authentication; it does not download subtitles.
3. Start `python -m app.main`, open the test bot, and select English or Persian.
4. Search for a movie with available subtitles, select a result and subtitle,
   and open the received SRT. Record title, language, date, and pass/fail below.
5. Search for a series, choose a season and episode, and receive/open the SRT.
   Confirm the filename contains the selected season, episode, and language.

| Check | Result | Evidence |
| --- | --- | --- |
| Telegram authentication | Pass | Bot API `getMe` succeeded on 2026-09-21; no token was printed or recorded |
| Full production smoke | Blocked | Repository `.env` is absent; TMDb and OpenSubtitles credentials are unavailable |
| Live movie delivery | Not run | Requires the five configured credentials and a test chat |
| Live episode delivery | Not run | Requires the five configured credentials and a test chat |
| Hosted PR CI | Pass | Quality run `35623114441` |
| Default branch CI | Pass | Quality run `35624502885` for `bcc7fb3` |

## Conversation recovery acceptance (next milestone)

Confirmed defects: candidates are cleared before provider download completes;
the workflow remains DELIVERING after success; Change language asks users to
type a command instead of opening its picker.

- [ ] Download failure preserves choices and offers Retry and Search another title.
- [ ] Telegram delivery failure also leaves an actionable recovery path.
- [ ] Successful delivery allows another search without restarting.
- [ ] Change language opens the picker directly.
- [ ] Tests cover success, failure, concurrent attempts, and stale callbacks.

## Demo and release gates

- [ ] Record a 45–75 second real movie/episode walkthrough and link near README top.
- [ ] Review setup/provider limitations and add repository description/topics.
- [ ] Verify deployment, restart behavior, and secret handling before publication.
- [ ] Owner chooses a license if publishing; add release notes and stable tag only
  after deployment and live integration evidence exists.

## Current issue classification

- **Blocker:** real TMDb/OpenSubtitles search and Telegram movie/episode delivery
  cannot be verified without the missing provider credentials.
- **Blocker:** a production-like PostgreSQL/Redis deployment and restart have not
  been exercised on this host; Docker is not currently available.
- **Important:** conversation recovery still has the dead ends listed above.
- **Important:** the public repository has no description, topics, or license.
- **Follow-up:** record and link the short walkthrough after live verification.

Defer filename matching until baseline and recovery are complete. No web frontend,
automatic synchronization, model training, additional deployment platforms, or
horizontal scaling is planned for this milestone.
