import dataclasses
import unittest
from unittest.mock import patch, MagicMock
from app.gateway.doi.resource import DOIPayload, Attributes, Creator, Title, Types, Data
from app.gateway.doi.doi import DOIGateway


class TestDOIGateway(unittest.TestCase):
    def setUp(self):
        creators = [Creator(name="Caio Maia")]
        titles = [Title(title="Test REST API")]
        types = Types(resourceTypeGeneral="Text")
        attributes = Attributes(
            prefix="10.1234",
            creators=creators,
            titles=titles,
            publisher="DataCite e.V.",
            publicationYear=2024,
            types=types,
            url="https://example.org",
            event="publish",
        )
        data = Data(attributes=attributes)
        self.doi_payload = DOIPayload(data=data)

        self.base_url = "https://api.datacite.org"
        self.repository = "test-repo"
        self.login = "test-login"
        self.password = "test-password"

        self.gateway = DOIGateway(
            base_url=self.base_url, 
            login=self.login, 
            password=self.password,
        )

    @patch("app.gateway.doi.doi.requests.post")
    def test_post_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "10.1234/test-doi"}}
        mock_post.return_value = mock_response

        response = self.gateway.post(doi=self.doi_payload)

        mock_post.assert_called_once_with(
            f"{self.base_url}/dois",
            headers=self.gateway._base_headers,
            auth=(self.login, self.password),
            json=dataclasses.asdict(self.doi_payload),
        )

        self.assertEqual(response, {"data": {"id": "10.1234/test-doi"}})

    @patch("app.gateway.doi.doi.requests.post")
    def test_post_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        with self.assertRaises(Exception) as context:
            self.gateway.post(self.doi_payload)

        self.assertTrue("Error creating DOI: Bad Request" in str(context.exception))

    @patch("app.gateway.doi.doi.requests.get")
    def test_get_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"id": "10.1234/test-doi"}}
        mock_get.return_value = mock_response

        response = self.gateway.get(repository=self.repository, identifier="test-doi")

        mock_get.assert_called_once_with(
            f"{self.base_url}/dois/{self.repository}/test-doi",
            headers=self.gateway._base_headers,
            auth=(self.login, self.password),
        )

        self.assertEqual(response, {"data": {"id": "10.1234/test-doi"}})

    @patch("app.gateway.doi.doi.requests.put")
    def test_update_success(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"id": f"{self.doi_payload.data.attributes.prefix}/test-doi"}}
        mock_put.return_value = mock_response

        response = self.gateway.update(doi=self.doi_payload, identifier=f"{self.doi_payload.data.attributes.prefix}/test-doi")

        mock_put.assert_called_once_with(
            f"{self.base_url}/dois/{self.doi_payload.data.attributes.prefix}/test-doi",
            headers=self.gateway._base_headers,
            auth=(self.login, self.password),
            json=dataclasses.asdict(self.doi_payload),
        )

        self.assertEqual(response, {"data": {"id": f"{self.doi_payload.data.attributes.prefix}/test-doi"}})

    @patch("app.gateway.doi.doi.requests.delete")
    def test_delete_success(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response

        self.gateway.delete(repository=self.repository, identifier="test-doi")

        mock_delete.assert_called_once_with(
            f"{self.base_url}/dois/{self.repository}/test-doi",
            headers=self.gateway._base_headers,
            auth=(self.login, self.password),
        )

    @patch("app.gateway.doi.doi.requests.delete")
    def test_delete_failure(self, mock_delete):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_delete.return_value = mock_response

        with self.assertRaises(Exception) as context:
            self.gateway.delete(repository=self.repository, identifier="invalid-doi")

        self.assertEqual("Error deleting DOI: Not Found", str(context.exception))


if __name__ == "__main__":
    unittest.main()
