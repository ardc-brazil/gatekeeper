# TODO the information in the headers depends on local database information. Different api keys and secrets are generated in each local env. Commenting for now so we can think on something about this.
# import unittest

# from app.main import fastAPIApp
# from fastapi.testclient import TestClient


# class TestDatasetFilterController(unittest.TestCase):
#     def setUp(self):
#         # TODO: how to mock the middlewares/interceptors?
#         # fastAPIApp.dependency_overrides[authorize] = mock_authorize
#         self.client = TestClient(fastAPIApp)

#     def test_get_datasets_filters(self):
#         # given
#         # TODO: How to create header parameters for testing and not depend on the database?
#         h = {
#             "X-Api-Key": "2836396d-7316-4db2-859b-d9047d4b3469",
#             "X-Api-Secret": "1234",
#             "X-User-Id": "09928f56-2e88-4a1c-a8fb-1393d092634f",
#             "X-Datamap-Tenancies": "datamap/production/data-amazon",
#         }

#         # when
#         response = self.client.get("/api/v1/datasets/filters", headers=h)

#         # then
#         assert response.status_code == 200

#         data = response.json()
#         for filter in data:
#             self.assertIsNotNone(filter["id"], "id from is None")
#             self.assertIsNotNone(filter["title"], "title from is None")
#             self.assertIsNotNone(filter["selection"], "selection from is None")


# if __name__ == "__main__":
#     unittest.main()
