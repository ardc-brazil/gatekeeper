import unittest
from unittest.mock import MagicMock
from app.model.doi import Mode as ModeModel, State as StateModel, Title as TitleModel
from app.model.db.doi import DOI as DOIDb
from app.adapter.doi import database_to_model, model_to_payload
from app.gateway.doi.resource import DOIPayload

class TestDOIAdapter(unittest.TestCase):
    
    def setUp(self):
        self.database_doi = MagicMock(spec=DOIDb)
        self.database_doi.identifier = "10.1234/example-doi"
        self.database_doi.mode = "AUTO"
        self.database_doi.prefix = "10.1234"
        self.database_doi.suffix = "example-doi"
        self.database_doi.url = "https://example.com/doi"
        self.database_doi.state = "DRAFT"
        self.database_doi.doi = {"title": "Test DOI", "creators": [{"name": "Creator One"}, {"name": "Creator Two"}], "publisher": "Test Publisher", "publication_year": 2024, "resource_type": "Text"}


    def test_database_to_model_success(self):
        result = database_to_model(self.database_doi)
        
        self.assertEqual(result.identifier, "10.1234/example-doi")
        self.assertEqual(result.title, "Test DOI")
        self.assertEqual(result.creators, [{"name": "Creator One"}, {"name": "Creator Two"}])
        self.assertEqual(result.publisher, "Test Publisher")
        self.assertEqual(result.publication_year, 2024)
        self.assertEqual(result.resource_type, "Text")
        self.assertEqual(result.url, "https://example.com/doi")
        self.assertEqual(result.mode, ModeModel.AUTO)
        self.assertEqual(result.state, StateModel.DRAFT)
        self.assertEqual(result.provider_response, {"title": "Test DOI", "creators": [{"name": "Creator One"}, {"name": "Creator Two"}], "publisher": "Test Publisher", "publication_year": 2024, "resource_type": "Text"})

    def test_database_to_model_invalid_mode(self):
        self.database_doi.mode = "INVALID_MODE"

        with self.assertRaises(KeyError):
            database_to_model(self.database_doi)

    def test_database_to_model_invalid_state(self):
        self.database_doi.state = "INVALID_STATE"

        with self.assertRaises(KeyError):
            database_to_model(self.database_doi)

    def test_model_to_payload_success(self):
        model = database_to_model(self.database_doi)
        payload = model_to_payload(model)
        
        self.assertIsInstance(payload, DOIPayload)
        self.assertEqual(payload.data.attributes.prefix, "10.1234")
        self.assertEqual(len(payload.data.attributes.creators), 2)
        self.assertEqual(payload.data.attributes.creators[0].name, "Creator One")
        self.assertEqual(payload.data.attributes.creators[1].name, "Creator Two")
        self.assertEqual(payload.data.attributes.titles[0].title, "Test DOI")
        self.assertEqual(payload.data.attributes.publisher, "Test Publisher")
        self.assertEqual(payload.data.attributes.publicationYear, 2024)
        self.assertEqual(payload.data.attributes.url, "https://example.com/doi")
        self.assertEqual(payload.data.attributes.types.resourceTypeGeneral, "Text")

    def test_model_to_payload_empty_creators(self):
        model = database_to_model(self.database_doi)
        model.creators = []
        payload = model_to_payload(model)
        
        self.assertEqual(payload.data.attributes.creators, [])
    
    def test_model_to_payload_missing_title(self):
        model = database_to_model(self.database_doi)
        model.title = TitleModel(title="")
        payload = model_to_payload(model)
        
        self.assertEqual(payload.data.attributes.titles[0].title.title, "")

    def test_model_to_payload_invalid_publication_year(self):
        model = database_to_model(self.database_doi)
        model.publication_year = 0
        payload = model_to_payload(model)
        
        self.assertEqual(payload.data.attributes.publicationYear, 0)

if __name__ == '__main__':
    unittest.main()
