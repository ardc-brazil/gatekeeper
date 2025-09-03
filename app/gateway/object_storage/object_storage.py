from datetime import timedelta
from io import BytesIO
from minio import Minio


class ObjectStorageGateway:
    def __init__(self, minio_client: Minio):
        self._minio_client = minio_client

    def get_pre_signed_url(
        self,
        bucket_name: str,
        object_name: str,
        original_file_name: str,
        expires_in: timedelta = timedelta(days=7),
    ) -> str:
        return self._minio_client.presigned_get_object(
            bucket_name=bucket_name,
            object_name=object_name,
            expires=expires_in,
            extra_query_params={
                "response-content-disposition": f"attachment; filename={original_file_name}"
            },
        )

    def put_file(
        self,
        bucket_name: str,
        object_name: str,
        file_data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """
        Store a file in MinIO object storage.

        Args:
            bucket_name: The name of the bucket to store the file in
            object_name: The name/path of the object in the bucket
            file_data: The file content as bytes
            content_type: The MIME type of the file (default: application/octet-stream)
        """
        data_stream = BytesIO(file_data)
        self._minio_client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data_stream,
            length=len(file_data),
            content_type=content_type,
        )

    def get_file(
        self,
        bucket_name: str,
        object_name: str,
    ) -> bytes:
        """
        Retrieve a file from MinIO object storage.

        Args:
            bucket_name: The name of the bucket containing the file
            object_name: The name/path of the object in the bucket

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If the object doesn't exist
        """
        response = None
        try:
            response = self._minio_client.get_object(
                bucket_name=bucket_name, object_name=object_name
            )
            return response.read()
        except Exception as e:
            # MinIO client raises various exceptions for missing objects
            # Convert to standard FileNotFoundError for consistent handling
            raise FileNotFoundError(
                f"Object not found: {bucket_name}/{object_name}"
            ) from e
        finally:
            # Ensure response is closed to free resources
            if response is not None:
                try:
                    response.close()
                    response.release_conn()
                except Exception:
                    # Ignore cleanup errors to avoid masking the original exception
                    pass
