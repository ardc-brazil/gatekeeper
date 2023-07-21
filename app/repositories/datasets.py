from app.models.datasets import Datasets
from app import db

class DatasetRepository:
    def fetch(self, dataset_id, is_enabled=True):
        return Datasets.query.filter_by(id=dataset_id, is_enabled=is_enabled).first()
    
    def fetch_all(self, is_enabled=True):
        return Datasets.query.filter_by(is_enabled=is_enabled).all()

    def upsert(self, dataset):
        if (dataset.id is not None):
            db.session.add(dataset)
        db.session.commit()
        