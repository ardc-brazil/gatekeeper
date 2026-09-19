import logging
from time import perf_counter

from sqlalchemy import text

from app.database import Database
from app.gateway.object_storage.object_storage import ObjectStorageGateway
from app.logging_config import Redactor, fields


class DependencyHealthService:
    """Reports whether the things the API depends on are answering.

    Separate from the liveness endpoint on purpose: the deploy waits on that one.
    """

    def __init__(
        self,
        database: Database,
        object_storage: ObjectStorageGateway,
        bucket: str,
    ) -> None:
        self._logger = logging.getLogger("service:health")
        self._database = database
        self._object_storage = object_storage
        self._bucket = bucket

    def check(self) -> dict:
        checks = {
            "database": self._timed(self._check_database),
            "object_storage": self._timed(self._check_object_storage),
        }
        degraded = [name for name, check in checks.items() if check["status"] != "up"]
        if degraded:
            self._logger.warning(
                "dependency check degraded", extra=fields(degraded=degraded)
            )
        return {
            "status": "degraded" if degraded else "healthy",
            "checks": checks,
        }

    def _timed(self, check) -> dict:
        started = perf_counter()
        try:
            result = check()
        except Exception as e:
            # A connection error carries the DSN, and the DSN carries the password.
            result = {"status": "down", "error": Redactor.scrub_text(str(e))}
        result["latency_ms"] = round((perf_counter() - started) * 1000, 1)
        return result

    def _check_database(self) -> dict:
        with self._database.session() as session:
            session.execute(text("SELECT 1"))
        return {"status": "up"}

    def _check_object_storage(self) -> dict:
        if not self._object_storage.bucket_exists(self._bucket):
            return {"status": "bucket_missing", "bucket": self._bucket}
        return {"status": "up"}
