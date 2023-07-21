from app.models.datasets import Datasets
from app.repositories.datasets import DatasetRepository

repository = DatasetRepository()

class DatasetService:
    def fetch_dataset(self, dataset_id):
        res = repository.fetch(dataset_id)
        datasets = [{"id": dataset.id, "name": dataset.name, "data": dataset.data} for dataset in res]
        return datasets

    def fetch_all_datasets(self):
        res = repository.fetch_all()
        datasets = [{"id": dataset.id, "name": dataset.name, "data": dataset.data} for dataset in res]
        return datasets

    def update_dataset(self, dataset_id, request_body):
        dataset = Datasets(id=dataset_id, name=request_body['name'], data=request_body['data'])
        repository.upsert(dataset)

    def create_dataset(self, request_body):
        dataset = Datasets(name=request_body['name'], data=request_body['data'])
        repository.upsert(dataset)
    
    def disable_dataset(self, dataset_id):
        dataset = Datasets(id=dataset_id, is_enabled=False)
        repository.upsert(dataset)