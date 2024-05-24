import unittest

from app.main import fastAPIApp
from fastapi.testclient import TestClient

# TODO: This was a tentative to mock the interceptor
# async def mock_authorize( request: Request, user_id: UUID, auth_service: AuthService):
#     print("authorization mocked")


class TestDatasetController(unittest.TestCase):
    def setUp(self):
        # TODO: how to mock the middlewares/interceptors?
        # fastAPIApp.dependency_overrides[authorize] = mock_authorize
        self.client = TestClient(fastAPIApp)

    def test_get_datasets(self):
        # TODO: How to create header parameters for testing and not depend on the database?
        h = {
            "X-Api-Key": "5060b1a2-9aaf-48db-871a-0839007fd478",
            "X-Api-Secret": "g*aZkbWom3deiAX-vtoT",
            "X-User-Id": "cbb0a683-630f-4b86-8b45-91b90a6fce1c",
            "X-Datamap-Tenancies": "datamap/production/data-amazon",
        }

        response = self.client.get("/api/v1/datasets?full_text=", headers=h)
        print(response)
        assert response.status_code == 200
        respDict = response.json()
        assert "content" in respDict, "expected 'content' in json response"
        assert "size" in respDict, "expected 'size' in json response"
        self.assertEqual(
            len(respDict["content"]),
            respDict["size"],
            "len(content) is different from content.size",
        )
        for c in respDict["content"]:
            self.assertIsNotNone(c["id"], "DatasetGetResponse.id from content is None")


if __name__ == "__main__":
    unittest.main()
