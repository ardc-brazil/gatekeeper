import unittest
from unittest.mock import MagicMock, patch
import uuid
from app.service.doi import DOIService
from app.gateway.doi.doi import DOIGateway
from app.repository.doi import DOIRepository
from app.model.doi import (
    DOI,
    Mode,
    State,
    Event,
    Title as TitleModel,
    Creator as CreatorModel,
)
from app.model.db.doi import DOI as DOIDb
from app.exception.bad_request import BadRequestException
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException


class TestDOIService(unittest.TestCase):
    def setUp(self):
        self.mock_gateway = MagicMock(spec=DOIGateway)
        self.mock_repository = MagicMock(spec=DOIRepository)
        self.doi_prefix = "10.1234"
        self.service = DOIService(
            doi_gateway=self.mock_gateway,
            doi_repository=self.mock_repository,
            doi_prefix=self.doi_prefix,
        )

    def test_validate_manual_doi_empty_identifier(self):
        doi = DOI(
            identifier="",
            mode=Mode.MANUAL,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        with self.assertRaises(BadRequestException) as context:
            self.service._validate_manual_doi(doi)

        self.assertEqual(len(context.exception.errors), 1)
        self.assertEqual(context.exception.errors[0].code, "empty")
        self.assertEqual(context.exception.errors[0].field, "identifier")

    def test_validate_manual_doi_valid(self):
        doi = DOI(
            identifier="10.1234/example-doi",
            mode=Mode.MANUAL,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        try:
            self.service._validate_manual_doi(doi)
        except BadRequestException:
            self.fail(
                "_validate_manual_doi() levantou BadRequestException inesperadamente!"
            )

    def test_validate_auto_doi_with_identifier(self):
        doi = DOI(
            identifier="10.1234/example-doi",
            mode=Mode.AUTO,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        with self.assertRaises(BadRequestException) as context:
            self.service._validate_auto_doi(doi)

        self.assertEqual(len(context.exception.errors), 1)
        self.assertEqual(context.exception.errors[0].code, "not_empty")
        self.assertEqual(context.exception.errors[0].field, "identifier")

    def test_validate_auto_doi_missing_fields(self):
        doi = DOI(
            identifier="",
            mode=Mode.AUTO,
            title=None,  # Empty field
            creators=[],  # Empty field
            publisher="",
            publication_year=None,
            resource_type=None,
            url=None,
            provider_response={},
        )

        with self.assertRaises(BadRequestException) as context:
            self.service._validate_auto_doi(doi)

        self.assertEqual(len(context.exception.errors), 6)
        expected_fields = [
            "title",
            "creators",
            "publisher",
            "publication_year",
            "resource_type",
            "url",
        ]
        actual_fields = [error.field for error in context.exception.errors]
        self.assertListEqual(sorted(actual_fields), sorted(expected_fields))
        for error in context.exception.errors:
            self.assertEqual(error.code, "missing_field")

    def test_validate_auto_doi_valid(self):
        doi = DOI(
            identifier="",
            mode=Mode.AUTO,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        try:
            self.service._validate_auto_doi(doi)
        except BadRequestException:
            self.fail(
                "_validate_auto_doi() levantou BadRequestException inesperadamente!"
            )

    def test_validate_doi_manual_mode_valid(self):
        doi = DOI(
            identifier="10.1234/example-doi",
            mode=Mode.MANUAL,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        with patch.object(self.service, "_validate_manual_doi") as mock_validate:
            self.service._validate_doi(doi)
            mock_validate.assert_called_once_with(doi)

    def test_validate_doi_auto_mode_valid(self):
        doi = DOI(
            identifier="",
            mode=Mode.AUTO,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        with patch.object(self.service, "_validate_auto_doi") as mock_validate:
            self.service._validate_doi(doi)
            mock_validate.assert_called_once_with(doi)

    def test_get_success(self):
        doi_identifier = "10.1234/example-doi"
        expected_doi = DOI(
            identifier=doi_identifier,
            mode=Mode.MANUAL,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )
        self.mock_gateway.get.return_value = expected_doi

        result = self.service.get(doi_identifier)

        self.mock_gateway.get.assert_called_once_with(doi_identifier)
        self.assertEqual(result, expected_doi)

    def test_get_from_database_success(self):
        identifier = "10.1234/example-doi"
        expected_doidb = DOIDb(
            id=uuid.uuid4(),
            identifier=identifier,
            mode="AUTO",
            state="DRAFT",
            doi={"data": {}},
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
        )
        self.mock_repository.fetch.return_value = expected_doidb

        result = self.service.get_from_database(identifier)

        self.mock_repository.fetch.assert_called_once_with(identifier=identifier)
        self.assertEqual(result, expected_doidb)

    def test_create_manual_mode_success(self):
        doi = DOI(
            identifier="10.1234/example-doi",
            mode=Mode.MANUAL,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        mock_doidb = DOIDb(
            id=1,
            identifier=doi.identifier,
            mode=doi.mode.name,
            state="DRAFT",
            doi=doi.provider_response,
            prefix=doi.identifier.split("/")[0],
            suffix=doi.identifier.split("/")[1],
            url=doi.url,
        )

        self.mock_repository.upsert.return_value = mock_doidb

        result = self.service.create(doi)

        self.mock_gateway.post.assert_not_called()
        self.mock_repository.upsert.assert_called_once()

        self.assertEqual(result.id, mock_doidb.id)
        self.assertEqual(result.identifier, doi.identifier)

    def test_create_auto_mode_success(self):
        doi = DOI(
            identifier="",  # Deve estar vazio para AUTO
            mode=Mode.AUTO,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        gateway_response = {"data": {"id": "10.1234/new-doi"}}
        self.mock_gateway.post.return_value = gateway_response

        mock_doidb = DOIDb(
            id=1,
            identifier=gateway_response["data"]["id"],
            mode=doi.mode.name,
            state="DRAFT",
            doi=gateway_response,
            prefix="10.1234",
            suffix="new-doi",
            url=doi.url,
        )

        self.mock_repository.upsert.return_value = mock_doidb

        result = self.service.create(doi)

        self.mock_gateway.post.assert_called_once()
        self.mock_repository.upsert.assert_called_once()

        self.assertEqual(result.id, mock_doidb.id)
        self.assertEqual(result.identifier, gateway_response["data"]["id"])
        self.assertEqual(result.provider_response, gateway_response)

    def test_create_auto_mode_gateway_fail(self):
        doi = DOI(
            identifier="",
            mode=Mode.AUTO,
            title=TitleModel(title="Test DOI"),
            creators=[CreatorModel(name="Creator One")],
            publisher="Test Publisher",
            publication_year=2024,
            resource_type="Text",
            url="https://example.com/doi",
            provider_response={},
        )

        self.mock_gateway.post.side_effect = Exception("Gateway error")

        with self.assertRaises(Exception) as context:
            self.service.create(doi)

        self.assertEqual(str(context.exception), "Gateway error")
        self.mock_gateway.post.assert_called_once()
        self.mock_repository.upsert.assert_not_called()

    def test_change_state_manual_mode_fail(self):
        identifier = "10.1234/example-doi"
        from_database = DOIDb(
            identifier=identifier,
            mode=Mode.MANUAL.name,
            state=State.DRAFT.name,
            doi={"data": {}},
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
        )

        self.mock_repository.fetch.return_value = from_database

        with self.assertRaises(IllegalStateException) as context:
            self.service.change_state(identifier=identifier, new_state=State.FINDABLE)

        self.assertEqual(str(context.exception), "manual_doi_cannot_change_state")
        self.mock_gateway.update.assert_not_called()
        self.mock_repository.upsert.assert_not_called()

    def test_change_state_auto_mode_valid_transition(self):
        identifier = "10.1234/example-doi"
        from_database = DOIDb(
            identifier=identifier,
            mode=Mode.AUTO.name,
            state=State.DRAFT.name,
            doi={"data": {}},
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
        )

        new_state = State.FINDABLE
        event = Event.PUBLISH

        self.mock_repository.fetch.return_value = from_database

        with patch.object(
            self.service, "_get_valid_event_from_state", return_value=event
        ) as mock_get_event:
            updated_doi = {"data": {"attributes": {"state": new_state.name}}}
            self.mock_gateway.update.return_value = updated_doi

            self.service.change_state(identifier=identifier, new_state=new_state)

            mock_get_event.assert_called_once_with(from_database, new_state)
            self.mock_gateway.update.assert_called_once()
            self.assertEqual(from_database.doi, updated_doi)
            self.assertEqual(from_database.state, new_state.name)
            self.mock_repository.upsert.assert_called_once_with(doi=from_database)

    def test_change_state_auto_mode_invalid_transition(self):
        identifier = "10.1234/example-doi"
        from_database = DOIDb(
            identifier=identifier,
            mode=Mode.AUTO.name,
            state=State.DRAFT.name,
            doi={"data": {}},
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
        )

        new_state = State.REGISTERED

        self.mock_repository.fetch.return_value = from_database

        with patch.object(
            self.service,
            "_get_valid_event_from_state",
            side_effect=IllegalStateException("invalid_state_transition"),
        ):
            with self.assertRaises(IllegalStateException) as context:
                self.service.change_state(identifier=identifier, new_state=new_state)

            self.assertEqual(str(context.exception), "invalid_state_transition")
            self.mock_gateway.update.assert_not_called()
            self.mock_repository.upsert.assert_not_called()

    def test_delete_not_found(self):
        identifier = "10.1234/non-existent-doi"

        self.mock_repository.fetch.return_value = None

        with self.assertRaises(NotFoundException) as context:
            self.service.delete(identifier=identifier)

        self.assertEqual(str(context.exception), f"not_found: {identifier}")
        self.mock_gateway.delete.assert_not_called()
        self.mock_repository.delete.assert_not_called()

    def test_delete_not_in_draft_state(self):
        identifier = "10.1234/example-doi"
        existing_doi = DOIDb(
            identifier=identifier,
            state=State.FINDABLE.name,
            mode=Mode.AUTO.name,
            doi={"data": {}},
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
        )

        self.mock_repository.fetch.return_value = existing_doi

        with self.assertRaises(IllegalStateException) as context:
            self.service.delete(identifier=identifier)

        self.assertEqual(str(context.exception), "doi_not_in_draft_state")
        self.mock_gateway.delete.assert_not_called()
        self.mock_repository.delete.assert_not_called()

    def test_delete_manual_mode_success(self):
        identifier = "10.1234/example-doi"
        existing_doi = DOIDb(
            identifier=identifier,
            state=State.DRAFT.name,
            mode=Mode.MANUAL.name,
            doi={"data": {}},
            prefix="10.1234",
            suffix="example-doi",
            url="https://example.com/doi",
        )

        self.mock_repository.fetch.return_value = existing_doi

        self.service.delete(identifier=identifier)

        self.mock_gateway.delete.assert_not_called()
        self.mock_repository.delete.assert_called_once_with(doi=existing_doi)

    def test_delete_auto_mode_success(self):
        identifier = "10.1234/example-doi"
        existing_doi = DOIDb(
            identifier=identifier,
            state=State.DRAFT.name,
            mode=Mode.AUTO.name,
            prefix="10.1234",
            suffix="example-doi",
            doi={"data": {}},
            url="https://example.com/doi",
        )

        self.mock_repository.fetch.return_value = existing_doi

        self.service.delete(identifier=identifier)

        self.mock_gateway.delete.assert_called_once_with(
            repository=existing_doi.prefix, identifier=existing_doi.suffix
        )
        self.mock_repository.delete.assert_called_once_with(doi=existing_doi)


if __name__ == "__main__":
    unittest.main()
