from app import db
from app.model.dataset import DatasetVersion
from sqlalchemy import desc


class DatasetVersionRepository:
    def fetch_draft_version(self, dataset_id):
        return (
            db.session.query(DatasetVersion)
            .filter_by(dataset_id=dataset_id, design_state="DRAFT")
            .order_by(desc(DatasetVersion.created_at))
            .first()
        )

    def upsert(self, dataset_version):
        if dataset_version.id is None:
            db.session.add(dataset_version)
        db.session.commit()
        db.session.refresh(dataset_version)
        return dataset_version

    def fetch_version_by_name(self, dataset_id, version_name):
        return (
            db.session.query(DatasetVersion)
            .filter_by(dataset_id=dataset_id, name=version_name)
            .first()
        )
