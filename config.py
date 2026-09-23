import os


BASE_URL = os.getenv("PAYMENTS_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("PAYMENTS_REQUEST_TIMEOUT", "5"))
