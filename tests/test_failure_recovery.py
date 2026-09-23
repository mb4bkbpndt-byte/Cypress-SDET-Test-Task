from collections import Counter

import pytest

from api_client import PaymentsApiClient
from tests.assertions import assert_payment_matches_payload, business_fields
from tests.concurrency import send_payments_concurrently
from tests.factories import make_idempotency_key, make_payment_payload


pytestmark = [
    pytest.mark.contract,
    pytest.mark.idempotency,
    pytest.mark.known_defect("BUG-004"),
]

RETRY_COUNT = 5
CONCURRENT_RETRY_COUNT = 20


def _create_payment_with_unknown_result(
    api_client: PaymentsApiClient,
    payload: dict,
    idempotency_key: str,
) -> str:
    failed_response = api_client.create_payment(
        payload,
        idempotency_key,
        simulate="fail-after-create",
    )
    assert failed_response.status_code == 500, failed_response.text

    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])
    assert debug_response.status_code == 200, debug_response.text
    debug_data = debug_response.json()
    assert debug_data["count"] == 1, {
        "stage": "before_retry",
        "idempotency_key": idempotency_key,
        "beneficiary_ref": payload["beneficiary_ref"],
        "debug_data": debug_data,
    }
    original_payment = debug_data["payments"][0]
    original_id = assert_payment_matches_payload(original_payment, payload)
    return original_id


def test_multiple_retries_after_fail_after_create_return_original_payment(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload(
        beneficiary_prefix="recovery-sequential"
    )
    idempotency_key = make_idempotency_key(prefix="recovery-sequential")
    original_id = _create_payment_with_unknown_result(
        api_client,
        payload,
        idempotency_key,
    )

    retry_responses = [
        api_client.create_payment(payload, idempotency_key)
        for _ in range(RETRY_COUNT)
    ]
    retry_statuses = [response.status_code for response in retry_responses]
    retry_bodies = [response.json() for response in retry_responses]
    retry_ids = [body.get("payment_id") for body in retry_bodies]
    get_response = api_client.get_payment(original_id)
    final_debug_response = api_client.get_payments_by_ref(
        payload["beneficiary_ref"]
    )
    final_debug_data = final_debug_response.json()

    actual = {
        "retry_statuses": retry_statuses,
        "retry_ids": retry_ids,
        "get_status": get_response.status_code,
        "debug_status": final_debug_response.status_code,
        "final_count": final_debug_data.get("count"),
        "final_ids": [
            item.get("payment_id")
            for item in final_debug_data.get("payments", [])
        ],
    }
    expected = {
        "retry_statuses": [200] * RETRY_COUNT,
        "retry_ids": [original_id] * RETRY_COUNT,
        "get_status": 200,
        "debug_status": 200,
        "final_count": 1,
        "final_ids": [original_id],
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "idempotency_key": idempotency_key,
        "beneficiary_ref": payload["beneficiary_ref"],
        "retry_bodies": retry_bodies,
        "get_body": get_response.text,
    }
    assert_payment_matches_payload(get_response.json(), payload)


def test_changed_amount_after_fail_after_create_returns_409(
    api_client: PaymentsApiClient,
) -> None:
    original_payload = make_payment_payload(
        beneficiary_prefix="recovery-amount"
    )
    changed_payload = {
        **original_payload,
        "amount": original_payload["amount"] + 1,
    }
    idempotency_key = make_idempotency_key(prefix="recovery-amount")
    original_id = _create_payment_with_unknown_result(
        api_client,
        original_payload,
        idempotency_key,
    )

    conflict_response = api_client.create_payment(changed_payload, idempotency_key)
    get_response = api_client.get_payment(original_id)
    original_replay = api_client.create_payment(
        original_payload,
        idempotency_key,
    )
    debug_response = api_client.get_payments_by_ref(
        original_payload["beneficiary_ref"]
    )
    debug_data = debug_response.json()
    get_body = get_response.json()
    stored_payments = debug_data.get("payments", [])

    actual = {
        "conflict_status": conflict_response.status_code,
        "replay_status": original_replay.status_code,
        "replay_id": original_replay.json().get("payment_id"),
        "get_status": get_response.status_code,
        "get_id": get_body.get("payment_id"),
        "get_business_fields": business_fields(get_body),
        "debug_status": debug_response.status_code,
        "count": debug_data.get("count"),
        "payment_ids": [item.get("payment_id") for item in stored_payments],
        "stored_business_fields": (
            business_fields(stored_payments[0])
            if len(stored_payments) == 1 else None
        ),
    }
    expected = {
        "conflict_status": 409,
        "replay_status": 200,
        "replay_id": original_id,
        "get_status": 200,
        "get_id": original_id,
        "get_business_fields": business_fields(original_payload),
        "debug_status": 200,
        "count": 1,
        "payment_ids": [original_id],
        "stored_business_fields": business_fields(original_payload),
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "idempotency_key": idempotency_key,
        "beneficiary_ref": original_payload["beneficiary_ref"],
        "conflict_body": conflict_response.text,
        "replay_body": original_replay.text,
        "get_body": get_response.text,
        "debug_body": debug_response.text,
    }


def test_changed_beneficiary_after_fail_after_create_returns_409(
    api_client: PaymentsApiClient,
) -> None:
    original_payload = make_payment_payload(
        beneficiary_prefix="recovery-beneficiary-original"
    )
    changed_payload = make_payment_payload(
        beneficiary_prefix="recovery-beneficiary-changed",
        corridor=original_payload["corridor"],
        amount=original_payload["amount"],
        currency=original_payload["currency"],
    )
    idempotency_key = make_idempotency_key(prefix="recovery-beneficiary")
    original_id = _create_payment_with_unknown_result(
        api_client,
        original_payload,
        idempotency_key,
    )

    conflict_response = api_client.create_payment(changed_payload, idempotency_key)
    get_response = api_client.get_payment(original_id)
    original_replay = api_client.create_payment(
        original_payload,
        idempotency_key,
    )
    original_debug = api_client.get_payments_by_ref(
        original_payload["beneficiary_ref"]
    )
    changed_debug = api_client.get_payments_by_ref(
        changed_payload["beneficiary_ref"]
    )
    original_data = original_debug.json()
    changed_data = changed_debug.json()
    get_body = get_response.json()
    stored_payments = original_data.get("payments", [])

    actual = {
        "conflict_status": conflict_response.status_code,
        "replay_status": original_replay.status_code,
        "replay_id": original_replay.json().get("payment_id"),
        "get_status": get_response.status_code,
        "get_id": get_body.get("payment_id"),
        "get_business_fields": business_fields(get_body),
        "original_debug_status": original_debug.status_code,
        "original_count": original_data.get("count"),
        "original_ids": [item.get("payment_id") for item in stored_payments],
        "stored_business_fields": (
            business_fields(stored_payments[0])
            if len(stored_payments) == 1 else None
        ),
        "changed_count": changed_data.get("count"),
        "changed_debug_status": changed_debug.status_code,
        "changed_ids": [
            item.get("payment_id") for item in changed_data.get("payments", [])
        ],
    }
    expected = {
        "conflict_status": 409,
        "replay_status": 200,
        "replay_id": original_id,
        "get_status": 200,
        "get_id": original_id,
        "get_business_fields": business_fields(original_payload),
        "original_debug_status": 200,
        "original_count": 1,
        "original_ids": [original_id],
        "stored_business_fields": business_fields(original_payload),
        "changed_count": 0,
        "changed_debug_status": 200,
        "changed_ids": [],
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "idempotency_key": idempotency_key,
        "original_ref": original_payload["beneficiary_ref"],
        "changed_ref": changed_payload["beneficiary_ref"],
        "conflict_body": conflict_response.text,
        "replay_body": original_replay.text,
        "get_body": get_response.text,
        "original_debug_body": original_debug.text,
        "changed_debug_body": changed_debug.text,
    }


@pytest.mark.concurrency
def test_concurrent_retries_after_fail_after_create_return_original_payment(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload(
        beneficiary_prefix="recovery-concurrent"
    )
    idempotency_key = make_idempotency_key(prefix="recovery-concurrent")
    original_id = _create_payment_with_unknown_result(
        api_client,
        payload,
        idempotency_key,
    )

    responses = send_payments_concurrently(
        base_url=api_client.base_url,
        timeout=api_client.timeout,
        payload=payload,
        idempotency_key=idempotency_key,
        requests_count=CONCURRENT_RETRY_COUNT,
    )
    statuses = [response.status_code for response in responses]
    response_bodies = [response.json() for response in responses]
    response_ids = [body.get("payment_id") for body in response_bodies]
    get_response = api_client.get_payment(original_id)
    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])
    debug_data = debug_response.json()

    actual = {
        "status_counts": dict(Counter(statuses)),
        "unique_response_ids": sorted(set(response_ids), key=str),
        "get_status": get_response.status_code,
        "debug_status": debug_response.status_code,
        "count": debug_data.get("count"),
        "payment_ids": [
            item.get("payment_id") for item in debug_data.get("payments", [])
        ],
    }
    expected = {
        "status_counts": {200: CONCURRENT_RETRY_COUNT},
        "unique_response_ids": [original_id],
        "get_status": 200,
        "debug_status": 200,
        "count": 1,
        "payment_ids": [original_id],
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "idempotency_key": idempotency_key,
        "beneficiary_ref": payload["beneficiary_ref"],
        "response_ids": response_ids,
        "response_bodies": response_bodies,
        "get_body": get_response.text,
    }
    assert_payment_matches_payload(get_response.json(), payload)
