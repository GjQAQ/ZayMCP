"""Failure while locating or using OpticStudio."""

__all__ = [
    'OpticStudioError',
]


class OpticStudioError(Exception):
    """OpticStudio could not be located or used."""
