# SubMate avatar v2 and search recovery

Prepared 2026-10-22 using built-in image generation.
Asset: submate-avatar-v2.png. The previous avatar is preserved.

Generation brief: A Telegram profile picture specifically for a movie/TV subtitle finder. Movie clapperboard, prominent mint CC badge, two white caption lines, exact SubMate wordmark, midnight indigo background. High contrast with circular-crop margins. No movie characters, mockup, or watermark.
Final edit prompt: Preserve the clapperboard, CC badge, subtitle lines, SubMate wordmark, colors and lighting. Reduce the complete composition by 18 percent around its center, leaving generous dark margins for a circular crop.

Observed live checks: target Telegram authentication succeeded; no webhook was configured; TMDb search succeeded. OpenSubtitles API key, username, and password remain missing. No real subtitle delivery is claimed.

Code change: A new typed title replaces the previous workflow while retaining the language. Old buttons expire. Empty searches also invalidate previous choices. Network failures retain previous choices. New searches are blocked during delivery to avoid abandoning an upload.

Regression tests cover a new search after provider configuration failure and stale buttons after empty results. 105 tests, lint, format, and type checking passed. The source changes must be loaded by restarting the running bot. No profile change was published.