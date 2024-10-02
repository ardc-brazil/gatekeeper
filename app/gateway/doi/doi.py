import dataclasses
import requests

from app.exception.not_found import NotFoundException
from app.gateway.doi.resource import DOIPayload


class DOIGateway:
    def __init__(self, base_url: str, login: str, password: str):
        self._base_url = base_url
        self._login = login
        self._password = password
        self._base_headers = {"Content-Type": "application/vnd.api+json"}

    def post(self, doi: DOIPayload) -> dict:
        url = f"{self._base_url}/dois"
        response = requests.post(
            url,
            headers=self._base_headers,
            auth=(self._login, self._password),
            json=dataclasses.asdict(doi),
        )

        if not response.status_code == 201:
            raise Exception(f"Error creating DOI: {response.text}")

        return response.json()

    def get(self, repository: str, identifier: str) -> dict:
        url = f"{self._base_url}/dois/{repository}/{identifier}"
        response = requests.get(
            url, headers=self._base_headers, auth=(self._login, self._password)
        )

        if response.status_code == 404:
            raise NotFoundException(f"not_found: {identifier}")

        if not response.status_code == 200:
            raise Exception(f"Error getting DOI: {response.text}")

        return response.json()

    def update(self, doi: DOIPayload, identifier: str) -> dict:
        url = f"{self._base_url}/dois/{identifier}"
        response = requests.put(
            url,
            headers=self._base_headers,
            auth=(self._login, self._password),
            json=dataclasses.asdict(doi),
        )

        if not response.status_code == 200:
            raise Exception(f"Error updating DOI: {response.text}")

        return response.json()

    def delete(self, repository: str,  identifier: str) -> None:
        url = f"{self._base_url}/dois/{repository}/{identifier}"
        response = requests.delete(
            url, headers=self._base_headers, auth=(self._login, self._password)
        )

        if not response.status_code == 204:
            raise Exception(f"Error deleting DOI: {response.text}")
