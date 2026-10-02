import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import app.model.db.doi  # noqa: F401  # registers DOI before Dataset's mapper resolves its "DOI" relationship
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.dataset_access import AccessEventType
from app.repository.dataset import DatasetRepository
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.embargo_termination import EmbargoTermination

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class TestEmbargoTermination(unittest.TestCase):
    def test_ending_moves_the_date_to_now_and_records_it(self):
        repository = Mock(spec=DatasetRepository)
        audit = Mock(spec=DatasetAccessAudit)
        termination = EmbargoTermination(repository=repository, audit=audit)
        user_id = uuid4()
        dataset = DatasetDBModel(
            id=uuid4(),
            name="d",
            embargo_until=NOW + timedelta(days=3),
            embargo_metadata_visible=True,
        )

        termination.end(dataset=dataset, ended_by=user_id, now=NOW, note="manual DOI")

        self.assertEqual(dataset.embargo_until, NOW)
        repository.upsert.assert_called_once_with(dataset=dataset)
        audit.record.assert_called_once_with(
            dataset_id=dataset.id,
            event_type=AccessEventType.ENDED_EARLY,
            changed_by=user_id,
            old_value={
                "until": (NOW + timedelta(days=3)).isoformat(),
                "metadata_visible": True,
            },
            new_value={"until": NOW.isoformat(), "metadata_visible": True},
            note="manual DOI",
        )
