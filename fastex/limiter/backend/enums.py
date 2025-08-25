from enum import Enum


class FallbackMode(Enum):
    ALLOW = "allow"  # Allow all requests
    DENY = "deny"  # Block all requests
    RAISE = "raise"  # Raise Exception
