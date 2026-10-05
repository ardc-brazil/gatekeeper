import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.controller.v1.tenancy.access_resource import (
    AdminTenancyRequestDetailResponse,
    TenancyMembersResponse,
)
from app.model.tenancy import summary_of
from app.model.tenancy_access import (
    AdminTenancyRequestDetailView,
    Page,
    Requester,
    TenancyMembersView,
    TenancyMemberView,
    UserRef,
)

AT = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)


class TestFromViews(unittest.TestCase):
    def test_a_detail_view_with_nested_views_becomes_json(self):
        view = AdminTenancyRequestDetailView(
            id=uuid4(),
            requester=Requester(uuid4(), "Bruna", None, False, "0000-0002-1825-0097"),
            requested_name="ATTO",
            reason="r",
            status="pending",
            kind="join",
            suggested_tenancy=summary_of("datamap/production/atto", "ATTO"),
            created_at=AT,
            tenancy=None,
            created_tenancy=False,
            decision_message=None,
            decided_by=None,
            decided_at=None,
            requester_tenancies=[summary_of("datamap/production/public", "Public")],
            suggested_tenancy_members=4,
        )

        body = AdminTenancyRequestDetailResponse.model_validate(view).model_dump(
            mode="json"
        )

        self.assertEqual(body["suggested_tenancy"]["display_name"], "ATTO")
        self.assertEqual(body["requester"]["email"], None)
        self.assertEqual(body["requester_tenancies"][0]["is_default"], True)
        self.assertEqual(body["suggested_tenancy_members"], 4)
        self.assertEqual(body["created_at"], "2026-10-05T09:30:00Z")

    def test_a_page_of_members(self):
        view = TenancyMembersView(
            members=Page(
                items=[
                    TenancyMemberView(
                        uuid4(), "Ana", "a@usp.br", AT, UserRef(uuid4(), "Alan")
                    )
                ],
                total_count=1,
                limit=50,
                offset=0,
            ),
            invitations=[],
        )

        body = TenancyMembersResponse.model_validate(view).model_dump(mode="json")

        self.assertEqual(body["members"]["total_count"], 1)
        self.assertEqual(body["members"]["items"][0]["invited_by"]["name"], "Alan")
        self.assertEqual(body["invitations"], [])
