from app import db
from app.models.datasets import DatasetVersions
from sqlalchemy import desc

class DatasetVersionRepository:
    def fetch_draft_version(self, dataset_id):
        return db.session.query(DatasetVersions) \
            .filter_by(dataset_id=dataset_id, design_state='DRAFT') \
            .order_by(desc(DatasetVersions.created_at)) \
            .first()
    
    def upsert(self, dataset_version):
        if (dataset_version.id is None):
            db.session.add(dataset_version)
        db.session.commit()
        db.session.refresh(dataset_version)
        return dataset_version
    