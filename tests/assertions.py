from typing import Any, Dict

import requests


BUSINESS_FIELDS = ("corridor", "amount", "currency", "beneficiary_ref")


def business_fields(payment: Dict[str, Any]) -> Dict[str, Any]:
    return {field: payment.get(field) for field in BUSINESS_FIELDS}


def assert_payment_matches_payload(
    payment: Dict[str, Any],
    payload: Dict[str, Any],
) -> str:
    payment_id = payment.get("payment_id")
    assert isinstance(payment_id, str) and payment_id, payment
    for field in BUSINESS_FIELDS:
        assert payment.get(field) == payload[field], {
            "field": field,
            "expected": payload[field],
            "actual": payment.get(field),
            "payment": payment,
        }
    return payment_id


def assert_single_payment(
    response: requests.Response,
    expected_payment_id: str,
) -> Dict[str, Any]:
    assert response.status_code == 200, response.text
    data = response.json()
    payment_ids = [item["payment_id"] for item in data["payments"]]
    assert data["count"] == 1, data
    assert payment_ids == [expected_payment_id], data
    return data["payments"][0]
