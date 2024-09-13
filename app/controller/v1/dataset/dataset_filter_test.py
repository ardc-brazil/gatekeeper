import unittest

from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize
from app.main import fastAPIApp
from fastapi.testclient import TestClient


class TestDatasetFilterController(unittest.TestCase):
    def setUp(self):
        fastAPIApp.dependency_overrides[authenticate] = lambda: None
        fastAPIApp.dependency_overrides[authorize] = lambda: None
        self.client = TestClient(fastAPIApp)

    def test_get_datasets_filters(self):
        # given
        # TODO: How to create header parameters for testing and not depend on the database?
        h = {
            "X-Api-Key": "5060b1a2-9aaf-48db-871a-0839007fd478",
            "X-Api-Secret": "g*aZkbWom3deiAX-vtoT",
            "X-User-Id": "cbb0a683-630f-4b86-8b45-91b90a6fce1c",
            "X-Datamap-Tenancies": "datamap/production/data-amazon",
        }

        # when
        response = self.client.get("/api/v1/datasets/filters", headers=h)

        # then
        assert response.status_code == 200

        data = response.json()
        for filter in data:
            self.assertIsNotNone(filter["id"], "id from is None")
            self.assertIsNotNone(filter["title"], "title from is None")
            self.assertIsNotNone(filter["selection"], "selection from is None")


if __name__ == "__main__":
    unittest.main()
