from app.model.dataset import DatasetVersion, Dataset
from app import db
from sqlalchemy import and_, or_, cast, func, String
from sqlalchemy.sql.expression import true


class DatasetRepository:
    def fetch(
        self,
        dataset_id,
        is_enabled=True,
        tenancies=[],
        latest_version=False,
        version_design_state=None,
        version_is_enabled=True,
    ):
        query = db.session.query(Dataset)
        query = query.filter(Dataset.id == dataset_id)

        if is_enabled:
            query = query.filter(Dataset.is_enabled == is_enabled)

        query = query.filter(Dataset.tenancy.in_(tenancies))

        if latest_version:
            subquery = (
                db.session.query(
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

    def upsert(self, dataset):
        if dataset.id is None:
            db.session.add(dataset)
        db.session.commit()
        db.session.refresh(dataset)
        return dataset

    def search(self, query_params, tenancies=[]):
        query = db.session.query(Dataset)

        search_conditions = []

        if query_params["categories"]:
            for category in query_params["categories"]:
                search_term = f"%{category.strip()}%"
                search_conditions.append(
                    Dataset.data["category"].astext.ilike(search_term)
                )

        if query_params["data_types"]:
            for data_type in query_params["data_types"]:
                search_term = f"%{data_type.strip()}%"
                search_conditions.append(
                    Dataset.data["data_type"].astext.ilike(search_term)
                )

        if query_params["level"]:
            search_conditions.append(
                Dataset.data["level"].astext.ilike(query_params["level"])
            )

        if search_conditions:
            query = query.filter(*search_conditions)

        if query_params["date_from"]:
            query = query.filter(Dataset.created_at >= query_params["date_from"])

        if query_params["date_to"]:
            query = query.filter(Dataset.created_at <= query_params["date_to"])

        if not query_params["include_disabled"]:
            query = query.filter(Dataset.is_enabled == true())

        if query_params["full_text"]:
            search_term = f'%{query_params["full_text"]}%'
            query = query.filter(
                or_(
                    cast(Dataset.data, String).ilike(search_term),
                    Dataset.name.ilike(search_term),
                )
            )

        if query_params["version"]:
            query = query.filter(
                Dataset.versions.any(DatasetVersion.name == query_params["version"])
            )

        query = query.filter(Dataset.tenancy.in_(tenancies))

        return query.all()
