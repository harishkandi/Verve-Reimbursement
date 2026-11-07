class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class Conflict(DomainError):
    """The action isn't allowed in the claim's current state."""

    status_code = 409


class Invalid(DomainError):
    status_code = 422
