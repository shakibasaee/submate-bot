# SubMate baseline and integration evidence

Checked 2026-09-21. This checklist distinguishes automated tests from live delivery.

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
- [ ] Recovery PR passes hosted Quality checks and is merged.
- [ ] Default-branch Quality run passes after merge.

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
| Live movie delivery | Not run | No credentials configured in this workspace |
| Live episode delivery | Not run | No credentials configured in this workspace |
| Hosted PR CI | Pending | Record the run URL after completion |
| Default branch CI | Pending | Requires merge and a successful push run |

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

Defer filename matching until baseline and recovery are complete. No web frontend,
automatic synchronization, model training, additional deployment platforms, or
horizontal scaling is planned for this milestone.
