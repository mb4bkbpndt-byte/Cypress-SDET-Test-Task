import pytest

from api_client import PaymentsApiClient
from tests.assertions import (
    assert_payment_matches_payload,
    assert_single_payment,
)
from tests.factories import make_idempotency_key, make_payment_payload


pytestmark = pytest.mark.contract


@pytest.mark.smoke
def test_health_returns_ok(api_client: PaymentsApiClient) -> None:
    response = api_client.health()

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_create_payment_with_valid_data_returns_201(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload()

    response = api_client.create_payment(payload, make_idempotency_key())

    assert response.status_code == 201, response.text
    payment = response.json()
    payment_id = assert_payment_matches_payload(payment, payload)

    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])
    stored_payment = assert_single_payment(debug_response, payment_id)
    assert_payment_matches_payload(stored_payment, payload)


def test_get_created_payment_returns_current_payment_without_side_effects(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload()
    create_response = api_client.create_payment(payload, make_idempotency_key())
    assert create_response.status_code == 201, create_response.text
    payment_id = assert_payment_matches_payload(create_response.json(), payload)

    first_get_response = api_client.get_payment(payment_id)
    second_get_response = api_client.get_payment(payment_id)
    debug_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])

    assert first_get_response.status_code == 200, first_get_response.text
    assert second_get_response.status_code == 200, second_get_response.text
    assert_payment_matches_payload(first_get_response.json(), payload)
    assert_payment_matches_payload(second_get_response.json(), payload)
    assert first_get_response.json()["payment_id"] == payment_id
    assert second_get_response.json()["payment_id"] == payment_id
    stored_payment = assert_single_payment(debug_response, payment_id)
    assert_payment_matches_payload(stored_payment, payload)


def test_debug_payments_with_ref_returns_only_matching_payments(
    api_client: PaymentsApiClient,
) -> None:
    target_payload = make_payment_payload()
    other_payload = make_payment_payload()
    target_response = api_client.create_payment(
        target_payload,
        make_idempotency_key(),
    )
    other_response = api_client.create_payment(
        other_payload,
        make_idempotency_key(),
    )
    assert target_response.status_code == 201, target_response.text
    assert other_response.status_code == 201, other_response.text
    target_id = assert_payment_matches_payload(target_response.json(), target_payload)
    other_id = assert_payment_matches_payload(other_response.json(), other_payload)
    assert target_id != other_id

    debug_response = api_client.get_payments_by_ref(
        target_payload["beneficiary_ref"]
    )
    other_debug_response = api_client.get_payments_by_ref(
        other_payload["beneficiary_ref"]
    )

    stored_payment = assert_single_payment(debug_response, target_id)
    assert_payment_matches_payload(stored_payment, target_payload)
    other_stored_payment = assert_single_payment(other_debug_response, other_id)
    assert_payment_matches_payload(other_stored_payment, other_payload)


def test_debug_payments_without_ref_returns_400(
    api_client: PaymentsApiClient,
) -> None:
    response = api_client.get_payments_by_ref(None)

    assert response.status_code == 400, response.text
