"""Reads what the gatekeeper sent, from Mailpit's HTTP API."""

import os
import time

import requests

MAILPIT_URL = os.getenv("MAILPIT_URL", "http://localhost:8025")


class Mailpit:
    def __init__(self, base_url: str = MAILPIT_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def messages_to(self, address: str) -> list[dict]:
        response = requests.get(
            f"{self.base_url}/api/v1/search",
            params={"query": f'to:"{address}"'},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("messages", [])

    def wait_for(
        self, address: str, count: int = 1, timeout: float = 10.0
    ) -> list[dict]:
        deadline = time.monotonic() + timeout
        while True:
            found = self.messages_to(address)
            if len(found) >= count or time.monotonic() >= deadline:
                return found
            time.sleep(0.2)

    def message(self, message_id: str) -> dict:
        response = requests.get(
            f"{self.base_url}/api/v1/message/{message_id}", timeout=5
        )
        response.raise_for_status()
        return response.json()
