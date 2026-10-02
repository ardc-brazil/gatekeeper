import unittest

from app.model.dataset_access import AccessEventType, AccessLevel, PermissionLevel


class TestAccessModel(unittest.TestCase):
    def test_levels_serialise_to_the_contract_values(self):
        self.assertEqual(
            [level.value for level in AccessLevel],
            ["owner", "write", "read", "tenancy"],
        )
        self.assertEqual([level.value for level in PermissionLevel], ["read", "write"])

    def test_event_types_fit_the_column(self):
        for event in AccessEventType:
            self.assertLessEqual(len(event.value), 32)

    def test_the_access_model_does_not_depend_on_the_embargo(self):
        import app.model.dataset_access as module

        with open(module.__file__) as source:
            self.assertNotIn("app.model.embargo", source.read())

    def test_the_members_access_event_and_action_have_their_contract_values(self):
        from app.model.dataset_access import DatasetAction

        self.assertEqual(
            AccessEventType.MEMBERS_ACCESS_CHANGED.value, "members_access_changed"
        )
        self.assertEqual(
            DatasetAction.MANAGE_MEMBERS_ACCESS.value, "manage_members_access"
        )
