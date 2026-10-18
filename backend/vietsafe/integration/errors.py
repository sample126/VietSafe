"""Serializable boundary errors; no traceback or exception chaining in payloads."""

CODES = frozenset({
    "INVALID_CONTRACT", "NETWORK_VERSION_MISMATCH", "UNKNOWN_ROAD",
    "FEATURE_SCHEMA_MISMATCH", "UNSUPPORTED_HORIZON", "MISSING_INPUT",
    "UNAVAILABLE", "STALE",
})


class IntegrationContractError(ValueError):
    def __init__(self, code, message, path=None):
        if code not in CODES:
            raise ValueError("Unsupported integration error code")
        self.code, self.message, self.path = code, message, path
        super().__init__(message)

    def to_dict(self):
        result = {"code": self.code, "message": self.message}
        if self.path is not None:
            result["path"] = self.path
        return result
