import logging
from uuid import UUID
from app.models.tus import TusResult
from app.services.datasets import DatasetService

dataset_service = DatasetService()

class TusService:
    def handle_post_finish(self, payload: dict, user_id: UUID) -> TusResult:
        file_upload = payload['Event']['Upload']
        file_metadata = file_upload['MetaData']
        storage = file_upload['Storage']
        dataset_id = UUID(file_metadata['dataset_id'])
        file = {
            'name': file_metadata['filename'],
            'size_bytes': file_upload['Size'],
            'format': file_metadata['filetype'],
            'storage_file_name': file_upload['ID'],
            'storage_path': storage['Bucket'] + "/" + storage['Key'],
            'author_id': user_id
        }

        dataset_service.create_data_file(file, dataset_id, user_id)

        return TusResult(status_code=200, body_msg='')

    def handle(self, payload: dict, user_id: UUID) -> TusResult:
        try:
            hook_type = payload['Type']
    
            if hook_type == 'post-finish':
                return self.handle_post_finish(payload, user_id)
            else:
                return TusResult(200, '')
        except Exception as e:
            logging.error(e)
            return TusResult(status_code=500, body_msg=str(e), reject_upload=True)