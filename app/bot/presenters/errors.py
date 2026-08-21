"""Consistent user-facing application errors."""

from app.domain.errors import (
    ApplicationError,
    ConfigurationError,
    MetadataError,
    ProviderError,
    ProviderLinkError,
    ProviderQuotaError,
    RateLimitedError,
    UnsafeSubtitleError,
)


def present_error(error: ApplicationError) -> str:
    if isinstance(error, ConfigurationError):
        return str(error)
    if isinstance(error, RateLimitedError):
        retry = f" Try again in about {error.retry_after} seconds." if error.retry_after else ""
        return f"{error}{retry}"
    if isinstance(error, ProviderQuotaError):
        return "The subtitle provider is quota-limited right now. Please try again later."
    if isinstance(error, ProviderLinkError):
        return "The temporary subtitle link expired or the download failed. Try again."
    if isinstance(error, UnsafeSubtitleError):
        return "That subtitle was rejected because it was unsafe, corrupt, or not a valid SRT."
    if isinstance(error, MetadataError):
        return str(error)
    if isinstance(error, ProviderError):
        return "Subtitle search is temporarily unavailable. Please try again later."
    return str(error)
