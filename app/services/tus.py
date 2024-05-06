import logging
from uuid import UUID
from app.models.tus import TusResult
from app.repositories.dataset_versions import DatasetVersionRepository
from app.repositories.datasets import DatasetRepository
from app.services.datasets import DatasetService
import os

from app.services.users import UsersService

repository = DatasetRepository()
version_repository = DatasetVersionRepository()
user_service = UsersService()

dataset_service = DatasetService(repository, version_repository, user_service)


class TusService:
    def handle_post_finish(self, payload: dict, user_id: UUID) -> TusResult:
        file_upload = payload["Event"]["Upload"]
        file_metadata = file_upload["MetaData"]
        storage = file_upload["Storage"]
        dataset_id = UUID(file_metadata["dataset_id"])
        file = {
            "name": file_metadata["filename"],
            "size_bytes": file_upload["Size"],
            "format": file_metadata["filetype"],
            "extension": os.path.splitext(file_metadata["filename"])[1][1:].lower(),
            "storage_file_name": storage["Key"],
            "storage_path": storage["Bucket"] + "/" + storage["Key"],
            "author_id": user_id,
        }

        dataset_service.create_data_file(file, dataset_id, user_id)

        return TusResult(status_code=200, body_msg="")

    def handle(self, payload: dict, user_id: UUID) -> TusResult:
        try:
            hook_type = payload["Type"]

            if hook_type == "post-finish":
                return self.handle_post_finish(payload, user_id)
            else:
                return TusResult(200, "")
        except Exception as e:
            logging.error(e)
            return TusResult(status_code=500, body_msg=str(e), reject_upload=True)
