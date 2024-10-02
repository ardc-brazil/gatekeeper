import unittest
from unittest.mock import MagicMock
from datetime import timedelta
from minio import Minio
from app.gateway.object_storage.object_storage import ObjectStorageGateway


class TestObjectStorageGateway(unittest.TestCase):
    def setUp(self):
        self.mock_minio_client = MagicMock(spec=Minio)
        self.gateway = ObjectStorageGateway(minio_client=self.mock_minio_client)
    
    def test_get_pre_signed_url_default_expiration(self):
        bucket = "test-bucket"
        obj_name = "test-file.txt"
        file_name = "download-file.txt"
        expected_url = "http://presigned.url"
        
        self.mock_minio_client.presigned_get_object.return_value = expected_url
        
        url = self.gateway.get_pre_signed_url(bucket_name=bucket, object_name=obj_name, original_file_name=file_name)
        
        self.mock_minio_client.presigned_get_object.assert_called_once_with(
            bucket_name=bucket,
            object_name=obj_name,
            expires=timedelta(days=7),
            extra_query_params={"response-content-disposition": f"attachment; filename={file_name}"}
        )
        
        self.assertEqual(url, expected_url)
    
    def test_get_pre_signed_url_custom_expiration(self):
        bucket = "test-bucket"
        obj_name = "test-file.txt"
        file_name = "download-file.txt"
        custom_exp = timedelta(hours=2)
        expected_url = "http://presigned.url.custom"
        
        self.mock_minio_client.presigned_get_object.return_value = expected_url
        
        url = self.gateway.get_pre_signed_url(bucket_name=bucket, object_name=obj_name, original_file_name=file_name, expires_in=custom_exp)
        
        self.mock_minio_client.presigned_get_object.assert_called_once_with(
            bucket_name=bucket,
            object_name=obj_name,
            expires=custom_exp,
            extra_query_params={"response-content-disposition": f"attachment; filename={file_name}"}
        )
        
        self.assertEqual(url, expected_url)

if __name__ == '__main__':
    unittest.main()
