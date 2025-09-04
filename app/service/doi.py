from app.adapter.doi import model_to_payload, model_to_database, change_state_to_payload
from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.illegal_state import IllegalStateException
from app.exception.not_found import NotFoundException
from app.gateway.doi.doi import DOIGateway
from app.model.doi import DOI, Mode, State, Event
from app.repository.doi import DOIRepository
from app.model.db.doi import DOI as DOIDBModel


class DOIService:
    def __init__(
        self, doi_gateway: DOIGateway, doi_repository: DOIRepository, doi_prefix: str
    ):
        self._doi_gateway = doi_gateway
        self._doi_repository = doi_repository
        self._doi_prefix = doi_prefix

    def _validate_manual_doi(self, doi: DOI) -> None:
        if not doi.identifier:
            raise BadRequestException(
                errors=[ErrorDetails(code="empty", field="identifier")]
            )

    def _validate_auto_doi(self, doi: DOI) -> None:
        if doi.identifier:
            raise BadRequestException(
                errors=[ErrorDetails(code="not_empty", field="identifier")]
            )

        fields = {
            "title": doi.title,
            "creators": doi.creators,
            "publisher": doi.publisher,
            "publication_year": doi.publication_year,
            "resource_type": doi.resource_type,
            "url": doi.url,
        }

        missing_fields = [name for name, value in fields.items() if not value]

        if missing_fields:
            raise BadRequestException(
                errors=[
                    ErrorDetails(code="missing_field", field=field)
                    for field in missing_fields
                ]
            )

    def _validate_doi(self, doi: DOI) -> None:
        if doi.mode == Mode.MANUAL:
            self._validate_manual_doi(doi)
        else:
            self._validate_auto_doi(doi)

    def get(self, doi: str) -> DOI:
        return self._doi_gateway.get(doi)

    def get_from_database(self, identifier: str) -> DOIDBModel:
        return self._doi_repository.fetch(identifier=identifier)

    def create(self, doi: DOI) -> DOI:
        self._validate_doi(doi)

        if doi.mode == Mode.AUTO:
            res = self._doi_gateway.post(
                model_to_payload(repository=self._doi_prefix, doi=doi)
            )
            doi.identifier = res["data"]["attributes"]["doi"]
            doi.provider_response = res

        db_res = self._doi_repository.upsert(model_to_database(doi))
        doi.id = db_res.id

        return doi

    def _get_valid_event_from_state(self, doi: DOIDBModel, new_state: State) -> Event:
        if doi.state == State.DRAFT.name and new_state == State.FINDABLE:
            return Event.PUBLISH
        elif doi.state == State.DRAFT.name and new_state == State.REGISTERED:
            return Event.REGISTER
        elif doi.state == State.REGISTERED.name and new_state == State.FINDABLE:
            return Event.PUBLISH
        elif doi.state == State.FINDABLE.name and new_state == State.REGISTERED:
            return Event.HIDE
        else:
            raise IllegalStateException("invalid_state_transition")

    def change_state(self, identifier: str, new_state: State):
        from_database: DOIDBModel = self.get_from_database(identifier)

        if from_database.mode == Mode.MANUAL.name:
            raise IllegalStateException("manual_doi_cannot_change_state")

        if from_database.mode == Mode.AUTO.name:
            event: Event = self._get_valid_event_from_state(from_database, new_state)
            res = self._doi_gateway.update(
                change_state_to_payload(doi=from_database, event=event), identifier
            )
            from_database.doi = res
            from_database.state = new_state.name

        self._doi_repository.upsert(doi=from_database)

    def delete(self, identifier: str) -> None:
        existing_doi: DOIDBModel = self.get_from_database(identifier)

        if not existing_doi:
            raise NotFoundException(f"not_found: {identifier}")

        if existing_doi.state != State.DRAFT.name:
            raise IllegalStateException("doi_not_in_draft_state")

        if existing_doi.mode == Mode.AUTO.name:
            self._doi_gateway.delete(
                repository=identifier.split("/")[0], identifier=identifier.split("/")[1]
            )

        self._doi_repository.delete(doi=existing_doi)

    def update_metadata(self, doi: DOI) -> None:
        if doi is not None and doi.mode == Mode.AUTO:
            from_database: DOIDBModel = self.get_from_database(doi.identifier)

            if from_database is None:
                raise NotFoundException(f"not_found: {doi.identifier}")

            if from_database.mode == Mode.MANUAL.name:
                raise IllegalStateException("manual_doi_cannot_update_metadata")

            res = self._doi_gateway.update(
                doi=model_to_payload(repository=from_database.prefix, doi=doi),
                identifier=doi.identifier,
            )
            from_database.doi = res

            self._doi_repository.upsert(doi=from_database)
