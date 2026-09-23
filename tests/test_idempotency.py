import json
from collections import Counter

import pytest

from api_client import PaymentsApiClient
from tests.assertions import (
    assert_payment_matches_payload,
    assert_single_payment,
    business_fields,
)
from tests.concurrency import (
    send_payment_variants_concurrently,
    send_payments_concurrently,
)
from tests.factories import (
    make_beneficiary_ref,
    make_idempotency_key,
    make_payment_payload,
)


pytestmark = [pytest.mark.contract, pytest.mark.idempotency]

CONCURRENT_REQUESTS = 20
CONCURRENT_ROUNDS = 3


def test_replay_with_equivalent_new_payload_returns_original_payment(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload()
    replay_payload = dict(payload)
    assert replay_payload is not payload
    idempotency_key = make_idempotency_key()

    first_response = api_client.create_payment(payload, idempotency_key)
    replay_response = api_client.create_payment(replay_payload, idempotency_key)
    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])

    assert first_response.status_code == 201, first_response.text
    assert replay_response.status_code == 200, replay_response.text
    first_id = assert_payment_matches_payload(first_response.json(), payload)
    replay_id = assert_payment_matches_payload(replay_response.json(), payload)
    assert replay_id == first_id
    stored_payment = assert_single_payment(debug_response, first_id)
    assert_payment_matches_payload(stored_payment, payload)


@pytest.mark.parametrize("serialization", ["reordered", "whitespace"])
def test_replay_with_equivalent_raw_json_returns_original_payment(
    api_client: PaymentsApiClient,
    serialization: str,
) -> None:
    payload = make_payment_payload()
    idempotency_key = make_idempotency_key()
    original_raw = json.dumps(payload, separators=(",", ":"))
    if serialization == "reordered":
        replay_payload = dict(reversed(list(payload.items())))
        replay_raw = json.dumps(replay_payload, separators=(",", ":"))
    else:
        replay_raw = json.dumps(payload, indent=4)

    first_response = api_client.create_payment_raw(
        original_raw,
        idempotency_key,
    )
    replay_response = api_client.create_payment_raw(
        replay_raw,
        idempotency_key,
    )
    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])

    assert first_response.status_code == 201, first_response.text
    assert replay_response.status_code == 200, replay_response.text
    first_id = assert_payment_matches_payload(first_response.json(), payload)
    replay_id = assert_payment_matches_payload(replay_response.json(), payload)
    assert replay_id == first_id
    stored_payment = assert_single_payment(debug_response, first_id)
    assert_payment_matches_payload(stored_payment, payload)


@pytest.mark.known_defect("BUG-001")
def test_reuse_key_with_changed_amount_returns_409_without_side_effect(
    api_client: PaymentsApiClient,
) -> None:
    original_payload = make_payment_payload()
    changed_payload = {
        **original_payload,
        "amount": original_payload["amount"] + 1,
    }
    idempotency_key = make_idempotency_key()

    first_response = api_client.create_payment(original_payload, idempotency_key)
    assert first_response.status_code == 201, first_response.text
    original_id = assert_payment_matches_payload(
        first_response.json(),
        original_payload,
    )

    conflict_response = api_client.create_payment(changed_payload, idempotency_key)
    stored_response = api_client.get_payment(original_id)
    debug_response = api_client.get_payments_by_ref(
        original_payload["beneficiary_ref"]
    )
    debug_data = debug_response.json()
    replay_response = api_client.create_payment(original_payload, idempotency_key)
    stored_payments = debug_data.get("payments", [])

    actual = {
        "conflict_status": conflict_response.status_code,
        "get_status": stored_response.status_code,
        "get_id": stored_response.json().get("payment_id"),
        "get_business_fields": business_fields(stored_response.json()),
        "debug_status": debug_response.status_code,
        "stored_business_fields": (
            business_fields(stored_payments[0])
            if len(stored_payments) == 1 else None
        ),
        "replay_status": replay_response.status_code,
        "replay_id": replay_response.json().get("payment_id"),
        "count": debug_data.get("count"),
        "payment_ids": [
            item.get("payment_id") for item in stored_payments
        ],
    }
    expected = {
        "conflict_status": 409,
        "get_status": 200,
        "get_id": original_id,
        "get_business_fields": business_fields(original_payload),
        "debug_status": 200,
        "stored_business_fields": business_fields(original_payload),
        "replay_status": 200,
        "replay_id": original_id,
        "count": 1,
        "payment_ids": [original_id],
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "idempotency_key": idempotency_key,
        "beneficiary_ref": original_payload["beneficiary_ref"],
        "conflict_body": conflict_response.text,
        "get_body": stored_response.text,
        "debug_body": debug_response.text,
        "replay_body": replay_response.text,
    }


@pytest.mark.known_defect("BUG-001")
def test_reuse_key_with_changed_beneficiary_returns_409_without_side_effect(
    api_client: PaymentsApiClient,
) -> None:
    original_payload = make_payment_payload()
    changed_payload = make_payment_payload(
        beneficiary_prefix="changed-beneficiary",
        corridor=original_payload["corridor"],
        amount=original_payload["amount"],
        currency=original_payload["currency"],
    )
    idempotency_key = make_idempotency_key()

    first_response = api_client.create_payment(original_payload, idempotency_key)
    assert first_response.status_code == 201, first_response.text
    original_id = assert_payment_matches_payload(
        first_response.json(),
        original_payload,
    )

    conflict_response = api_client.create_payment(changed_payload, idempotency_key)
    stored_response = api_client.get_payment(original_id)
    original_debug = api_client.get_payments_by_ref(
        original_payload["beneficiary_ref"]
    )
    changed_debug = api_client.get_payments_by_ref(
        changed_payload["beneficiary_ref"]
    )
    original_data = original_debug.json()
    changed_data = changed_debug.json()
    replay_response = api_client.create_payment(original_payload, idempotency_key)
    stored_payments = original_data.get("payments", [])

    actual = {
        "conflict_status": conflict_response.status_code,
        "get_status": stored_response.status_code,
        "get_id": stored_response.json().get("payment_id"),
        "get_business_fields": business_fields(stored_response.json()),
        "replay_status": replay_response.status_code,
        "replay_id": replay_response.json().get("payment_id"),
        "original_debug_status": original_debug.status_code,
        "original_count": original_data.get("count"),
        "original_ids": [
            item.get("payment_id") for item in stored_payments
        ],
        "stored_business_fields": (
            business_fields(stored_payments[0])
            if len(stored_payments) == 1 else None
        ),
        "changed_debug_status": changed_debug.status_code,
        "changed_count": changed_data.get("count"),
        "changed_ids": [
            item.get("payment_id") for item in changed_data.get("payments", [])
        ],
    }
    expected = {
        "conflict_status": 409,
        "get_status": 200,
        "get_id": original_id,
        "get_business_fields": business_fields(original_payload),
        "replay_status": 200,
        "replay_id": original_id,
        "original_debug_status": 200,
        "original_count": 1,
        "original_ids": [original_id],
        "stored_business_fields": business_fields(original_payload),
        "changed_debug_status": 200,
        "changed_count": 0,
        "changed_ids": [],
    }
    assert actual == expected, {
        "actual": actual,
        "expected": expected,
        "idempotency_key": idempotency_key,
        "original_ref": original_payload["beneficiary_ref"],
        "changed_ref": changed_payload["beneficiary_ref"],
        "conflict_body": conflict_response.text,
        "get_body": stored_response.text,
        "original_debug_body": original_debug.text,
        "changed_debug_body": changed_debug.text,
        "replay_body": replay_response.text,
    }


def test_create_with_different_keys_returns_different_payments(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload()

    first_response = api_client.create_payment(payload, make_idempotency_key())
    second_response = api_client.create_payment(payload, make_idempotency_key())
    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])

    assert first_response.status_code == 201, first_response.text
    assert second_response.status_code == 201, second_response.text
    first_id = assert_payment_matches_payload(first_response.json(), payload)
    second_id = assert_payment_matches_payload(second_response.json(), payload)
    assert first_id != second_id
    assert debug_response.status_code == 200, debug_response.text
    debug_data = debug_response.json()
    assert debug_data["count"] == 2, debug_data
    assert {item["payment_id"] for item in debug_data["payments"]} == {
        first_id,
        second_id,
    }


@pytest.mark.concurrency
@pytest.mark.known_defect("BUG-009")
def test_concurrent_replay_creates_exactly_one_payment(
    api_client: PaymentsApiClient,
) -> None:
    failures = []

    for round_number in range(1, CONCURRENT_ROUNDS + 1):
        payload = make_payment_payload(
            beneficiary_prefix=f"concurrent-{round_number}"
        )
        idempotency_key = make_idempotency_key(
            prefix=f"concurrent-{round_number}"
        )
        responses = send_payments_concurrently(
            base_url=api_client.base_url,
            timeout=api_client.timeout,
            payload=payload,
            idempotency_key=idempotency_key,
            requests_count=CONCURRENT_REQUESTS,
        )
        statuses = [response.status_code for response in responses]
        response_bodies = [response.json() for response in responses]
        response_ids = [body.get("payment_id") for body in response_bodies]
        response_details = [
            {
                "status": response.status_code,
                "payment_id": body.get("payment_id"),
                "business_fields": business_fields(body),
            }
            for response, body in zip(responses, response_bodies)
        ]
        debug_response = api_client.get_payments_by_ref(
            payload["beneficiary_ref"]
        )
        assert debug_response.status_code == 200, debug_response.text
        debug_data = debug_response.json()
        stored_ids = [
            item.get("payment_id") for item in debug_data.get("payments", [])
        ]
        unique_response_ids = set(response_ids)
        common_id = None
        get_status = None
        get_body = None
        if (
            len(unique_response_ids) == 1
            and None not in unique_response_ids
        ):
            common_id = next(iter(unique_response_ids))
            get_response = api_client.get_payment(common_id)
            get_status = get_response.status_code
            get_body = get_response.json()

        get_matches_instruction = (
            isinstance(get_body, dict)
            and all(
                get_body.get(field) == payload[field]
                for field in (
                    "corridor",
                    "amount",
                    "currency",
                    "beneficiary_ref",
                )
            )
        )
        stored_payment = (
            debug_data["payments"][0]
            if debug_data.get("count") == 1
            and len(debug_data.get("payments", [])) == 1
            else None
        )
        stored_matches_instruction = (
            isinstance(stored_payment, dict)
            and all(
                stored_payment.get(field) == payload[field]
                for field in (
                    "corridor",
                    "amount",
                    "currency",
                    "beneficiary_ref",
                )
            )
        )
        actual = {
            "status_counts": dict(Counter(statuses)),
            "all_responses_have_one_id": (
                common_id is not None and len(response_ids) == CONCURRENT_REQUESTS
            ),
            "stored_count": debug_data.get("count"),
            "stored_id_matches_responses": stored_ids == [common_id],
            "get_status": get_status,
            "get_matches_instruction": get_matches_instruction,
            "stored_matches_instruction": stored_matches_instruction,
        }
        expected = {
            "status_counts": {201: 1, 200: CONCURRENT_REQUESTS - 1},
            "all_responses_have_one_id": True,
            "stored_count": 1,
            "stored_id_matches_responses": True,
            "get_status": 200,
            "get_matches_instruction": True,
            "stored_matches_instruction": True,
        }
        if actual != expected:
            failures.append(
                {
                    "round": round_number,
                    "idempotency_key": idempotency_key,
                    "beneficiary_ref": payload["beneficiary_ref"],
                    "actual": actual,
                    "expected": expected,
                    "response_ids": response_ids,
                    "responses": response_details,
                    "stored_ids": stored_ids,
                    "debug_body": debug_response.text,
                    "get_body": get_body,
                }
            )

    if failures:
        pytest.fail(json.dumps(failures, ensure_ascii=False, indent=2))


@pytest.mark.concurrency
@pytest.mark.known_defect("BUG-001", "BUG-009")
def test_concurrent_different_bodies_with_one_key_create_one_payment(
    api_client: PaymentsApiClient,
) -> None:
    failures = []

    for round_number in range(1, CONCURRENT_ROUNDS + 1):
        first_payload = make_payment_payload(
            beneficiary_prefix=f"mixed-first-{round_number}"
        )
        second_payload = {
            **first_payload,
            "amount": first_payload["amount"] + 1,
            "beneficiary_ref": make_beneficiary_ref(
                f"mixed-second-{round_number}"
            ),
        }
        idempotency_key = make_idempotency_key(prefix=f"mixed-{round_number}")
        payloads = [first_payload, second_payload] * 5

        attempts = send_payment_variants_concurrently(
            base_url=api_client.base_url,
            timeout=api_client.timeout,
            payloads=payloads,
            idempotency_key=idempotency_key,
        )
        response_details = []
        for submitted_payload, response in attempts:
            body = response.json()
            successful = response.status_code in {200, 201}
            response_details.append(
                {
                    "submitted_ref": submitted_payload["beneficiary_ref"],
                    "submitted_fields": business_fields(submitted_payload),
                    "status": response.status_code,
                    "payment_id": body.get("payment_id"),
                    "returned_fields": business_fields(body) if successful else None,
                    "matches_submitted_body": (
                        business_fields(body) == business_fields(submitted_payload)
                        if successful else None
                    ),
                    "body": response.text,
                }
            )

        first_before = api_client.get_payments_by_ref(
            first_payload["beneficiary_ref"]
        )
        second_before = api_client.get_payments_by_ref(
            second_payload["beneficiary_ref"]
        )
        assert first_before.status_code == 200, first_before.text
        assert second_before.status_code == 200, second_before.text
        first_data = first_before.json()
        second_data = second_before.json()
        stored_before = first_data["payments"] + second_data["payments"]
        before_snapshot = sorted(
            [dict(item) for item in stored_before],
            key=lambda item: str(item.get("payment_id")),
        )

        winner = None
        payment_id = None
        if len(stored_before) == 1:
            payment_id = stored_before[0].get("payment_id")
            stored_fields = business_fields(stored_before[0])
            if stored_fields == business_fields(first_payload):
                winner = "first"
            elif stored_fields == business_fields(second_payload):
                winner = "second"

        first_replay = api_client.create_payment(first_payload, idempotency_key)
        second_replay = api_client.create_payment(second_payload, idempotency_key)
        replay_details = []
        for variant, submitted_payload, response in (
            ("first", first_payload, first_replay),
            ("second", second_payload, second_replay),
        ):
            body = response.json()
            should_replay = variant == winner
            replay_details.append(
                {
                    "variant": variant,
                    "status": response.status_code,
                    "payment_id": body.get("payment_id"),
                    "matches_expected": (
                        response.status_code == 200
                        and body.get("payment_id") == payment_id
                        and business_fields(body) == business_fields(submitted_payload)
                        if should_replay
                        else response.status_code == 409
                    ),
                    "body": response.text,
                }
            )

        first_after = api_client.get_payments_by_ref(
            first_payload["beneficiary_ref"]
        )
        second_after = api_client.get_payments_by_ref(
            second_payload["beneficiary_ref"]
        )
        assert first_after.status_code == 200, first_after.text
        assert second_after.status_code == 200, second_after.text
        after_data_first = first_after.json()
        after_data_second = second_after.json()
        stored_after = after_data_first["payments"] + after_data_second["payments"]
        after_snapshot = sorted(
            [dict(item) for item in stored_after],
            key=lambda item: str(item.get("payment_id")),
        )

        get_response = api_client.get_payment(payment_id) if payment_id else None
        expected_payload = first_payload if winner == "first" else second_payload
        actual = {
            "allowed_concurrent_statuses": all(
                item["status"] in {200, 201, 409} for item in response_details
            ),
            "successful_responses_match_submitted_body": all(
                item["matches_submitted_body"] is True
                for item in response_details
                if item["status"] in {200, 201}
            ),
            "successful_responses_have_stored_id": all(
                item["payment_id"] == payment_id
                for item in response_details
                if item["status"] in {200, 201}
            ),
            "count_before_replay": first_data["count"] + second_data["count"],
            "stored_rows_before_replay": len(stored_before),
            "stored_variant_identified": winner is not None,
            "sequential_replays_match_contract": all(
                item["matches_expected"] for item in replay_details
            ),
            "count_after_replay": (
                after_data_first["count"] + after_data_second["count"]
            ),
            "stored_rows_after_replay": len(stored_after),
            "stored_data_unchanged": after_snapshot == before_snapshot,
            "get_status": get_response.status_code if get_response is not None else None,
            "get_matches_stored_variant": (
                business_fields(get_response.json()) == business_fields(expected_payload)
                and get_response.json().get("payment_id") == payment_id
                if get_response is not None and winner is not None
                else False
            ),
        }
        expected = {
            "allowed_concurrent_statuses": True,
            "successful_responses_match_submitted_body": True,
            "successful_responses_have_stored_id": True,
            "count_before_replay": 1,
            "stored_rows_before_replay": 1,
            "stored_variant_identified": True,
            "sequential_replays_match_contract": True,
            "count_after_replay": 1,
            "stored_rows_after_replay": 1,
            "stored_data_unchanged": True,
            "get_status": 200,
            "get_matches_stored_variant": True,
        }
        if actual != expected:
            failures.append(
                {
                    "round": round_number,
                    "idempotency_key": idempotency_key,
                    "first_payload": first_payload,
                    "second_payload": second_payload,
                    "actual": actual,
                    "expected": expected,
                    "concurrent_responses": response_details,
                    "sequential_replays": replay_details,
                    "first_debug_before": first_data,
                    "second_debug_before": second_data,
                    "first_debug_after": after_data_first,
                    "second_debug_after": after_data_second,
                    "get_body": get_response.text if get_response is not None else None,
                }
            )

    if failures:
        pytest.fail(json.dumps(failures, ensure_ascii=False, indent=2))
