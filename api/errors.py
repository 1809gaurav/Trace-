"""API errors with a stable, plain-language response shape."""


class APIError(Exception):
    """Expected client-facing error."""

    def __init__(self, status_code: int, code: str, message: str, details: object = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
