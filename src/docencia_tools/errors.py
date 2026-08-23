"""Clasificación explícita de fallos y diagnósticos accionables."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    INFRASTRUCTURE = "infrastructure_error"
    PROTOCOL = "protocol_error"
    IMPLEMENTATION = "implementation_error"
    ACADEMIC_VALIDATION = "academic_validation_error"


@dataclass(frozen=True)
class Issue:
    code: str
    kind: FailureKind
    message: str
    responsible: str
    blocks_review: bool = False
    blocks_execution: bool = False

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data


class InfrastructureError(RuntimeError):
    """Fallo de la automatización que no debe atribuirse al alumno."""


EXIT_CODES = {
    FailureKind.PROTOCOL: 2,
    FailureKind.IMPLEMENTATION: 3,
    FailureKind.ACADEMIC_VALIDATION: 4,
    FailureKind.INFRASTRUCTURE: 10,
}
