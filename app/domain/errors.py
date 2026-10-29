"""Domain and normalized external-service failures."""


class ApplicationError(Exception):
    """Base failure safe to map to a user-facing category."""


class PreferenceUnavailableError(ApplicationError):
    """Preference storage failed; the original database exception stays private."""


class InvalidInputError(ApplicationError):
    pass


class WorkflowExpiredError(ApplicationError):
    pass


class InvalidTransitionError(ApplicationError):
    pass


class ConfigurationError(ApplicationError):
    pass


class RateLimitedError(ApplicationError):
    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class MetadataError(ApplicationError):
    pass


class ProviderError(ApplicationError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderQuotaError(ProviderRateLimitError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderNotFoundError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


class ProviderConfigurationError(ConfigurationError):
    pass


class ProviderLinkError(ProviderResponseError):
    pass


class UnsafeSubtitleError(ProviderError):
    reason = "unsafe"


class MalformedSubtitleError(UnsafeSubtitleError):
    reason = "malformed"


class UnsupportedSubtitleError(UnsafeSubtitleError):
    reason = "unsupported"


class SubtitleDecodingError(UnsafeSubtitleError):
    reason = "decoding"


class UnsafeSubtitleContentError(UnsafeSubtitleError):
    reason = "unsafe_content"


class UnsafeSubtitleLinkError(UnsafeSubtitleError, ProviderLinkError):
    """A permanently rejected destination, rather than an expired provider link."""

    reason = "unsafe_link"
