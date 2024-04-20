import logging
from uuid import UUID
from app.models.datasets import Datasets, DatasetVersions, DataFiles, DesignState
from app.repositories.dataset_versions import DatasetVersionRepository
from app.repositories.datasets import DatasetRepository
from werkzeug.exceptions import NotFound, BadRequest
import json

from app.services.users import UsersService

repository = DatasetRepository()
version_repository = DatasetVersionRepository()
user_service = UsersService()


class DatasetService:
    def _adapt_file(self, file):
        return {
            "id": file.id,
            "name": file.name,
            "size_bytes": file.size_bytes,
            "extension": file.extension,
            "format": file.format,
            "storage_file_name": file.storage_file_name,
            "storage_path": file.storage_path,
            "created_at": file.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": file.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "created_by": file.created_by,
        }

    def _adapt_version(self, version):
        return {
            "id": version.id,
            "name": version.name,
            "description": version.description,
            "created_at": version.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": version.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "created_by": version.created_by,
            "is_enabled": version.is_enabled,
            "design_state": version.design_state.name,
            "files": [self._adapt_file(file) for file in version.files],
        }

    def _adapt_dataset(self, dataset):
        return {
            "id": dataset.id,
            "name": dataset.name,
            "data": json.dumps(dataset.data),
            "is_enabled": dataset.is_enabled,
            "created_at": dataset.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": dataset.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "tenancy": dataset.tenancy,
            "versions": [self._adapt_version(version) for version in dataset.versions],
        }

    def _determine_tenancies(self, user_id, tenancies=[]):
        user = user_service.fetch_by_id(user_id)
        user_tenancies = user.get("tenancies", [])

        if not tenancies:
            tenancies = user_tenancies

        if not set(tenancies).issubset(set(user_tenancies)):
            logging.warn(
                f"user {user_id} trying to query with unauthorized tenancy: {tenancies}"
            )
            raise NotFound()

        return tenancies

    def fetch_dataset(
        self,
        dataset_id,
        is_enabled=True,
        user_id=None,
        tenancies=[],
        latest_version=False,
        version_design_state=None,
        version_is_enabled=True,
    ):
        try:
            dataset = repository.fetch(
                dataset_id=dataset_id,
                is_enabled=is_enabled,
                tenancies=self._determine_tenancies(user_id, tenancies),
                latest_version=latest_version,
                version_design_state=version_design_state,
                version_is_enabled=version_is_enabled,
            )

            if dataset is not None:
                return self._adapt_dataset(dataset)

            return None
        except Exception as e:
            logging.error(e)
            raise e

    def update_dataset(self, dataset_id, request_body, user_id, tenancies=[]):
        try:
            dataset = repository.fetch(
                dataset_id=dataset_id,
                tenancies=self._determine_tenancies(user_id, tenancies),
            )

            if dataset is None:
                raise NotFound(f"Dataset {dataset_id} not found")

            dataset.name = request_body["name"]
            dataset.data = request_body["data"]
            dataset.tenancy = request_body["tenancy"]
            dataset.owner_id = user_id

            # check if new version is needed and create it
            draft_version = next(
                (
                    v
                    for v in dataset.versions
                    if v.design_state == DesignState.DRAFT and v.is_enabled
                ),
                None,
            )

            if draft_version is None:
                new_version_name = (
                    str(int(dataset.versions[-1].name) + 1) if dataset.versions else "1"
                )
                new_version = DatasetVersions(
                    name=new_version_name,
                    design_state=DesignState.DRAFT,
                    created_by=user_id,
                )
                dataset.versions.append(new_version)

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

    def create_dataset(self, request_body, user_id):
        try:
            dataset = Datasets(
                name=request_body["name"],
                data=request_body["data"],
                tenancy=request_body["tenancy"],
                design_state=DesignState.DRAFT,
                owner_id=user_id,
            )

            # create new version
            dataset.versions.append(
                DatasetVersions(
                    name="1", design_state=DesignState.DRAFT, created_by=user_id
                )
            )

            created = repository.upsert(dataset)
            return {
                "dataset": {
                    "id": created.id,
                    "design_state": created.design_state.name,
                },
                "version": {
                    "id": created.versions[0].id,
                    "name": created.versions[0].name,
                    "design_state": created.versions[0].design_state.name,
                },
            }

        except Exception as e:
            logging.error(e)
            raise e

    def disable_dataset(self, dataset_id, tenancies=[]):
        try:
            dataset = repository.fetch(dataset_id=dataset_id, tenancies=tenancies)

            if dataset is None:
                raise NotFound(f"Dataset {dataset_id} not found")

            dataset.is_enabled = False

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

    def enable_dataset(self, dataset_id, tenancies):
        try:
            dataset = repository.fetch(
                dataset_id=dataset_id, is_enabled=False, tenancies=tenancies
            )

            if dataset is None:
                raise NotFound(f"Dataset {dataset_id} not found")

            dataset.id = dataset_id
            dataset.is_enabled = True
            dataset.name = dataset.name
            dataset.data = dataset.data
            dataset.tenancy = dataset.tenancy

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

    def enable_dataset_version(self, dataset_id, user_id, version_name, tenancies=[]):
        try:
            dataset = repository.fetch(
                dataset_id=dataset_id,
                tenancies=self._determine_tenancies(user_id, tenancies),
                version_is_enabled=False,
            )

            if dataset is None:
                raise NotFound(f"Dataset {dataset_id} not found")

            version = version_repository.fetch_version_by_name(dataset_id, version_name)

            if version is None:
                raise NotFound(
                    f"Version {version_name} not found for Dataset {dataset_id}"
                )

            version.is_enabled = True

            version_repository.upsert(version)
        except Exception as e:
            logging.error(e)
            raise e

    def disable_dataset_version(self, dataset_id, user_id, version_name, tenancies=[]):
        try:
            dataset = repository.fetch(
                dataset_id=dataset_id,
                tenancies=self._determine_tenancies(user_id, tenancies),
            )

            if dataset is None:
                raise NotFound(f"Dataset {dataset_id} not found")

            if len(dataset.versions) <= 1:
                raise BadRequest("Cannot disable the only version of the dataset")

            version = version_repository.fetch_version_by_name(dataset_id, version_name)

            if version is None:
                raise NotFound(
                    f"Version {version_name} not found for Dataset {dataset_id}"
                )

            version.is_enabled = False

            version_repository.upsert(version)
        except Exception as e:
            logging.error(e)
            raise e

    def fetch_available_filters(self):
        with open("app/resources/available_filters.json") as categories:
            return json.load(categories)

    def search_datasets(self, query_params, user_id, tenancies=[]):
        try:
            res = repository.search(
                query_params=query_params,
                tenancies=self._determine_tenancies(
                    user_id=user_id, tenancies=tenancies
                ),
            )
            if res is not None:
                datasets = [self._adapt_dataset(dataset) for dataset in res]
                return datasets

            return []
        except Exception as e:
            logging.error(e)
            raise e

    def create_data_file(self, file, dataset_id: UUID, user_id: UUID):
        try:
            dataset = self.fetch_dataset(dataset_id=dataset_id, user_id=user_id)
            version = version_repository.fetch_draft_version(dataset["id"])

            version.files.append(
                DataFiles(
                    name=file["name"],
                    size_bytes=file["size_bytes"],
                    extension=file["extension"],
                    format=file["format"],
                    storage_file_name=file["storage_file_name"],
                    storage_path=file["storage_path"],
                    created_by=user_id,
                )
            )

            version_repository.upsert(version)
        except Exception as e:
            logging.error(e)
            raise e
