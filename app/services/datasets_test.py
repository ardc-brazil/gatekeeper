import unittest
from unittest.mock import MagicMock

from app.models.datasets import Datasets
from app.services.datasets import DatasetService

from werkzeug.exceptions import NotFound


class Test_Datasets(unittest.TestCase):

    def test_enable_dataset(self):
        # given
        repo = MagicMock()
        repo.fetch.return_value = Datasets()
        repo.upset.return_value = Datasets()

        target = DatasetService(repo, None, None)

        # when
        target.enable_dataset("dsid", "tenancy")

        # then
        repo.fetch.assert_called_once()
        repo.upsert.assert_called_once()

    def test_enable_dataset_dataset_not_found(self):
        # given
        repo = MagicMock()
        repo.fetch.return_value = None

        expected_dataset_id = "dsid"

        target = DatasetService(repo, None, None)

        # when
        with self.assertRaises(NotFound) as e:
            target.enable_dataset("dsid", "tenancy")

        # then
        self.assertEqual(404, e.exception.code)
        self.assertEqual(
            "Dataset %s not found" % expected_dataset_id, e.exception.description
        )
        repo.fetch.assert_not_called
        repo.upsert.assert_not_called


if __name__ == "__main__":
    unittest.main()
