"""Domain errors. Services raise these; `main.py` maps them to HTTP status codes."""


class DomainError(Exception):
    """Base class for errors the API reports to the client."""


class UnknownSiteError(DomainError):
    """A site id that is not in the catalogue (HTTP 404)."""


class LimitExceededError(DomainError):
    """A request too large to compute (HTTP 422)."""


class InvalidInputError(DomainError):
    """Input that passes schema validation but can't be computed, e.g. an unsupported step (HTTP 422)."""


class EphemerisUnavailableError(DomainError):
    """The upstream ephemeris (JPL Horizons) failed or returned unusable data (HTTP 502)."""


class TerrainUnavailableError(DomainError):
    """Terrain routing was requested but no verified LOLA DEM is mounted (HTTP 503)."""
