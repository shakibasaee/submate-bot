"""Short actionable messages without provider internals or credentials."""

from app.bot.texts import ui
from app.domain.errors import (
    ApplicationError,
    ConfigurationError,
    InvalidTransitionError,
    MetadataError,
    PreferenceUnavailableError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderLinkError,
    ProviderNotFoundError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
    UnsafeSubtitleError,
    WorkflowExpiredError,
)


def retryable(error: ApplicationError) -> bool:
    return (
        isinstance(
            error,
            (
                ProviderUnavailableError,
                ProviderTimeoutError,
                ProviderRateLimitError,
                ProviderLinkError,
                RateLimitedError,
                MetadataError,
            ),
        )
        and not isinstance(error, UnsafeSubtitleError)
        and "rejected" not in str(error).lower()
    )


def present_error(error: ApplicationError) -> str:
    if isinstance(error, PreferenceUnavailableError):
        return ui("preference_error")
    if isinstance(error, UnsafeSubtitleError):
        return (
            ui(f"invalid_{error.reason}")
            if error.reason in {"malformed", "unsupported", "decoding", "unsafe_content"}
            else ui("unsafe")
        )
    if isinstance(error, WorkflowExpiredError):
        return ui("busy") if "being delivered" in str(error) else ui("stale")
    if isinstance(error, ProviderQuotaError):
        return ui("quota_error")
    if isinstance(error, ProviderAuthenticationError):
        return ui("auth_error")
    if isinstance(error, ConfigurationError):
        return ui("config_error")
    if isinstance(error, RateLimitedError):
        wait = ui("rate_wait").format(seconds=error.retry_after) if error.retry_after else ""
        return ui("rate_error") + wait
    if isinstance(error, ProviderNotFoundError):
        return ui("not_found_error")
    if isinstance(error, ProviderLinkError):
        return ui("link_error")
    if isinstance(error, (ProviderError, MetadataError)):
        if "rejected" in str(error).lower():
            return ui("service_auth_error")
        return ui("provider_error")
    if isinstance(error, InvalidTransitionError):
        return ui("busy") if "delivered" in str(error) else ui("stale")
    return ui("request_error")
