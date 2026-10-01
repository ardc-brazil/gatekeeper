import unittest
from unittest.mock import Mock
from uuid import uuid4

from app.exception.forbidden import ForbiddenException
from app.service.dataset import DatasetService
from app.service.tus import TusService


def _payload(dataset_id) -> dict:
    return {
        "Type": "post-finish",
        "Event": {
            "Upload": {
                "Size": 10,
                "MetaData": {
                    "dataset_id": str(dataset_id),
                    "filename": "a.nc",
                    "filetype": "application/x-netcdf",
                },
                "Storage": {"Bucket": "datamap", "Key": "staged/abc"},
            }
        },
    }


class TestTusService(unittest.TestCase):
    def test_an_upload_the_access_rule_forbids_is_rejected(self):
        datasets = Mock(spec=DatasetService)
        datasets.create_data_file.side_effect = ForbiddenException("no")

        result = TusService(dataset_service=datasets).handle(
            payload=_payload(uuid4()), user_id=uuid4()
        )

        self.assertEqual(result.status_code, 403)
        self.assertTrue(result.reject_upload)
        self.assertEqual(result.body_msg, "upload_not_allowed")
