class PortfolioBTError(Exception):
    """Base package exception."""


class ValidationError(PortfolioBTError):
    """Raised when the user input is invalid."""


class NoOverlapError(PortfolioBTError):
    """Raised when no common date range exists across selected series."""


class ProviderError(PortfolioBTError):
    """Raised when a data provider fails."""


class CacheError(PortfolioBTError):
    """Raised when the cache cannot be read or written."""
