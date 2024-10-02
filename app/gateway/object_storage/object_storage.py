from datetime import timedelta
from minio import Minio


class ObjectStorageGateway:
    def __init__(self, minio_client: Minio):
        self._minio_client = minio_client
    
    def get_pre_signed_url(self, bucket_name: str, object_name: str, original_file_name: str, expires_in: timedelta = timedelta(days=7)) -> str:
        return self._minio_client.presigned_get_object(bucket_name=bucket_name, object_name=object_name, expires=expires_in, extra_query_params={"response-content-disposition": f"attachment; filename={original_file_name}"})
