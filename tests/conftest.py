from typing import Iterator

import pytest

from api_client import PaymentsApiClient
from config import BASE_URL, REQUEST_TIMEOUT


@pytest.fixture(scope="session")
def api_client() -> Iterator[PaymentsApiClient]:
    client = PaymentsApiClient(
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT,
    )
    yield client
    client.close()
