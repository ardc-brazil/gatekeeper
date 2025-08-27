import logging
from uuid import UUID
import json
from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.exception.unauthorized import UnauthorizedException
from app.gateway.object_storage.object_storage import ObjectStorageGateway
from app.model.doi import (
    DOI,
    State as DOIState,
    Mode as DOIMode,
    Publisher as DOIPublisher,
    Title as DOITitle,
    Creator as DOICreator,
)
from app.repository.datafile import DataFileRepository
from app.repository.dataset import DatasetRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.service.doi import DOIService
from app.service.tenancy import TenancyService
from app.service.user import UserService
from app.model.dataset import (
    Dataset,
    DatasetQuery,
    DatasetVersion,
    DataFile,
    DesignState,
    VisibilityStatus,
)
from app.model.db.dataset import (
    Dataset as DatasetDBModel,
    DatasetVersion as DatasetVersionDBModel,
    DataFile as DataFileDBModel,
)
from app.adapter import doi as DOIAdapter


class DatasetService:
    def __init__(
        self,
        repository: DatasetRepository,
        version_repository: DatasetVersionRepository,
        data_file_repository: DataFileRepository,
        user_service: UserService,
        doi_service: DOIService,
        minio_gateway: ObjectStorageGateway,
        tenancy_service: TenancyService,
        dataset_bucket: str,
    ):
        self._logger = logging.getLogger("service:DatasetService")
        self._repository = repository
        self._version_repository = version_repository
        self._user_service = user_service
        self._doi_service = doi_service
        self._minio_gateway = minio_gateway
        self._dataset_bucket = dataset_bucket
        self._data_file_repository = data_file_repository
        self._tenancy_service = tenancy_service

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

    def _calculate_files_size_in_bytes(self, files: list[DataFileDBModel]) -> int:
        return sum([file.size_bytes or 0 for file in files])

    def _calculate_files_count(self, files: list[DataFileDBModel]) -> int:
        return len(files)

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
            files_in=[self._adapt_file(file=file) for file in version.files_in],
            files_size_in_bytes=self._calculate_files_size_in_bytes(version.files_in),
            files_count=self._calculate_files_count(version.files_in),
            doi=DOIAdapter.database_to_model(doi=version.doi) if version.doi else None,
        )

    def _adapt_minimal_version(self, version: DatasetVersionDBModel) -> DatasetVersion:
        return DatasetVersion(
            id=version.id,
            name=version.name,
            description=version.description,
            created_at=version.created_at,
            updated_at=version.updated_at,
            created_by=version.created_by,
            is_enabled=version.is_enabled,
            design_state=version.design_state,
            files_size_in_bytes=self._calculate_files_size_in_bytes(version.files_in),
            files_count=self._calculate_files_count(version.files_in),
            doi=DOIAdapter.database_to_model(doi=version.doi) if version.doi else None,
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
            visibility=dataset.visibility,
            versions=[
                self._adapt_version(version=version) for version in dataset.versions
            ],
            current_version=self._adapt_version(version=current_version)
            if current_version is not None
            else None,
        )

    def _adapt_minimal_dataset(self, dataset: DatasetDBModel) -> Dataset:
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
            visibility=dataset.visibility,
            versions=[
                self._adapt_minimal_version(version=version)
                for version in dataset.versions
            ],
            current_version=self._adapt_minimal_version(version=current_version)
            if current_version is not None
            else None,
        )

    def _adapt_dataset_version(
        self, dataset: DatasetDBModel, dataset_version: DatasetVersionDBModel
    ) -> Dataset:
        return Dataset(
            id=dataset.id,
            name=dataset.name,
            data=dataset.data,
            is_enabled=dataset.is_enabled,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            tenancy=dataset.tenancy,
            design_state=dataset.design_state,
            visibility=dataset.visibility,
            version=self._adapt_version(version=dataset_version),
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

        # Check if tenancy is enabled
        for tenancy in tenancies:
            database_tenancy = self._tenancy_service.fetch(name=tenancy)

            if not database_tenancy or not database_tenancy.is_enabled:
                tenancies.remove(tenancy)

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

        dataset_db.name = dataset_request.name
        dataset_db.data = dataset_request.data
        dataset_db.tenancy = dataset_request.tenancy
        dataset_db.owner_id = user_id

        if self._should_create_new_version(dataset_db, dataset_request):
            new_version = self._create_new_version(dataset_db, user_id)
            dataset_db.versions.append(new_version)
        else:
            # TODO Should we get the specific version for doi, updated the last doi or update all dois for each version?
            current_version = self._get_current_dataset_version(dataset_db.versions)
            if current_version and current_version.doi is not None:
                doi = self._create_doi_model(
                    doi=DOIAdapter.database_to_model(current_version.doi),
                    dataset=dataset_db,
                    version=current_version,
                    creator_id=user_id,
                )
                self._doi_service.update_metadata(doi=doi)

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

        if query.minimal:
            return [self._adapt_minimal_dataset(dataset=dataset) for dataset in res]

        return [self._adapt_dataset(dataset=dataset) for dataset in res]

    def create_data_file(self, file: DataFile, dataset_id: UUID, user_id: UUID) -> None:
        dataset: DatasetDBModel = self.fetch_dataset(
            dataset_id=dataset_id, user_id=user_id
        )
        version: DatasetVersionDBModel = self._version_repository.fetch_draft_version(
            dataset_id=dataset.id
        )

        version.files_in.append(
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

    def _create_doi_model(
        self,
        doi: DOI,
        dataset: DatasetDBModel,
        version: DatasetVersionDBModel,
        creator_id: UUID,
    ) -> DOI:
        doi.title = DOITitle(title=dataset.name)

        doi.creators = [
            DOICreator(name=author["name"])
            for author in dataset.data.get("authors", [])
        ]
        doi.publication_year = dataset.created_at.year
        doi.publisher = (
            DOIPublisher(publisher=dataset.data.get("institution"))
            if dataset.data.get("institution")
            else None
        )
        doi.url = f"https://datamap.pcs.usp.br/doi/datasets/{dataset.id}/versions/{version.name}"
        doi.state = DOIState.DRAFT
        doi.dataset_version_name = version.name
        doi.dataset_id = dataset.id
        doi.dataset_version_id = version.id
        doi.created_by = creator_id

        return doi

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

        if version.doi:
            raise BadRequestException(errors=[ErrorDetails(code="already_exists")])

        doi = self._create_doi_model(
            doi=doi, dataset=dataset, version=version, creator_id=user_id
        )

        created_doi: DOI = self._doi_service.create(doi=doi)
        
        # If this is a MANUAL DOI, publish the dataset snapshot immediately
        if doi.mode == DOIMode.MANUAL:
            try:
                self._publish_dataset_snapshot(
                    dataset_id=dataset_id,
                    version_name=version_name,
                    user_id=user_id,
                    tenancies=tenancies
                )
            except Exception as e:
                # Log the error but don't fail the DOI creation
                self._logger.error(
                    f"DOI created successfully but dataset publication failed for {dataset_id}-{version_name}: {str(e)}"
                )

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

        # Change the DOI state first
        self._doi_service.change_state(
            identifier=version.doi.identifier,
            new_state=new_state,
        )
        
        # If DOI is being published (changed to FINDABLE), publish the dataset snapshot
        if new_state == DOIState.FINDABLE:
            try:
                self._publish_dataset_snapshot(
                    dataset_id=dataset_id,
                    version_name=version_name,
                    user_id=user_id,
                    tenancies=tenancies
                )
            except Exception as e:
                # Log the error but don't fail the DOI state change
                self._logger.error(
                    f"DOI state changed successfully but dataset publication failed for {dataset_id}-{version_name}: {str(e)}"
                )

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

        if not version.doi:
            raise NotFoundException(f"not_found: DOI for version {version_name}")

        return DOIAdapter.database_to_model(doi=version.doi)

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

    def get_file_download_url(
        self,
        dataset_id: UUID,
        version_name: str,
        file_id: UUID,
        user_id: UUID,
        tenancies: list[str] = [],
    ) -> str:
        dataset: DatasetDBModel = self.fetch_dataset(
            dataset_id=dataset_id,
            user_id=user_id,
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

        file: DataFileDBModel = next(
            (file for file in version.files_in if file.id == file_id), None
        )

        if file is None:
            raise NotFoundException(f"not_found: {file_id}")

        return self._minio_gateway.get_pre_signed_url(
            bucket_name=self._dataset_bucket,
            object_name=file.storage_file_name,
            original_file_name=file.name,
        )

    def create_new_version(
        self,
        dataset_id: UUID,
        user_id: UUID,
        tenancies: list[str] = [],
        datafilesPreviouslyUploaded: list[str] = [],
    ) -> DatasetVersion:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
            version_is_enabled=False,
        )

        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")

        current_version = self._get_current_dataset_version(dataset.versions)
        if current_version.design_state == DesignState.DRAFT:
            current_version.is_enabled = False
            self._version_repository.upsert(current_version)

        new_version = self._create_new_version(dataset_db=dataset, user_id=user_id)
        new_version.dataset_id = dataset_id
        for file_id in datafilesPreviouslyUploaded:
            new_version.files_in.append(
                self._data_file_repository.fetch_by_id(id=file_id)
            )

        self._version_repository.upsert(dataset_version=new_version)

        return self._adapt_version(version=new_version)

    def fetch_dataset_version(
        self,
        dataset_id: UUID,
        version_name: str,
        user_id: UUID,
        tenancies: list[str] = [],
    ) -> Dataset:
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id=user_id, tenancies=tenancies),
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

        return self._adapt_dataset_version(dataset=dataset, dataset_version=version)

    def _get_latest_published_version(self, dataset: DatasetDBModel) -> DatasetVersionDBModel:
        """
        Get the latest published version of a dataset based on max(created_at).
        Returns the version with the most recent created_at that has a published DOI.
        """
        published_versions = [
            version for version in dataset.versions
            if version.is_enabled and version.doi is not None
        ]
        
        if not published_versions:
            return None
        
        # Sort by created_at descending and return the first (latest)
        return max(published_versions, key=lambda v: v.created_at)

    def _update_dataset_visibility(self, dataset: DatasetDBModel) -> None:
        """
        Update the dataset visibility to PUBLIC in the database.
        """
        dataset.visibility = VisibilityStatus.PUBLIC
        self._repository.upsert(dataset)

    def _create_dataset_json_snapshot(
        self, 
        dataset: DatasetDBModel, 
        version: DatasetVersionDBModel, 
        include_versions_list: bool = False
    ) -> dict:
        """
        Create a JSON snapshot of the dataset metadata for public consumption.
        """
        # Start with the base dataset data
        snapshot = dict(dataset.data) if dataset.data else {}
        
        # Add version-specific metadata
        snapshot.update({
            "dataset_id": str(dataset.id),
            "version_name": version.name,
            "doi_identifier": version.doi.identifier if version.doi else None,
            "doi_link": f"https://doi.org/{version.doi.identifier}" if version.doi else None,
            "doi_state": version.doi.state if version.doi else None,
            "publication_date": version.created_at.isoformat() if version.created_at else None,
        })
        
        # Add datafiles summary
        files = version.files_in or []
        
        # Calculate extension breakdown
        extension_stats = {}
        total_files = len(files)
        total_size = 0
        
        for file in files:
            # Extract file extension (including dot)
            if "." in file.name and len(file.name.split(".")) > 1:
                file_extension = "." + file.name.split(".")[-1]
            else:
                file_extension = "(no extension)"
            
            # Initialize stats for this extension if not exists
            if file_extension not in extension_stats:
                extension_stats[file_extension] = {"count": 0, "total_size_bytes": 0}
            
            # Update stats
            extension_stats[file_extension]["count"] += 1
            file_size = file.size_bytes or 0
            extension_stats[file_extension]["total_size_bytes"] += file_size
            total_size += file_size
        
        # Convert to list format
        extensions_breakdown = [
            {
                "extension": ext,
                "count": stats["count"],
                "total_size_bytes": stats["total_size_bytes"]
            }
            for ext, stats in extension_stats.items()
        ]
        
        # Sort by count descending, then by extension name
        extensions_breakdown.sort(key=lambda x: (-x["count"], x["extension"]))
        
        snapshot["files_summary"] = {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "extensions_breakdown": extensions_breakdown
        }
        
        # Add versions list for -latest.json files
        if include_versions_list:
            versions_info = []
            for v in dataset.versions:
                if v.is_enabled and v.doi is not None:
                    # For MANUAL DOIs, state should be FINDABLE
                    doi_state = "FINDABLE" if hasattr(v.doi, 'mode') and v.doi.mode == DOIMode.MANUAL else v.doi.state
                    versions_info.append({
                        "id": str(v.id),
                        "name": v.name,
                        "doi_identifier": v.doi.identifier,
                        "doi_state": doi_state,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                    })
            
            # Sort by created_at descending (most recent first)
            versions_info.sort(key=lambda x: x["created_at"], reverse=True)
            snapshot["versions"] = versions_info
        
        return snapshot

    def _publish_dataset_snapshot(
        self, 
        dataset_id: UUID, 
        version_name: str, 
        user_id: UUID, 
        tenancies: list[str]
    ) -> None:
        """
        Publish dataset snapshot by updating visibility and creating JSON files in object storage.
        """
        # Fetch the dataset
        dataset: DatasetDBModel = self._repository.fetch(
            dataset_id=dataset_id,
            tenancies=self._determine_tenancies(user_id, tenancies),
        )
        
        if dataset is None:
            raise NotFoundException(f"not_found: {dataset_id}")
        
        # Find the specific version
        version: DatasetVersionDBModel = self._version_repository.fetch_version_by_name(
            dataset_id=dataset_id, version_name=version_name
        )
        
        if version is None:
            raise NotFoundException(f"not_found: {version_name} for dataset {dataset_id}")
        
        try:
            # Step 1: Update dataset visibility to PUBLIC
            self._update_dataset_visibility(dataset)
            
            # Step 2: Create and store versioned snapshot
            version_snapshot = self._create_dataset_json_snapshot(dataset, version, include_versions_list=False)
            version_json_bytes = json.dumps(version_snapshot, indent=2).encode('utf-8')
            
            version_object_name = f"snapshots/{dataset_id}-{version_name}.json"
            self._minio_gateway.put_file(
                bucket_name="datamap",
                object_name=version_object_name,
                file_data=version_json_bytes,
                content_type="application/json"
            )
            
            # Step 3: Determine if this is the latest published version and create/update latest snapshot
            latest_version = self._get_latest_published_version(dataset)
            if latest_version and latest_version.id == version.id:
                latest_snapshot = self._create_dataset_json_snapshot(dataset, version, include_versions_list=True)
                latest_json_bytes = json.dumps(latest_snapshot, indent=2).encode('utf-8')
                
                latest_object_name = f"snapshots/{dataset_id}-latest.json"
                self._minio_gateway.put_file(
                    bucket_name="datamap",
                    object_name=latest_object_name,
                    file_data=latest_json_bytes,
                    content_type="application/json"
                )
            
            self._logger.info(
                f"Successfully published dataset snapshot for {dataset_id}-{version_name}"
            )
            
        except Exception as e:
            self._logger.error(
                f"Failed to publish dataset snapshot for {dataset_id}-{version_name}: {str(e)}"
            )
            # Re-raise the exception to let the caller handle it
            raise

    def get_dataset_latest_snapshot(self, dataset_id: UUID) -> dict:
        """
        Retrieve the latest dataset snapshot from object storage.
        
        Args:
            dataset_id: The dataset ID
            
        Returns:
            dict: The snapshot data
            
        Raises:
            NotFoundException: If the snapshot doesn't exist
        """
        object_name = f"snapshots/{dataset_id}-latest.json"
        
        try:
            file_bytes = self._minio_gateway.get_file(
                bucket_name="datamap",
                object_name=object_name
            )
            return json.loads(file_bytes.decode('utf-8'))
        except FileNotFoundError:
            raise NotFoundException(f"Latest snapshot not found for dataset {dataset_id}")
        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid JSON in snapshot {object_name}: {str(e)}")
            raise IllegalStateException(f"Corrupted snapshot data for dataset {dataset_id}")

    def get_dataset_version_snapshot(self, dataset_id: UUID, version_name: str) -> dict:
        """
        Retrieve a specific dataset version snapshot from object storage.
        
        Args:
            dataset_id: The dataset ID
            version_name: The version name
            
        Returns:
            dict: The snapshot data
            
        Raises:
            NotFoundException: If the snapshot doesn't exist
        """
        object_name = f"snapshots/{dataset_id}-{version_name}.json"
        
        try:
            file_bytes = self._minio_gateway.get_file(
                bucket_name="datamap",
                object_name=object_name
            )
            return json.loads(file_bytes.decode('utf-8'))
        except FileNotFoundError:
            raise NotFoundException(f"Snapshot not found for dataset {dataset_id} version {version_name}")
        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid JSON in snapshot {object_name}: {str(e)}")
            raise IllegalStateException(f"Corrupted snapshot data for dataset {dataset_id} version {version_name}")
