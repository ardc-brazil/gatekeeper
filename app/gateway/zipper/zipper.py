from uuid import UUID
import requests

from app.gateway.zipper.resource import CreateZipRequest, CreateZipResponse


class ZipperGateway:
    def __init__(self, base_url: str):
        self._base_url = base_url

    def create_zip(
        self,
        dataset_id: UUID,
        version: str,
        files: list[str],
        bucket: str,
        zip_name: str | None = None,
    ) -> CreateZipResponse:
        url = f"{self._base_url}/api/v1/datasets/{dataset_id}/versions/{version}/zip"
        data = CreateZipRequest(files=files, bucket=bucket)

        if zip_name:
            data.zip_name = zip_name

        response = requests.post(url=url, data=data.model_dump_json())

        if response.status_code != 201:
            raise Exception(f"Request failed with status {response.status_code}")

        json_response = response.json()

        return CreateZipResponse(
            id=json_response["id"],
            status=json_response["status"],
            name=json_response["name"],
        )
