"""Failures that stop the run instead of guessing."""


class ManualReview(RuntimeError):
    """The UI is ambiguous or conflicts with the source document.

    Nothing further is written or saved after this is raised.
    """


class GroundingError(RuntimeError):
    """A control could not be identified safely."""
