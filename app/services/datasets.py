from datetime import datetime
import logging
from app.models.datasets import Datasets
from app.repositories.datasets import DatasetRepository

repository = DatasetRepository()

class DatasetService:
    def __adapt_dataset(self, dataset):
        return {"id": dataset.id, "name": dataset.name, "data": dataset.data, "is_enabled": dataset.is_enabled}
    
    def fetch_dataset(self, dataset_id):
        res = repository.fetch(dataset_id)
        if res is not None:
            datasets = self.__adapt_dataset(res)
            return datasets
        
        return None

    def fetch_all_datasets(self):
        res = repository.fetch_all()
        if res is not None:
            datasets = [self.__adapt_dataset(dataset) for dataset in res]
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
    
    def fetch_categories(self):
        return ["Aerosols", "Precipitation", "Atmospheric State", "Cloud Properties", "Radiometric", "Surface Properties", 
                "Subsoil and Groundwater Properties", "Renewable Energy"]
    
    def search_datasets(self, query_params):
        res = repository.search(query_params)
        if res is not None:
            datasets = [self.__adapt_dataset(dataset) for dataset in res]
            return datasets
        
        return None