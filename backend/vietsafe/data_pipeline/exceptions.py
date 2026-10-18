"""Structured failures shared by models, validation and release publication."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    code: str
    message: str
    severity: str = "error"

    def to_dict(self):
        return asdict(self)


class DataValidationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{i.field}: {i.message}" for i in self.issues))

    def to_dict(self):
        return {"errors": [issue.to_dict() for issue in self.issues]}


class ReleaseExistsError(FileExistsError):
    """An immutable release or its publication lock already exists."""
