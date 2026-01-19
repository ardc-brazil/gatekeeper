from uuid import UUID
from app.model.dataset import DatasetQuery, FileCollocationStatus, PaginatedResult
from app.model.db.dataset import DatasetVersion, Dataset, DesignState
from sqlalchemy import and_, or_, func, text
from sqlalchemy.sql.expression import true
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable, List, Optional
from app.exception.conflict import ConflictException
from sqlalchemy.exc import IntegrityError


class DatasetRepository:
    def __init__(
        self, session_factory: Callable[..., AbstractContextManager[Session]]
    ) -> None:
        self._session_factory = session_factory

    def fetch(
        self,
        dataset_id: UUID,
        is_enabled: bool = True,
        tenancies: list[str] = [],
        latest_version: bool = False,
        version_design_state: DesignState = None,
        version_is_enabled: bool = True,
    ) -> Dataset:
        with self._session_factory() as session:
            query = session.query(Dataset)
            query = query.filter(Dataset.id == dataset_id)

            if is_enabled:
                query = query.filter(Dataset.is_enabled == is_enabled)

            query = query.filter(Dataset.tenancy.in_(tenancies))

            if latest_version:
                subquery = (
                    session.query(
                        DatasetVersion.dataset_id,
                        func.max(DatasetVersion.created_at).label("max_created_at"),
                    )
                    .group_by(DatasetVersion.dataset_id)
                    .subquery()
                )

                query = query.join(subquery, subquery.c.dataset_id == Dataset.id).join(
                    DatasetVersion,
                    and_(
                        Dataset.id == DatasetVersion.dataset_id,
                        DatasetVersion.created_at == subquery.c.max_created_at,
                        DatasetVersion.design_state == version_design_state
                        if version_design_state
                        else True,
                        DatasetVersion.is_enabled == version_is_enabled,
                    ),
                )
            elif version_is_enabled:
                query = query.filter(
                    Dataset.versions.any(
                        DatasetVersion.is_enabled == version_is_enabled
                    )
                )

            return query.first()

    def upsert(self, dataset: Dataset) -> Dataset:
        try:
            with self._session_factory() as session:
                session.add(dataset)
                session.commit()
                session.refresh(dataset)
                return dataset
        except IntegrityError:
            raise ConflictException(f"dataset_already_exists: {dataset.id}")

    def search(
        self, query_params: DatasetQuery, tenancies: list[str] = []
    ) -> PaginatedResult:
        """
        Search datasets with full-text search and pagination.

        Returns a PaginatedResult containing:
        - items: list of Dataset objects for the current page
        - total_count: total number of matching datasets
        - page: current page number
        - page_size: number of items per page
        """
        with self._session_factory() as session:
            query = session.query(Dataset)

            search_conditions = []

            for category in query_params.categories:
                search_term = f"%{category.strip()}%"
                search_conditions.append(
                    Dataset.data["category"].astext.ilike(search_term)
                )

            for data_type in query_params.data_types:
                search_term = f"%{data_type.strip()}%"
                search_conditions.append(
                    Dataset.data["data_type"].astext.ilike(search_term)
                )

            if query_params.level is not None:
                search_conditions.append(
                    Dataset.data["level"].astext.ilike(query_params.level)
                )

            if search_conditions:
                query = query.filter(*search_conditions)

            if query_params.date_from is not None:
                query = query.filter(Dataset.created_at >= query_params.date_from)

            if query_params.date_to is not None:
                query = query.filter(Dataset.created_at <= query_params.date_to)

            if not query_params.include_disabled:
                query = query.filter(Dataset.is_enabled == true())

            if query_params.design_state is not None:
                query = query.filter(Dataset.design_state == query_params.design_state)

            if query_params.visibility is not None:
                query = query.filter(Dataset.visibility == query_params.visibility)

            if query_params.version is not None:
                query = query.filter(
                    Dataset.versions.any(DatasetVersion.name == query_params.version)
                )

            query = query.filter(Dataset.tenancy.in_(tenancies))

            # Full-text search with relevance ranking
            if query_params.full_text is not None and query_params.full_text.strip():
                # Use PostgreSQL full-text search with unaccent for accent-insensitive matching
                # plainto_tsquery safely handles user input (no special syntax needed)
                search_term = func.plainto_tsquery(
                    text("'simple'"), func.unaccent(query_params.full_text)
                )
                search_vector = func.to_tsvector(
                    text("'simple'"), func.coalesce(Dataset.search_vector, "")
                )

                query = query.filter(search_vector.op("@@")(search_term))

                # Order by relevance when searching
                query = query.order_by(
                    func.ts_rank(search_vector, search_term).desc(),
                    Dataset.created_at.desc(),
                )
            else:
                # Order by date when not searching
                query = query.order_by(Dataset.created_at.desc())

            # Get total count before pagination
            total_count = query.count()

            # Apply pagination
            page = max(1, query_params.page)
            page_size = max(1, min(100, query_params.page_size))
            offset = (page - 1) * page_size

            datasets = query.offset(offset).limit(page_size).all()

            return PaginatedResult(
                items=datasets,
                total_count=total_count,
                page=page,
                page_size=page_size,
            )

    def fetch_by_collocation_status(
        self, statuses: List[Optional[FileCollocationStatus]]
    ) -> List[Dataset]:
        """
        Fetch datasets by file collocation status.
        Supports None (NULL in DB) to fetch legacy datasets.
        """
        with self._session_factory() as session:
            query = session.query(Dataset)

            # Build OR condition for multiple statuses
            conditions = []
            for status in statuses:
                if status is None:
                    conditions.append(Dataset.file_collocation_status.is_(None))
                else:
                    conditions.append(Dataset.file_collocation_status == status)

            if conditions:
                query = query.filter(or_(*conditions))

            query = query.filter(Dataset.is_enabled == true())
            query = query.order_by(Dataset.created_at.asc())
            return query.all()
