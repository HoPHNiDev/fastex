class LimiterBackendError(RuntimeError):
    """Base exception for all limiter backend errors."""

    def __init__(self, message: str = "Limiter backend error occurred") -> None:
        super().__init__(message)
