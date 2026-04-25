from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    verification_type: str
    reason: str = ""


def verify_output(
    *,
    output: dict[str, Any],
    exit_code: int,
    verification: dict[str, Any],
) -> VerificationResult:
    verification_type = str(verification.get("type", ""))
    if verification_type == "exit_status":
        expected = int(verification.get("expected", 0))
        if exit_code == expected:
            return VerificationResult(True, verification_type)
        return VerificationResult(False, verification_type, "exit_status_mismatch")

    if verification_type == "output_check":
        field = str(verification.get("field", ""))
        if field not in output:
            return VerificationResult(False, verification_type, "field_missing")
        operator = str(verification.get("operator", ""))
        value = output[field]
        if operator == "between":
            minimum = verification.get("min")
            maximum = verification.get("max")
            if isinstance(value, int | float) and minimum <= value <= maximum:
                return VerificationResult(True, verification_type)
            return VerificationResult(False, verification_type, "value_out_of_range")
        if operator == "equals":
            if value == verification.get("value"):
                return VerificationResult(True, verification_type)
            return VerificationResult(False, verification_type, "value_mismatch")
        if operator == "exists":
            return VerificationResult(True, verification_type)
        return VerificationResult(False, verification_type, "unsupported_output_check_operator")

    if verification_type == "adapter_verifier":
        return VerificationResult(False, verification_type, "adapter_verifier_not_bound")

    return VerificationResult(False, verification_type, "unsupported_verification_type")
