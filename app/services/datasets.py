from datetime import datetime
import logging
from app.models.datasets import Datasets
from app.repositories.datasets import DatasetRepository

repository = DatasetRepository()

class DatasetService:
    def fetch_dataset(self, dataset_id):
        res = repository.fetch(dataset_id)
        if res is not None:
            datasets = [{"id": res.id, "name": res.name, "data": res.data, "is_enabled": res.is_enabled}]
            return datasets
        
        return None

    def fetch_all_datasets(self):
        res = repository.fetch_all()
        if res is not None:
            datasets = [{"id": dataset.id, "name": dataset.name, "data": dataset.data, "is_enabled": dataset.is_enabled} for dataset in res]
            return datasets
    
        return []

    def update_dataset(self, dataset_id, request_body):
        dataset = repository.fetch(dataset_id)
        if (dataset is not None):
            dataset.name = request_body['name']
            dataset.data = request_body['data']
            repository.upsert(dataset)
        else:
            raise Exception(f'Dataset {dataset_id} not found')

    def create_dataset(self, request_body):
        try:
            dataset = Datasets(name=request_body['name'], data=request_body['data'])
            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise Exception('An error occurred while creating the dataset')
    
    def disable_dataset(self, dataset_id):
        dataset = repository.fetch(dataset_id)
        if (dataset is not None):
            dataset = Datasets(id=dataset_id, is_enabled=False, name=dataset.name, data=dataset.data)
            repository.upsert(dataset)
        else:
            raise Exception(f'Dataset {dataset_id} not found')