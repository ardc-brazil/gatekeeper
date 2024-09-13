from app.exception.illegal_state import IllegalStateException
from app.gateway.doi.doi import DOIGateway


class DOIService:
    def __init__(self, doi_gateway: DOIGateway):
        self._doi_gateway = doi_gateway
    
    def get(self, doi: str) -> dict:
        return self._doi_gateway.get(doi)
    
    def create(self, doi: dict) -> dict:
        return self._doi_gateway.post(doi)
    
    def update(self, doi: dict, identifier: str) -> dict:
        return self._doi_gateway.update(doi, identifier)
    
    def delete(self, identifier: str) -> dict:
        existing_doi = self.get(identifier)

        if existing_doi.get("data", {}).get("state") != "draft":
            raise IllegalStateException("doi_not_draft")

        return self._doi_gateway.delete(identifier)
