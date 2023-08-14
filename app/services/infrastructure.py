import logging
from app.services.other_service import OtherService

class InfrastructureService:
    def __init__(self, other_service: OtherService):
        self._other_service = other_service
        self._logger = logging.getLogger(__name__)

    def health_check(self):
        self._other_service.something()
        self._logger.error("Health check")
        return "success"