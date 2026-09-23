from typing import Any, Dict, Optional, Union

import requests


class PaymentsApiClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def close(self) -> None:
        self._session.close()

    def health(self) -> requests.Response:
        return self._session.get(
            f"{self.base_url}/health",
            timeout=self.timeout,
        )

    def create_payment(
        self,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
        simulate: Optional[str] = None,
    ) -> requests.Response:
        headers: Dict[str, str] = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        if simulate is not None:
            headers["X-Simulate"] = simulate

        return self._session.post(
            f"{self.base_url}/v1/payments",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

    def create_payment_raw(
        self,
        raw_body: Union[str, bytes],
        idempotency_key: Optional[str],
        simulate: Optional[str] = None,
    ) -> requests.Response:
        headers = {"Content-Type": "application/json"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        if simulate is not None:
            headers["X-Simulate"] = simulate

        return self._session.post(
            f"{self.base_url}/v1/payments",
            headers=headers,
            data=raw_body,
            timeout=self.timeout,
        )

    def get_payment(self, payment_id: str) -> requests.Response:
        return self._session.get(
            f"{self.base_url}/v1/payments/{payment_id}",
            timeout=self.timeout,
        )

    def get_payments_by_ref(
        self,
        beneficiary_ref: Optional[str],
    ) -> requests.Response:
        params = (
            {"beneficiary_ref": beneficiary_ref}
            if beneficiary_ref is not None
            else None
        )
        return self._session.get(
            f"{self.base_url}/debug/payments",
            params=params,
            timeout=self.timeout,
        )
