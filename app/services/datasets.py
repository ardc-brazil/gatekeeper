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
            'updated_at': dataset.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'tenancy': dataset.tenancy
        }
    
    def fetch_dataset(self, dataset_id, is_enabled=True, tenancies=[]):
        try: 
            res = repository.fetch(dataset_id, is_enabled, tenancies)

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
            dataset.tenancy = request_body['tenancy']
            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

    def create_dataset(self, request_body):
        try:
            dataset = Datasets(name=request_body['name'], data=request_body['data'], tenancy=request_body['tenancy'])
            return repository.upsert(dataset).id
        except Exception as e:
            logging.error(e)
            raise e
        
    def disable_dataset(self, dataset_id, tenancies=[]):
        try: 
            dataset = repository.fetch(dataset_id=dataset_id, tenancies=tenancies)

            if dataset is None:
                raise NotFound(f'Dataset {dataset_id} not found')
            
            dataset.is_enabled = False
            
            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e
    
    def enable_dataset(self, dataset_id, tenancies):
        try: 
            dataset = repository.fetch(dataset_id=dataset_id, is_enabled=False, tenancies=tenancies)

            if dataset is None:
                raise NotFound(f'Dataset {dataset_id} not found')
            
            dataset.id = dataset_id
            dataset.is_enabled = True
            dataset.name = dataset.name
            dataset.data = dataset.data
            dataset.tenancy = dataset.tenancy

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e
        
    def fetch_available_filters(self):
        with open('app/resources/available_filters.json') as categories:
            return json.load(categories)
    
    def search_datasets(self, query_params, tenancies=[]):
        try: 
            res = repository.search(query_params, tenancies)
            if res is not None:
                datasets = [self.__adapt_dataset(dataset) for dataset in res]
                return datasets
            
            return []
        except Exception as e:
            logging.error(e)
            raise e
