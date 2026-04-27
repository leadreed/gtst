"""GTST exception types."""


class GtstError(Exception):
    """Base exception for GTST errors."""


class GtstConfigError(GtstError):
    """Raised when a GTST config is missing or invalid."""


class GtstRootError(GtstError):
    """Raised when a GTST root cannot be resolved."""


class GtstPathError(GtstError):
    """Raised when a schema, facet, or filesystem path is invalid."""


class GtstVersionError(GtstError):
    """Raised when a version cannot be resolved or read."""


class GtstPublishError(GtstError):
    """Raised when publishing cannot complete."""


class GtstTagError(GtstError):
    """Raised when a tag operation cannot complete."""


class GtstLockError(GtstError):
    """Raised when a filesystem lock cannot be acquired."""
