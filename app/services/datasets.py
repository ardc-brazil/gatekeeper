import logging
from uuid import UUID
from app.models.datasets import Datasets, DatasetVersions, DataFiles, DesignState
from app.repositories.datasets import DatasetRepository
from werkzeug.exceptions import NotFound
import json

from app.services.users import UsersService

repository = DatasetRepository()
user_service = UsersService()

class DatasetService:
    def _adapt_dataset(self, dataset):
        return {
            'id': dataset.id, 
            'name': dataset.name, 
            'data': json.dumps(dataset.data), 
            'is_enabled': dataset.is_enabled,
            'created_at': dataset.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': dataset.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'tenancy': dataset.tenancy,
            'versions': dataset.versions
        }

    # TODO fetch latest dataset version
    # TODO fetch dataset with all versions
    def fetch_dataset(self, dataset_id, is_enabled=True, tenancies=[]):
        try: 
            res = repository.fetch(dataset_id, is_enabled, tenancies)

            if res is not None:
                datasets = self._adapt_dataset(res)
                return datasets
            
            return None
        except Exception as e:
            logging.error(e)
            raise e

    def _get_latest_dataset_version(self, dataset):
        if dataset.versions:
            latest_version = sorted(dataset.versions, key=lambda x: x.created_at, reverse=True)[0]
            return latest_version
        else:
            return None

    def _bump_dataset_version(self, dataset):
        latest_version = self._get_latest_dataset_version(dataset)
        if (latest_version is None):
            latest_version = 0

        return int(latest_version) + 1

    def update_dataset(self, dataset_id, request_body, user_id):
        try: 
            dataset = repository.fetch(dataset_id)

            if dataset is None:
                raise NotFound(f'Dataset {dataset_id} not found')
            
            dataset.name = request_body['name']
            dataset.data = request_body['data']
            dataset.tenancy = request_body['tenancy']
            dataset.owner_id = user_id
            
            # create new version
            new_version = self._bump_dataset_version(dataset)
            dataset.versions = DatasetVersions(name=str(new_version),
                                               author_id=user_id)
            
            # attach files
            if 'files' in request_body:
                for file in request_body['files']:
                    dataset.files.append(DataFiles(name=file['name'],
                                                   size_bytes=file['size_bytes'],
                                                   extension=file['extension'],
                                                   format=file['format'],
                                                   storage_file_name=file['storage_file_name'],
                                                   storage_path=file['storage_path'],
                                                   author_id=user_id))

            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

    def create_dataset(self, request_body, user_id):
        try:
            dataset = Datasets(name=request_body['name'], 
                               data=request_body['data'], 
                               tenancy=request_body['tenancy'],
                               design_state=DesignState.DRAFT,
                               owner_id=user_id)
            
            # create new version
            dataset.versions.append(DatasetVersions(name='1',
                                                    design_state=DesignState.DRAFT,
                                                    created_by=user_id))
            
            # # attach files
            # if 'files' in request_body:
            #     for file in request_body['files']:
            #         dataset.files.append(DataFiles(name=file['name'],
            #                                        size_bytes=file['size_bytes'],
            #                                        extension=file['extension'],
            #                                        format=file['format'],
            #                                        storage_file_name=file['storage_file_name'],
            #                                        storage_path=file['storage_path'],
            #                                        author_id=user_id))

            created = repository.upsert(dataset)
            return {
                'dataset': {
                    'id': created.id,
                    'design_state': created.design_state.name,
                },
                'version': {
                    'id': created.versions[0].id,
                    'name': created.versions[0].name,
                    'design_state': created.versions[0].design_state.name,
                }
            }
        
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
        
    # TODO enable/disable dataset versions
    
    def fetch_available_filters(self):
        with open('app/resources/available_filters.json') as categories:
            return json.load(categories)
    
    # TODO search by version
    def search_datasets(self, query_params, tenancies=[]):
        try: 
            res = repository.search(query_params, tenancies)
            if res is not None:
                datasets = [self._adapt_dataset(dataset) for dataset in res]
                return datasets
            
            return []
        except Exception as e:
            logging.error(e)
            raise e

    def create_data_file(self, file, dataset_id: UUID, user_id: UUID):
        try:
            user = user_service.fetch_by_id(user_id)
            # dataset = self.fetch_dataset(dataset_id, tenancies=user.tenancies)
            # TODO use self.fetch_by_id when versions are fixed
            dataset = repository.fetch(dataset_id, True, user.tenancies)

            # TODO fetch latest not published version
            dataset.files.append(DataFiles(name=file['name'],
                                            size_bytes=file['size_bytes'],
                                            extension=file['extension'],
                                            format=file['format'],
                                            storage_file_name=file['storage_file_name'],
                                            storage_path=file['storage_path'],
                                            author_id=user_id))
            
            repository.upsert(dataset)
        except Exception as e:
            logging.error(e)
            raise e

