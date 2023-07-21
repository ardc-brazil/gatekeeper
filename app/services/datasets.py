class DatasetService:
    def fetch_dataset(self, dataset_id):
        return f'Dataset {dataset_id}'

    def fetch_all_datasets(self):
        return 'All Datasets'

    def update_dataset(self, dataset_id, request_body):
        return f'Update Dataset {dataset_id} {request_body}'

    def create_dataset(self, request_body):
        return f'Post Datasets {request_body}'
    
    def disable_dataset(self, dataset_id):
        return f'Delete Dataset {dataset_id}'