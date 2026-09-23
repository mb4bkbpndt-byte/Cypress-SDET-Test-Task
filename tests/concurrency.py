from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any, Dict, List, Optional, Tuple

import requests

from api_client import PaymentsApiClient


def send_payments_concurrently(
    *,
    base_url: str,
    timeout: float,
    payload: Dict[str, Any],
    idempotency_key: str,
    requests_count: int,
    simulate: Optional[str] = None,
) -> List[requests.Response]:
    barrier = Barrier(requests_count)

    def send_request() -> requests.Response:
        client = PaymentsApiClient(base_url=base_url, timeout=timeout)
        try:
            barrier.wait(timeout=timeout)
            return client.create_payment(
                dict(payload),
                idempotency_key,
                simulate=simulate,
            )
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=requests_count) as executor:
        futures = [executor.submit(send_request) for _ in range(requests_count)]
        return [future.result(timeout=timeout + 2) for future in futures]


def send_payment_variants_concurrently(
    *,
    base_url: str,
    timeout: float,
    payloads: List[Dict[str, Any]],
    idempotency_key: str,
) -> List[Tuple[Dict[str, Any], requests.Response]]:
    barrier = Barrier(len(payloads))

    def send_request(payload: Dict[str, Any]) -> requests.Response:
        client = PaymentsApiClient(base_url=base_url, timeout=timeout)
        try:
            barrier.wait(timeout=timeout)
            return client.create_payment(dict(payload), idempotency_key)
        finally:
            client.close()

    submitted_payloads = [dict(payload) for payload in payloads]
    with ThreadPoolExecutor(max_workers=len(submitted_payloads)) as executor:
        futures = [
            executor.submit(send_request, payload) for payload in submitted_payloads
        ]
        return [
            (payload, future.result(timeout=timeout + 2))
            for payload, future in zip(submitted_payloads, futures)
        ]
