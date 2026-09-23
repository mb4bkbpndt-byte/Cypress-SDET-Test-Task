from typing import Any, Dict
from uuid import uuid4


def make_idempotency_key(prefix: str = "idem") -> str:
    return f"{prefix}-{uuid4().hex}"


def make_beneficiary_ref(prefix: str = "beneficiary") -> str:
    return f"{prefix}-{uuid4().hex}"


def make_payment_payload(
    beneficiary_prefix: str = "beneficiary",
    **overrides: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "corridor": "RUB/THB",
        "amount": 100_000,
        "currency": "RUB",
        "beneficiary_ref": make_beneficiary_ref(beneficiary_prefix),
    }
    payload.update(overrides)
    return payload
