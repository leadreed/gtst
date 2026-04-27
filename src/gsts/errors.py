"""GSTS exception types."""


class GstsError(Exception):
    """Base exception for GSTS errors."""


class GstsConfigError(GstsError):
    """Raised when a GSTS config is missing or invalid."""


class GstsRootError(GstsError):
    """Raised when a GSTS root cannot be resolved."""


class GstsPathError(GstsError):
    """Raised when a schema, facet, or filesystem path is invalid."""


class GstsVersionError(GstsError):
    """Raised when a version cannot be resolved or read."""


class GstsPublishError(GstsError):
    """Raised when publishing cannot complete."""


class GstsTagError(GstsError):
    """Raised when a tag operation cannot complete."""


class GstsLockError(GstsError):
    """Raised when a filesystem lock cannot be acquired."""
