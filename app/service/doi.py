from app.exception.illegal_state import IllegalStateException
from app.gateway.doi.doi import DOIGateway
from app.gateway.doi.resource import DOIPayload, Data as DOIPayloadData, Attributes as DOIPayloadAttributes, Types as DOIPayloadTypes, Creator as DOIPayloadCreator, Title as DOIPayloadTitle
from app.model.dataset import Dataset, DatasetVersion
from app.model.doi import DOI, Event, Mode, Title, Publisher, Creator, State, Identifier
from app.repository.doi import DOIRepository


class DOIService:
    def __init__(self, doi_gateway: DOIGateway):
        self._doi_gateway = doi_gateway
    
    def _adapt_model_to_payload(self, doi: DOI) -> DOIPayload:
        return DOIPayload(
            data=DOIPayloadData(
                attributes=DOIPayloadAttributes(
                    prefix=self._doi_repository,
                    creators=[DOIPayloadCreator(name=creator.name) for creator in doi.creators],
                    titles=[DOIPayloadTitle(title=doi.title.title)],
                    publisher=doi.publisher.publisher,
                    publicationYear=doi.publication_year,
                    url=doi.url,
                    types=DOIPayloadTypes(resourceTypeGeneral=doi.resource_type),
                )
            )
        )
    
    def _validate_manual_doi(self, doi: DOI) -> None:
        if not doi.identifier:
            raise IllegalStateException("doi_identifier_empty")
        
    def _validate_auto_doi(self, doi: DOI, event: Event) -> None:
        if doi.identifier:
            raise IllegalStateException("doi_identifier_not_empty")

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
            raise IllegalStateException("doi_missing_fields", missing_fields=missing_fields)
        
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
            res = self._doi_gateway.post(self._adapt_model_to_payload(doi))
            doi.identifier = Identifier(identifier=res["data"]["id"])
            doi.provider_response = res

        db_res = self._doi_repository.upsert(self._adapt_to_db(doi))
        doi.id = db_res.id

        return doi
    
    def update(self, doi: DOI, identifier: str) -> dict:
        return self._doi_gateway.update(doi, identifier)
    
    def delete(self, identifier: str) -> dict:
        existing_doi = self.get(identifier)

        if existing_doi.get("data", {}).get("state") != "draft":
            raise IllegalStateException("doi_not_draft")

        return self._doi_gateway.delete(identifier)
