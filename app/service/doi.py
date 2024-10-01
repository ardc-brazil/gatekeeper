from app.adapter.doi import model_to_payload
from app.exception.bad_request import BadRequestException, ErrorDetails
from app.exception.illegal_state import IllegalStateException
from app.gateway.doi.doi import DOIGateway
from app.model.doi import DOI, Event, Mode, Identifier


class DOIService:
    def __init__(self, doi_gateway: DOIGateway):
        self._doi_gateway = doi_gateway
    
    def _validate_manual_doi(self, doi: DOI) -> None:
        if not doi.identifier:
            raise BadRequestException(errors=[ErrorDetails(code="doi_identifier_empty")])
        
    def _validate_auto_doi(self, doi: DOI, event: Event) -> None:
        if doi.identifier:
            raise BadRequestException(errors=[ErrorDetails(code="doi_identifier_not_empty")])

        fields = {
            "title": doi.title,
            "creators": doi.creators,
            "publisher": doi.publisher,
            "publication_year": doi.publication_year,
            "resource_type": doi.resource_type,
            "url": doi.url,
            "event": event
        }

        missing_fields = [name for name, value in fields.items() if not value]

        if missing_fields:
            raise BadRequestException(errors=[ErrorDetails(code="missing_field", field=field) for field in missing_fields])
        
    def _validate_doi(self, doi: DOI) -> None:
        if doi.mode == Mode.MANUAL:
            self._validate_manual_doi(doi)
        else:
            self._validate_auto_doi(doi)
    
    def get(self, doi: str) -> DOI:
        return self._doi_gateway.get(doi)
    
    def create(self, doi: DOI) -> DOI:
        self._validate_doi(doi)
        
        if doi.mode == Mode.Auto:
            res = self._doi_gateway.post(model_to_payload(doi))
            doi.identifier = Identifier(identifier=res["data"]["id"])
            doi.provider_response = res

        db_res = self._doi_repository.upsert(self._adapt_to_db(doi))
        doi.id = db_res.id

        return doi
    
    def update(self, doi: DOI, identifier: str) -> dict:
        return self._doi_gateway.update(model_to_payload(doi), identifier)
    
    def delete(self, identifier: str) -> dict:
        existing_doi = self.get(identifier)

        if existing_doi.get("data", {}).get("state") != "draft":
            raise IllegalStateException("doi_not_draft")

        return self._doi_gateway.delete(identifier)
