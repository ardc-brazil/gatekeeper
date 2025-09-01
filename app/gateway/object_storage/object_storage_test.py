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

        url = self.gateway.get_pre_signed_url(
            bucket_name=bucket, object_name=obj_name, original_file_name=file_name
        )

        self.mock_minio_client.presigned_get_object.assert_called_once_with(
            bucket_name=bucket,
            object_name=obj_name,
            expires=timedelta(days=7),
            extra_query_params={
                "response-content-disposition": f"attachment; filename={file_name}"
            },
        )

        self.assertEqual(url, expected_url)

    def test_get_pre_signed_url_custom_expiration(self):
        bucket = "test-bucket"
        obj_name = "test-file.txt"
        file_name = "download-file.txt"
        custom_exp = timedelta(hours=2)
        expected_url = "http://presigned.url.custom"

        self.mock_minio_client.presigned_get_object.return_value = expected_url

        url = self.gateway.get_pre_signed_url(
            bucket_name=bucket,
            object_name=obj_name,
            original_file_name=file_name,
            expires_in=custom_exp,
        )

        self.mock_minio_client.presigned_get_object.assert_called_once_with(
            bucket_name=bucket,
            object_name=obj_name,
            expires=custom_exp,
            extra_query_params={
                "response-content-disposition": f"attachment; filename={file_name}"
            },
        )

        self.assertEqual(url, expected_url)

    def test_put_file_default_content_type(self):
        bucket = "test-bucket"
        obj_name = "test-file.json"
        file_data = b'{"test": "data"}'
        
        self.gateway.put_file(
            bucket_name=bucket,
            object_name=obj_name,
            file_data=file_data
        )
        
        self.mock_minio_client.put_object.assert_called_once()
        call_args = self.mock_minio_client.put_object.call_args
        
        self.assertEqual(call_args[1]["bucket_name"], bucket)
        self.assertEqual(call_args[1]["object_name"], obj_name)
        self.assertEqual(call_args[1]["length"], len(file_data))
        self.assertEqual(call_args[1]["content_type"], "application/octet-stream")
        
        # Verify the data stream contains correct data
        data_arg = call_args[1]["data"]
        self.assertEqual(data_arg.read(), file_data)

    def test_put_file_custom_content_type(self):
        bucket = "test-bucket"
        obj_name = "test-file.json"
        file_data = b'{"test": "data"}'
        content_type = "application/json"
        
        self.gateway.put_file(
            bucket_name=bucket,
            object_name=obj_name,
            file_data=file_data,
            content_type=content_type
        )
        
        self.mock_minio_client.put_object.assert_called_once()
        call_args = self.mock_minio_client.put_object.call_args
        
        self.assertEqual(call_args[1]["bucket_name"], bucket)
        self.assertEqual(call_args[1]["object_name"], obj_name)
        self.assertEqual(call_args[1]["length"], len(file_data))
        self.assertEqual(call_args[1]["content_type"], content_type)
        
        # Verify the data stream contains correct data
        data_arg = call_args[1]["data"]
        self.assertEqual(data_arg.read(), file_data)

    def test_get_file_success(self):
        bucket = "test-bucket"
        obj_name = "test-file.json"
        expected_data = b'{"test": "data"}'
        
        # Mock the MinIO response
        mock_response = MagicMock()
        mock_response.read.return_value = expected_data
        self.mock_minio_client.get_object.return_value = mock_response
        
        result = self.gateway.get_file(
            bucket_name=bucket,
            object_name=obj_name
        )
        
        self.mock_minio_client.get_object.assert_called_once_with(
            bucket_name=bucket,
            object_name=obj_name
        )
        mock_response.read.assert_called_once()
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()
        self.assertEqual(result, expected_data)

    def test_get_file_not_found(self):
        bucket = "test-bucket"
        obj_name = "missing-file.json"
        
        # Mock MinIO to raise an exception (any exception represents not found)
        self.mock_minio_client.get_object.side_effect = Exception("NoSuchKey")
        
        with self.assertRaises(FileNotFoundError) as context:
            self.gateway.get_file(
                bucket_name=bucket,
                object_name=obj_name
            )
        
        self.assertIn("Object not found", str(context.exception))
        self.assertIn(f"{bucket}/{obj_name}", str(context.exception))

    def test_get_file_successful_cleanup_after_read_failure(self):
        bucket = "test-bucket"
        obj_name = "test-file.json"
        
        # Mock the MinIO response where read fails but cleanup succeeds
        mock_response = MagicMock()
        mock_response.read.side_effect = Exception("Read failed")
        self.mock_minio_client.get_object.return_value = mock_response
        
        # Should raise FileNotFoundError for the read exception
        with self.assertRaises(FileNotFoundError) as context:
            self.gateway.get_file(
                bucket_name=bucket,
                object_name=obj_name
            )
        
        self.assertIn("Object not found", str(context.exception))
        # Verify cleanup methods were called
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    def test_get_file_cleanup_exception_handling(self):
        bucket = "test-bucket"
        obj_name = "test-file.json"
        
        # Mock the MinIO response where cleanup methods fail
        mock_response = MagicMock()
        mock_response.read.return_value = b"test data"
        mock_response.close.side_effect = Exception("Close failed")
        mock_response.release_conn.side_effect = Exception("Release failed")
        self.mock_minio_client.get_object.return_value = mock_response
        
        # Should still return data successfully despite cleanup failures
        result = self.gateway.get_file(
            bucket_name=bucket,
            object_name=obj_name
        )
        
        self.assertEqual(result, b"test data")
        # Verify cleanup was attempted
        mock_response.close.assert_called_once()
        # release_conn won't be called if close fails


if __name__ == "__main__":
    unittest.main()
