from typing import Any, Callable, Dict, Optional

import pytest
import requests

from api_client import PaymentsApiClient
from tests.factories import make_idempotency_key, make_payment_payload


pytestmark = [pytest.mark.validation]


def _field_case(
    field: str,
    value: Any,
    case_id: str,
    bug: Optional[str] = None,
    assumption: bool = False,
) -> Any:
    marks = [pytest.mark.assumption if assumption else pytest.mark.contract]
    if bug:
        marks.append(pytest.mark.known_defect(bug))
    return pytest.param(field, value, id=case_id, marks=marks)


INVALID_STRING_FIELDS = [
    _field_case("corridor", None, "corridor-null", "BUG-005", True),
    _field_case("corridor", 123, "corridor-number", "BUG-005", True),
    _field_case("corridor", True, "corridor-boolean", "BUG-005", True),
    _field_case("corridor", {"value": "RUB/THB"}, "corridor-object", "BUG-005", True),
    _field_case("corridor", ["RUB/THB"], "corridor-array", "BUG-005", True),
    _field_case("corridor", "", "corridor-empty", "BUG-005", True),
    _field_case("corridor", "   ", "corridor-whitespace", "BUG-005", True),
    _field_case("currency", None, "currency-null"),
    _field_case("currency", 123, "currency-number"),
    _field_case("currency", True, "currency-boolean"),
    _field_case("currency", {"value": "RUB"}, "currency-object", "BUG-006"),
    _field_case("currency", ["RUB"], "currency-array", "BUG-006"),
    _field_case("currency", "", "currency-empty"),
    _field_case("currency", "   ", "currency-whitespace"),
    _field_case("beneficiary_ref", None, "beneficiary-null", "BUG-007", True),
    _field_case("beneficiary_ref", 123, "beneficiary-number", "BUG-007", True),
    _field_case("beneficiary_ref", True, "beneficiary-boolean", "BUG-007", True),
    _field_case(
        "beneficiary_ref",
        {"value": "beneficiary"},
        "beneficiary-object",
        "BUG-007",
        True,
    ),
    _field_case(
        "beneficiary_ref",
        ["beneficiary"],
        "beneficiary-array",
        "BUG-007",
        True,
    ),
    _field_case("beneficiary_ref", "", "beneficiary-empty", "BUG-007", True),
    _field_case(
        "beneficiary_ref", "   ", "beneficiary-whitespace", "BUG-007", True
    ),
]

INVALID_AMOUNTS = [
    pytest.param("100", id="numeric-string", marks=pytest.mark.contract),
    pytest.param(None, id="null", marks=pytest.mark.contract),
    pytest.param(
        True,
        id="boolean-true",
        marks=[pytest.mark.contract, pytest.mark.known_defect("BUG-003")],
    ),
    pytest.param(
        False,
        id="boolean-false",
        marks=[pytest.mark.contract, pytest.mark.known_defect("BUG-003")],
    ),
    pytest.param({"value": 100}, id="object", marks=pytest.mark.contract),
    pytest.param([100], id="array", marks=pytest.mark.contract),
    pytest.param(
        0,
        id="zero",
        marks=[pytest.mark.assumption, pytest.mark.known_defect("BUG-002")],
    ),
    pytest.param(
        -1,
        id="negative",
        marks=[pytest.mark.assumption, pytest.mark.known_defect("BUG-002")],
    ),
]


def _capture_response(
    send_request: Callable[[], requests.Response],
) -> Dict[str, Any]:
    try:
        response = send_request()
    except requests.RequestException as error:
        return {
            "status": None,
            "body": None,
            "json": None,
            "request_error": f"{type(error).__name__}: {error}",
        }

    try:
        response_json = response.json()
    except ValueError:
        response_json = None

    return {
        "status": response.status_code,
        "body": response.text,
        "json": response_json,
        "request_error": None,
    }


def _debug_snapshot(
    api_client: PaymentsApiClient,
    beneficiary_ref: str,
) -> Dict[str, Any]:
    response = api_client.get_payments_by_ref(beneficiary_ref)
    data = response.json()
    return {
        "status": response.status_code,
        "count": data.get("count"),
        "payment_ids": [
            item.get("payment_id") for item in data.get("payments", [])
        ],
        "body": response.text,
    }


def _assert_rejected_without_observable_payment(
    *,
    api_client: PaymentsApiClient,
    send_invalid: Callable[[str], requests.Response],
    invalid_description: Dict[str, Any],
    observable_ref: Optional[str],
) -> None:
    idempotency_key = make_idempotency_key(prefix="validation")
    result = _capture_response(lambda: send_invalid(idempotency_key))
    response_body = result["json"]
    returned_id = (
        response_body.get("payment_id")
        if isinstance(response_body, dict)
        else None
    )
    get_response = (
        api_client.get_payment(returned_id)
        if isinstance(returned_id, str) and returned_id
        else None
    )
    snapshot = (
        _debug_snapshot(api_client, observable_ref)
        if observable_ref is not None
        else None
    )
    returned_payment_exists = False
    if get_response is not None:
        returned_payment_exists = (
            get_response.status_code == 200
            if get_response.status_code < 500
            else None
        )

    actual = {
        "status": result["status"],
        "request_error": result["request_error"],
        "returned_payment_exists": returned_payment_exists,
        "debug_status": snapshot["status"] if snapshot else None,
        "count": snapshot["count"] if snapshot else None,
        "payment_ids": snapshot["payment_ids"] if snapshot else None,
    }
    expected = {
        "status": 422,
        "request_error": None,
        "returned_payment_exists": False,
        "debug_status": 200 if observable_ref is not None else None,
        "count": 0 if observable_ref is not None else None,
        "payment_ids": [] if observable_ref is not None else None,
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "request": invalid_description,
        "idempotency_key": idempotency_key,
        "beneficiary_ref_checked": observable_ref,
        "response_body": result["body"],
        "returned_payment_id": returned_id,
        "get_status": get_response.status_code if get_response is not None else None,
        "get_body": get_response.text if get_response is not None else None,
        "debug_body": snapshot["body"] if snapshot else None,
    }


@pytest.mark.contract
def test_create_without_idempotency_key_returns_400(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload()
    response = api_client.create_payment(payload, idempotency_key=None)
    snapshot = _debug_snapshot(api_client, payload["beneficiary_ref"])

    assert {
        "status": response.status_code,
        "debug_status": snapshot["status"],
        "count": snapshot["count"],
        "payment_ids": snapshot["payment_ids"],
    } == {
        "status": 400,
        "debug_status": 200,
        "count": 0,
        "payment_ids": [],
    }, {"response_body": response.text, "debug_body": snapshot["body"]}


@pytest.mark.parametrize(("field", "value"), INVALID_STRING_FIELDS)
def test_invalid_string_field_returns_422_without_observable_payment(
    api_client: PaymentsApiClient,
    field: str,
    value: Any,
) -> None:
    payload = make_payment_payload(beneficiary_prefix=f"invalid-{field}")
    invalid_payload = {**payload, field: value}
    observable_ref = payload["beneficiary_ref"]
    if field == "beneficiary_ref":
        observable_ref = value if isinstance(value, str) and value else None

    _assert_rejected_without_observable_payment(
        api_client=api_client,
        send_invalid=lambda key: api_client.create_payment(invalid_payload, key),
        invalid_description={"field": field, "value": value, "body": invalid_payload},
        observable_ref=observable_ref,
    )


@pytest.mark.parametrize("amount", INVALID_AMOUNTS)
def test_invalid_amount_returns_422_without_payment(
    api_client: PaymentsApiClient,
    amount: Any,
) -> None:
    payload = make_payment_payload(beneficiary_prefix="invalid-amount")
    invalid_payload = {**payload, "amount": amount}

    _assert_rejected_without_observable_payment(
        api_client=api_client,
        send_invalid=lambda key: api_client.create_payment(invalid_payload, key),
        invalid_description={"body": invalid_payload},
        observable_ref=payload["beneficiary_ref"],
    )


@pytest.mark.assumption
def test_unsupported_currency_returns_422_without_payment(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload(beneficiary_prefix="unsupported-currency")
    invalid_payload = {**payload, "currency": "EUR"}

    _assert_rejected_without_observable_payment(
        api_client=api_client,
        send_invalid=lambda key: api_client.create_payment(invalid_payload, key),
        invalid_description={"body": invalid_payload},
        observable_ref=payload["beneficiary_ref"],
    )


@pytest.mark.contract
@pytest.mark.parametrize(
    "missing_field",
    ["corridor", "amount", "currency", "beneficiary_ref"],
)
def test_missing_required_field_returns_422_without_observable_payment(
    api_client: PaymentsApiClient,
    missing_field: str,
) -> None:
    payload = make_payment_payload(beneficiary_prefix=f"missing-{missing_field}")
    invalid_payload = dict(payload)
    invalid_payload.pop(missing_field)
    observable_ref = (
        payload["beneficiary_ref"] if missing_field != "beneficiary_ref" else None
    )

    _assert_rejected_without_observable_payment(
        api_client=api_client,
        send_invalid=lambda key: api_client.create_payment(invalid_payload, key),
        invalid_description={"body": invalid_payload},
        observable_ref=observable_ref,
    )


def _raw_case(
    raw_body_factory: Callable[[str], str],
    case_id: str,
    bug: Optional[str] = None,
) -> Any:
    marks = [pytest.mark.contract]
    if bug:
        marks.append(pytest.mark.known_defect(bug))
    return pytest.param(raw_body_factory, id=case_id, marks=marks)


INVALID_JSON_DOCUMENTS = [
    _raw_case(
        lambda ref: (
            '{"corridor":"RUB/THB","amount":100000,"currency":"RUB",'
            f'"beneficiary_ref":"{ref}"'
        ),
        "malformed-json",
    ),
    _raw_case(lambda ref: "", "empty-body"),
    _raw_case(lambda ref: "null", "json-null", "BUG-008"),
    _raw_case(lambda ref: "[]", "json-array"),
    _raw_case(lambda ref: '"payment"', "json-string"),
    _raw_case(lambda ref: "123", "json-number", "BUG-008"),
    _raw_case(lambda ref: "true", "json-true", "BUG-008"),
    _raw_case(lambda ref: "false", "json-false", "BUG-008"),
]


@pytest.mark.parametrize("raw_body_factory", INVALID_JSON_DOCUMENTS)
def test_invalid_json_document_returns_422_without_observable_payment(
    api_client: PaymentsApiClient,
    raw_body_factory: Callable[[str], str],
) -> None:
    payload = make_payment_payload(beneficiary_prefix="invalid-document")
    raw_body = raw_body_factory(payload["beneficiary_ref"])
    observable_ref = (
        payload["beneficiary_ref"] if "beneficiary_ref" in raw_body else None
    )

    _assert_rejected_without_observable_payment(
        api_client=api_client,
        send_invalid=lambda key: api_client.create_payment_raw(raw_body, key),
        invalid_description={"raw_body": raw_body},
        observable_ref=observable_ref,
    )
