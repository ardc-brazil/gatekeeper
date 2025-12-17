import logging
from uuid import UUID
from typing import List

from app.exception.not_found import NotFoundException
from app.exception.bad_request import BadRequestException
from app.repository.dataset import DatasetRepository
from app.repository.datafile import DataFileRepository
from app.model.dataset import FileCollocationStatus
from app.model.db.dataset import Dataset as DatasetDBModel, DataFile as DataFileDBModel


class DatasetCollocationService:
    """Service for managing dataset file collocation operations."""

    def __init__(
        self,
        dataset_repository: DatasetRepository,
        datafile_repository: DataFileRepository,
    ):
        self._logger = logging.getLogger("service:DatasetCollocationService")
        self._dataset_repository = dataset_repository
        self._datafile_repository = datafile_repository

    def get_pending_datasets(self) -> List[DatasetDBModel]:
        """
        Fetch all datasets with file_collocation_status IS NULL or 'PENDING'.
        NULL is treated as PENDING for legacy datasets.
        """
        self._logger.info("Fetching datasets pending file collocation")
        datasets = self._dataset_repository.fetch_by_collocation_status(
            statuses=[None, FileCollocationStatus.PENDING]
        )
        self._logger.info(f"Found {len(datasets)} datasets pending collocation")
        return datasets

    def get_dataset_files(self, dataset_id: UUID) -> List[DataFileDBModel]:
        """
        Fetch all files for a given dataset across all versions.
        """
        self._logger.info(f"Fetching files for dataset {dataset_id}")

        dataset = self._dataset_repository.fetch(dataset_id=dataset_id)
        if not dataset:
            dataset = self._dataset_repository.fetch(dataset_id=dataset_id, is_enabled=False)
            if not dataset:
                raise NotFoundException(f"Dataset not found: {dataset_id}")

        # Get all files from all versions of the dataset
        files = self._datafile_repository.fetch_by_dataset_id(dataset_id=dataset_id)
        self._logger.info(f"Found {len(files)} files for dataset {dataset_id}")
        return files

    def update_file_path(self, file_id: UUID, new_path: str) -> None:
        """
        Update the storage_path for a specific file.
        """
        self._logger.info(f"Updating storage path for file {file_id} to {new_path}")

        file = self._datafile_repository.fetch_by_id(id=file_id)
        if not file:
            raise NotFoundException(f"File not found: {file_id}")

        file.storage_path = new_path
        self._datafile_repository.upsert(file=file)
        self._logger.info(f"Successfully updated storage path for file {file_id}")

    def update_collocation_status(self, dataset_id: UUID, status: str) -> None:
        """
        Update the file_collocation_status for a dataset.
        """
        self._logger.info(
            f"Updating file collocation status for dataset {dataset_id} to {status}"
        )

        # Validate status
        try:
            status_enum = FileCollocationStatus(status)
        except ValueError:
            raise BadRequestException(
                f"Invalid status: {status}. Must be one of: {[s.value for s in FileCollocationStatus]}"
            )

        dataset = self._dataset_repository.fetch(dataset_id=dataset_id)
        if not dataset:
            dataset = self._dataset_repository.fetch(dataset_id=dataset_id, is_enabled=False)
            if not dataset:
                raise NotFoundException(f"Dataset not found: {dataset_id}")

        dataset.file_collocation_status = status_enum
        self._dataset_repository.upsert(dataset=dataset)
        self._logger.info(
            f"Successfully updated file collocation status for dataset {dataset_id}"
        )
