import logging
from uuid import UUID
import json
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.unauthorized import UnauthorizedException
from app.model.doi import (
    DOI,
    Mode as DOIMode,
    State as DOIState,
    Publisher as DOIPublisher,
    Title as DOITitle,
    Identifier as DOIIdentifier,
    Creator as DOICreator,
)
from app.repository.dataset import DatasetRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.service.doi import DOIService
from app.service.user import UserService
from app.model.dataset import (
    Dataset,
    DatasetQuery,
    DatasetVersion,
    DataFile,
    DesignState,
)
from app.model.db.dataset import (
    Dataset as DatasetDBModel,
    DatasetVersion as DatasetVersionDBModel,
    DataFile as DataFileDBModel,
)
from app.model.db.doi import DOI as DOIDBModel
from app.adapter.doi import database_to_model


class DatasetService:
    def __init__(
        self,
        repository: DatasetRepository,
        version_repository: DatasetVersionRepository,
        user_service: UserService,
        doi_service: DOIService,
    ):
        self._logger = logging.getLogger("service:DatasetService")
        self._repository = repository
        self._version_repository = version_repository
        self._user_service = user_service
        self._doi_service = doi_service

    def _adapt_file(self, file: DataFileDBModel) -> DataFile:
        return DataFile(
            id=file.id,
            name=file.name,
            size_bytes=file.size_bytes,
            extension=file.extension,
            format=file.format,
            storage_file_name=file.storage_file_name,
            storage_path=file.storage_path,
            created_at=file.created_at,
            updated_at=file.updated_at,
            created_by=file.created_by,
        )

    def _adapt_version(self, version: DatasetVersionDBModel) -> DatasetVersion:
        return DatasetVersion(
            id=version.id,
            name=version.name,
            description=version.description,
            created_at=version.created_at,
            updated_at=version.updated_at,
            created_by=version.created_by,
            is_enabled=version.is_enabled,
            design_state=version.design_state,
            files=[self._adapt_file(file=file) for file in version.files],
        )

    def _adapt_dataset(self, dataset: DatasetDBModel) -> Dataset:
        current_version = self._get_current_dataset_version(versions=dataset.versions)
        return Dataset(
            id=dataset.id,
            name=dataset.name,
            data=dataset.data,
            is_enabled=dataset.is_enabled,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            tenancy=dataset.tenancy,
            design_state=dataset.design_state,
            versions=[
                self._adapt_version(version=version) for version in dataset.versions
            ],
            current_version=self._adapt_version(version=current_version)
            if current_version is not None
            else None,
        )

    def _get_current_dataset_version(
        self, versions: list[DatasetVersionDBModel]
    ) -> DatasetVersionDBModel:
        """Get current version from the most recent by created_at and if the design_state is PUBLISHED or DRAFT"""
        versions = sorted(
            versions, key=lambda version: version.created_at, reverse=True
        )
        for version in versions:
            if (
                version.design_state == DesignState.PUBLISHED
                or version.design_state == DesignState.DRAFT
            ):
                return version

    def _determine_tenancies(
        self, user_id: UUID, tenancies: list[str] = []
    ) -> list[str]:
        try:
            user = self._user_service.fetch_by_id(id=user_id)
        except NotFoundException:
            raise UnauthorizedException(
                f"unauthorized_tenancy '{tenancies}' for user '{user_id}'"
            )

        if not tenancies:
            tenancies = user.tenancies

        # TODO check for enabled tenancy, if is not enabled, remove from list
        if not set(tenancies).issubset(set(user.tenancies)):
            logging.warning(
                f"user {user_id} trying to query with unauthorized tenancy: {tenancies}"
            )
            raise UnauthorizedException(f"unauthorized_tenancy: {tenancies}")

        return tenancies

    def fetch_dataset(
        self,
        dataset_id: UUID,
        is_enabled: bool = True,
        user_id: UUID = None,
        tenancies: list[str] = [],
        latest_version: bool = False,
        version_design_state: DesignState = None,
        version_is_enabled: bool = True,
    ) -> Dataset | None:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            is_enabled=is_enabled,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
            latest_version=latest_version,
            version_design_state=version_design_state,
            version_is_enabled=version_is_enabled,
        )

        if dataset is None:
            return None

        return self._adapt_dataset(dataset=dataset)

    def update_dataset(
        self,
        dataset_id: UUID,
        dataset_request: Dataset,
        user_id: UUID,
        tenancies: list[str] = [],
    ) -> None:
        dataset_db: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
        )

        if dataset_db is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        if self._should_create_new_version(dataset_db, dataset_request):
            new_version = self._create_new_version(dataset_db, user_id)
            dataset_db.versions.append(new_version)

        dataset_db.name = dataset_request.name
        dataset_db.data = dataset_request.data
        dataset_db.tenancy = dataset_request.tenancy
        dataset_db.owner_id = user_id

        self._repository.upsert(dataset=dataset_db)

    def _should_create_new_version(
        self, dataset_db: DatasetDBModel, dataset_request: Dataset
    ) -> bool:
        # get draft dataset version
        draft_version: DatasetVersionDBModel = next(
            (
                v
                for v in dataset_db.versions
                if v.design_state == DesignState.DRAFT and v.is_enabled
            ),
            None,
        )

        # get published dataset version
        publish_version: DatasetVersionDBModel = next(
            (
                v
                for v in dataset_db.versions
                if v.design_state == DesignState.PUBLISHED and v.is_enabled
            ),
            None,
        )

        # check if valid datasets versions exists
        no_version_enabled = draft_version is None and publish_version is None

        return no_version_enabled

    def _create_new_version(
        self, dataset_db: DatasetDBModel, user_id: UUID
    ) -> DatasetVersionDBModel:
        new_version_name = (
            str(int(dataset_db.versions[-1].name) + 1) if dataset_db.versions else "1"
        )
        new_version = DatasetVersionDBModel(
            name=new_version_name,
            design_state=DesignState.DRAFT,
            created_by=user_id,
        )

        return new_version

    def create_dataset(self, dataset: Dataset, user_id: UUID) -> Dataset:
        dataset = DatasetDBModel(
            name=dataset.name,
            data=dataset.data,
            tenancy=dataset.tenancy,
            design_state=DesignState.DRAFT,
            owner_id=user_id,
        )

        # create new version
        dataset.versions.append(
            DatasetVersionDBModel(
                name="1", design_state=DesignState.DRAFT, created_by=user_id
            )
        )

        created: DatasetDBModel = self._repository.upsert(dataset=dataset)

        return self._adapt_dataset(dataset=created)

    def disable_dataset(self, dataset_id: UUID, tenancies: list[str] = []) -> None:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id, tenancies=tenancies
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        dataset.is_enabled = False

        self._repository.upsert(dataset=dataset)

    def enable_dataset(self, dataset_id: UUID, tenancies: list[str] = []) -> None:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id, is_enabled=False, tenancies=tenancies
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        dataset.is_enabled = True

        self._repository.upsert(dataset=dataset)

    def enable_dataset_version(
        self,
        dataset_id: UUID,
        user_id: UUID,
        version_name: str,
        tenancies: list[str] = [],
    ) -> None:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
            version_is_enabled=False,
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        version.is_enabled = True

        self._version_repository.upsert(dataset_version=version)

    def disable_dataset_version(
        self,
        dataset_id: UUID,
        user_id: UUID,
        version_name: str,
        tenancies: list[str] = [],
    ) -> None:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        if len(dataset.versions) <= 1:
            raise IllegalStateException("dataset_has_only_one_version")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        version.is_enabled = False

        self._version_repository.upsert(dataset_version=version)

    def fetch_available_filters(self) -> dict:
        with open("app/resources/available_filters.json") as categories:
            return json.load(categories)

    def search_datasets(
        self, query: DatasetQuery, user_id: UUID, tenancies: list[str] = []
    ) -> list[Dataset]:
        res: list[DatasetDBModel] = self._repository.search(
            query_params=query,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
        )

        if res is None:
            return []

        return [self._adapt_dataset(dataset=dataset) for dataset in res]

    def create_data_file(self, file: DataFile, dataset_id: UUID, user_id: UUID) -> None:
        dataset: DatasetDBModel = self.fetch_dataset(
            dataset_id=dataset_id, user_id=user_id
        )
        version: DatasetVersionDBModel = self._version_repository.fetch_draft_version(
            dataset_id=dataset.id
        )

        version.files.append(
            DataFileDBModel(
                name=file.name,
                size_bytes=file.size_bytes,
                extension=file.extension,
                format=file.format,
                storage_file_name=file.storage_file_name,
                storage_path=file.storage_path,
                created_by=user_id,
            )
        )

        self._version_repository.upsert(version)

    def publish_dataset_version(
        self,
        dataset_id: UUID,
        user_id: UUID,
        version_name: str,
        tenancies: list[str] = [],
    ) -> None:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id, tenancies),
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        version.design_state = DesignState.PUBLISHED
        self._version_repository.upsert(dataset_version=version)

        if dataset.design_state == DesignState.DRAFT:
            dataset.design_state = DesignState.PUBLISHED
            self._repository.upsert(dataset=dataset)

    def create_doi(
        self,
        dataset_id: UUID,
        version_name: str,
        doi: DOI,
        user_id: UUID,
        tenancies: list[str] = [],
    ) -> DOI:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id, tenancies),
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        doi.title = DOITitle(title=dataset.name)
        doi.creators = [
            DOICreator(name=author.name) for author in dataset.data.get("authors")
        ]
        doi.publication_year = dataset.created_at.year
        doi.publisher = DOIPublisher(publisher=dataset.data.get("institution"))
        doi.url = f"https://datamap.pcs.usp.br/doi/dataset/{dataset.id}/version/{version.name}"
        doi.state = DOIState.DRAFT

        created_doi: DOI = self._doi_service.create(doi)

        version.doi = DOIDBModel(
            identifier=created_doi.identifier.identifier,
            mode=created_doi.mode,
            prefix=created_doi.identifier.split("/")[0],
            suffix=created_doi.identifier.split("/")[1],
            url=created_doi.url,
            state=created_doi.state,
            created_by=user_id,
            version_id=version.id,
            doi=created_doi.provider_response,
        )
        self._version_repository.upsert(dataset_version=version)

        return created_doi

    def change_doi_state(
        self,
        dataset_id: UUID,
        version_name: str,
        new_state: DOIState,
        user_id: UUID,
        tenancies: list[str] = [],
    ):
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id, tenancies),
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        if version.doi is None:
            raise NotFoundException(f"not_found: DOI for version {version_name}")

        self._doi_service.update(
            doi=DOI(
                state=new_state,
                mode=DOIMode.AUTO,
                identifier=DOIIdentifier(identifier=version.doi.identifier),
            ),
            identifier=version.doi.identifier,
        )

        version.doi.state = new_state
        self._version_repository.upsert(dataset_version=version)

    def get_doi(
        self,
        dataset_id: UUID,
        version_name: str,
        user_id: UUID,
        tenancies: list[str] = [],
    ):
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id, tenancies),
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        if version.doi is None:
            raise NotFoundException(f"not_found: DOI for version {version_name}")

        return database_to_model(doi=version.doi)

    def delete_doi(
        self,
        dataset_id: UUID,
        version_name: str,
        user_id: UUID,
        tenancies: list[str] = [],
    ):
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id, tenancies),
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )

        if version is None:
            raise NotFoundException(
                f"not_found: {version_name} for dataset {dataset_id}"
            )

        if version.doi is None:
            raise NotFoundException(f"not_found: DOI for version {version_name}")

        self._doi_service.delete(identifier=version.doi.identifier)
        version.doi = None
        self._version_repository.upsert(dataset_version=version)
