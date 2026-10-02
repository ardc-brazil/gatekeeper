import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from app.model.dataset_access import AccessEventType
from app.repository.access_event import AccessEventRepository
from app.service.dataset_access_audit import DatasetAccessAudit


class TestDatasetAccessAudit(unittest.TestCase):
    def test_an_event_is_appended_and_counted(self):
        events = Mock(spec=AccessEventRepository)
        audit = DatasetAccessAudit(event_repository=events)
        dataset_id, user_id = uuid4(), uuid4()

        with patch("app.service.dataset_access_audit.metrics") as metrics:
            audit.record(
                dataset_id=dataset_id,
                event_type=AccessEventType.EXTENDED,
                changed_by=user_id,
                old_value={"until": "a"},
                new_value={"until": "b"},
                note="review round 2",
            )

        events.append.assert_called_once_with(
            dataset_id=dataset_id,
            event_type="extended",
            changed_by=user_id,
            old_value={"until": "a"},
            new_value={"until": "b"},
            note="review round 2",
        )
        metrics.dataset_access_event.assert_called_once_with("extended")
