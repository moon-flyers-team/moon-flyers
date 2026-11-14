"""Domain errors. Services raise these; `main.py` maps them to HTTP status codes."""


class DomainError(Exception):
    """Base class for errors the API reports to the client."""


class UnknownSiteError(DomainError):
    """A site id that is not in the catalogue (HTTP 404)."""


class LimitExceededError(DomainError):
    """A request too large to compute (HTTP 422)."""
