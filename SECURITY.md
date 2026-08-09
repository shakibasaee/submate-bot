# Security and dependency maintenance

## Secret handling

- Keep Telegram, TMDb, OpenSubtitles, PostgreSQL, and Redis credentials only in
  environment variables or the ignored `.env` file.
- Never paste secrets into logs, issues, screenshots, or Git history.
- Rotate a credential immediately if it may have been exposed. Bot tokens are
  rotated through BotFather; provider and database credentials are rotated in
  their respective consoles.
- Production logs are JSON and redact secret-bearing fields, Telegram-token
  patterns, connection-string passwords, search queries, and message text.

## Updating dependencies

Perform this review at least monthly and immediately for a relevant security
advisory:

```powershell
python -m pip install --upgrade pip pip-audit
python -m pip list --outdated
python -m pip_audit -r requirements.lock
```

Update version ranges in `pyproject.toml`, recreate a clean virtual environment,
install the project, run all checks, and then regenerate `requirements.lock`
from the reviewed environment:

```powershell
python -m pip freeze --exclude-editable > requirements.lock
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Review changelogs for aiogram, aiohttp, Psycopg, redis-py, Pydantic, and
OpenSubtitles/TMDb API changes before deployment. Commit the source-range and
lock-file changes together so rollback restores the same dependency set.

## Privacy and copyright

PostgreSQL stores only the Telegram user ID, selected language, and update
timestamp. User search text is not intentionally persisted or logged. Provider
requests contain only the content identifiers, language, and episode coordinates
needed for the request. `/privacy` exposes the user-facing notice.

Downloaded subtitles remain copyrighted by their respective authors. Every
delivery attributes OpenSubtitles.com and includes uploader attribution when the
provider supplies it. Operators must comply with provider terms and local law.
