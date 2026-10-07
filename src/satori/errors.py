class SatoriError(Exception):
    """Base class for expected Satori failures."""


class DependencyUnavailable(SatoriError):
    """A selected component's runtime dependency is missing."""


class CheckpointUnavailable(SatoriError):
    """A selected model's trained checkpoint is unavailable."""


class ExternalSourceError(SatoriError):
    """A reproducible external-source request failed."""


class ComponentBlocked(SatoriError):
    """A component cannot run without a user decision or external resource."""

