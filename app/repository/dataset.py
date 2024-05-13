from uuid import UUID
from app.model.dataset import DatasetQuery
from app.model.db.dataset import DatasetVersion, Dataset, DesignState
from sqlalchemy import and_, or_, cast, func, String
from sqlalchemy.sql.expression import true
from contextlib import AbstractContextManager
from sqlalchemy.orm import Session
from typing import Callable
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
        tenancies : list[str] =[],
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
                    Dataset.versions.any(DatasetVersion.is_enabled == version_is_enabled)
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

    def search(self, query_params: DatasetQuery, tenancies: list[str] = []) -> list[Dataset]:
        with self._session_factory() as session:
            query = session.query(Dataset)

            search_conditions = []

            # TODO Test these
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

            if query_params.full_text is not None:
                search_term = f'%{query_params.full_text}%'
                query = query.filter(
                    or_(
                        cast(Dataset.data, String).ilike(search_term),
                        Dataset.name.ilike(search_term),
                    )
                )

            if query_params.version is not None:
                query = query.filter(
                    Dataset.versions.any(DatasetVersion.name == query_params.version)
                )

            query = query.filter(Dataset.tenancy.in_(tenancies))

            return query.all()
