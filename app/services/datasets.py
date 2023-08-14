import logging
from app.models.datasets import Datasets
from app.repositories.datasets import DatasetRepository
from werkzeug.exceptions import NotFound
import json

repository = DatasetRepository()

class DatasetService:
    def __adapt_dataset(self, dataset):
        return {
            'id': dataset.id, 
            'name': dataset.name, 
            'data': json.dumps(dataset.data), 
            'is_enabled': dataset.is_enabled,
            'created_at': dataset.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': dataset.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def fetch_dataset(self, dataset_id):
        
        try: 
            res = repository.fetch(dataset_id)

            if res is not None:
                datasets = self.__adapt_dataset(res)
                return datasets
            
            return None
        except Exception as e:
            logging.error(e)
            raise e

    def update_dataset(self, dataset_id, request_body):
        try: 
            dataset = repository.fetch(dataset_id)

            if dataset is None:
                raise NotFound(f'Dataset {dataset_id} not found')
            
            dataset.name = request_body['name']
            dataset.data = request_body['data']
            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

    def create_dataset(self, request_body):
        try:
            dataset = Datasets(name=request_body['name'], data=request_body['data'])
            return repository.upsert(dataset).id
        except Exception as e:
            logging.error(e)
            raise e
        
    def disable_dataset(self, dataset_id):
        try: 
            dataset = repository.fetch(dataset_id)

            if dataset is None:
                raise NotFound(f'Dataset {dataset_id} not found')
            
            dataset.id = dataset_id
            dataset.is_enabled = False
            dataset.name = dataset.name
            dataset.data = dataset.data

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e
    
    def enable_dataset(self, dataset_id):
        try: 
            dataset = repository.fetch(dataset_id, False)

            if dataset is None:
                raise NotFound(f'Dataset {dataset_id} not found')
            
            dataset.id = dataset_id
            dataset.is_enabled = True
            dataset.name = dataset.name
            dataset.data = dataset.data

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e
        
    def fetch_available_filters(self):
        with open('app/resources/available_filters.json') as categories:
            return json.load(categories)
    
    def search_datasets(self, query_params):
        try: 
            res = repository.search(query_params)
            if res is not None:
                datasets = [self.__adapt_dataset(dataset) for dataset in res]
                return datasets
            
            return []
        except Exception as e:
            logging.error(e)
            raise e
