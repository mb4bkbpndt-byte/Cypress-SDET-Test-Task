import pytest

from api_client import PaymentsApiClient
from tests.assertions import assert_payment_matches_payload, assert_single_payment
from tests.factories import make_idempotency_key, make_payment_payload


@pytest.mark.assumption
@pytest.mark.validation
def test_corrected_request_can_reuse_key_after_422(
    api_client: PaymentsApiClient,
) -> None:
    payload = make_payment_payload(beneficiary_prefix="corrected-after-422")
    invalid_payload = {key: value for key, value in payload.items() if key != "amount"}
    idempotency_key = make_idempotency_key(prefix="corrected-after-422")

    rejected_response = api_client.create_payment(invalid_payload, idempotency_key)
    before_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])
    assert rejected_response.status_code == 422, rejected_response.text
    assert before_response.status_code == 200, before_response.text
    assert before_response.json() == {"count": 0, "payments": []}

    corrected_response = api_client.create_payment(payload, idempotency_key)
    assert corrected_response.status_code == 201, corrected_response.text
    payment_id = assert_payment_matches_payload(corrected_response.json(), payload)

    after_response = api_client.get_payments_by_ref(payload["beneficiary_ref"])
    stored_payment = assert_single_payment(after_response, payment_id)
    assert_payment_matches_payload(stored_payment, payload)
