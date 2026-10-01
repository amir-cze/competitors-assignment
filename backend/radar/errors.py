"""Domain exceptions. Services raise these; the API layer maps them to HTTP status codes.

Keeping services free of FastAPI means they can be called from the worker, tests and scripts unchanged.
"""

from __future__ import annotations


class RadarError(Exception):
    status_code = 500

    def __init__(self, message: str = "Something went wrong"):
        super().__init__(message)
        self.message = message


class NotFound(RadarError):
    status_code = 404


class Conflict(RadarError):
    status_code = 409


class InvalidInput(RadarError):
    status_code = 400


class Unauthorized(RadarError):
    status_code = 401


class UpstreamFailure(RadarError):
    """A third party (site, Slack, OpenAI) did not cooperate."""

    status_code = 502
