import pytest

from tests.integration.fixtures.account import ADMIN_ADDRESS, newest_text, outbox
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.fixtures.tenancy import (
    ADMIN_ID,
    LEGACY,
    PUBLIC,
    admin,
    as_user,
    create_dataset,
    display_name,
    event_types,
    events,
    join,
    new_account,
    new_tenancy,
    request_access,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _refused(response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def _withdraw(http_client, user_id: str, request_id: str):
    return http_client.delete(
        f"/users/{user_id}/tenancy-requests/{request_id}", headers=as_user(user_id)
    )


def _approve(http_client, request_id: str, body: dict):
    return http_client.post(
        f"/admin/tenancy-requests/{request_id}/approve", json=body, headers=admin()
    )


def _decline(http_client, request_id: str, body: dict | None = None):
    return http_client.post(
        f"/admin/tenancy-requests/{request_id}/decline", json=body, headers=admin()
    )


def _queue(http_client, **params) -> dict:
    response = http_client.get(
        "/admin/tenancy-requests", params=params, headers=admin()
    )
    assert_status_code(response, 200)
    return response.json()


def _counts(http_client) -> dict:
    response = http_client.get("/admin/tenancy-requests/counts", headers=admin())
    assert_status_code(response, 200)
    return response.json()


class TestAsking:
    def test_a_request_is_stored_trimmed_and_every_admin_is_told(self, http_client):
        account = new_account(http_client)

        response = request_access(http_client, account["id"], name="  ATTO  ")

        assert_status_code(response, 201)
        body = response.json()
        assert (body["status"], body["requested_name"], body["tenancy"]) == (
            "pending",
            "ATTO",
            None,
        )
        items = outbox(
            http_client, template="tenancy_request_received", related_id=body["id"]
        )["items"]
        assert [item["recipient"] for item in items] == [ADMIN_ADDRESS]
        assert items[0]["subject"] == "Tenancy request from Bruna Costa"
        assert events(f"request_id = '{body['id']}'") == [
            {
                "event_type": "request_created",
                "tenancy": "",
                "user_id": account["id"],
                "actor_id": account["id"],
                "request_id": body["id"],
                "invitation_id": "",
            }
        ]

    def test_one_pending_request_and_three_a_day_withdrawn_included(self, http_client):
        account = new_account(http_client)
        first = request_access(http_client, account["id"])
        assert_status_code(first, 201)
        _refused(request_access(http_client, account["id"]), 409, "request_pending")

        current = first.json()["id"]
        for _ in range(2):
            assert_status_code(_withdraw(http_client, account["id"], current), 204)
            again = request_access(http_client, account["id"])
            assert_status_code(again, 201)
            current = again.json()["id"]
        assert_status_code(_withdraw(http_client, account["id"], current), 204)

        _refused(request_access(http_client, account["id"]), 429, "too_many_requests")

    def test_what_is_asked_is_checked(self, http_client):
        account = new_account(http_client)

        _refused(
            request_access(http_client, account["id"], name="   "),
            400,
            "tenancy_name_invalid",
        )
        _refused(
            request_access(http_client, account["id"], reason="x" * 1001),
            400,
            "reason_invalid",
        )
        missing = http_client.post(
            f"/users/{account['id']}/tenancy-requests",
            json={"tenancy_name": "ATTO"},
            headers=as_user(account["id"]),
        )
        _refused(missing, 400, "invalid_request")

    def test_the_latest_requests_and_withdrawing(self, http_client):
        account = new_account(http_client)
        created = request_access(http_client, account["id"]).json()

        withdrawn = _withdraw(http_client, account["id"], created["id"])
        listed = http_client.get(
            f"/users/{account['id']}/tenancy-requests", headers=as_user(account["id"])
        )

        assert_status_code(withdrawn, 204)
        assert [(r["id"], r["status"]) for r in listed.json()] == [
            (created["id"], "withdrawn")
        ]
        _refused(
            _withdraw(http_client, account["id"], created["id"]),
            404,
            "request_not_found",
        )
        assert event_types(f"request_id = '{created['id']}'") == [
            "request_created",
            "request_withdrawn",
        ]
        _refused(
            http_client.get(
                f"/admin/tenancy-requests/{created['id']}", headers=admin()
            ),
            404,
            "request_not_found",
        )

    def test_the_routes_are_self_only_even_for_an_admin(self, http_client):
        account, other = new_account(http_client), new_account(http_client)

        as_other = http_client.get(
            f"/users/{account['id']}/tenancy-requests", headers=as_user(other["id"])
        )
        as_admin = http_client.post(
            f"/users/{account['id']}/tenancy-requests",
            json={"tenancy_name": "ATTO", "reason": "r"},
            headers=admin(),
        )
        tenancies = http_client.get(
            f"/users/{account['id']}/tenancies", headers=admin()
        )

        for response in (as_other, as_admin, tenancies):
            assert_status_code(response, 401)


class TestTheQueue:
    def test_counts_join_or_new_and_search_by_name_email_and_orcid(self, http_client):
        tenancy = new_tenancy(display_name=unique("Queue Join"))
        joiner = new_account(http_client, name=unique("Joiner"))
        orcid = random_orcid()
        newcomer = new_account(
            http_client,
            name=unique("Newcomer"),
            providers=[{"name": "orcid", "reference": orcid}],
        )
        before = _counts(http_client)

        assert_status_code(
            request_access(
                http_client, joiner["id"], name=display_name(tenancy).upper()
            ),
            201,
        )
        assert_status_code(
            request_access(http_client, newcomer["id"], name=unique("Brand new")), 201
        )
        after = _counts(http_client)

        assert after["open"] == before["open"] + 2
        assert after["join"] == before["join"] + 1
        assert after["new"] == before["new"] + 1
        assert after["open"] == after["join"] + after["new"]
        (joined,) = _queue(http_client, q=joiner["name"])["items"]
        assert joined["kind"] == "join"
        assert joined["suggested_tenancy"]["path"] == tenancy
        assert joined["requester"]["email_verified"] is False
        (by_email,) = _queue(http_client, q=newcomer["email"])["items"]
        assert (by_email["kind"], by_email["suggested_tenancy"]) == ("new", None)
        (by_orcid,) = _queue(http_client, q=orcid)["items"]
        assert by_orcid["requester"]["orcid"] == orcid
        assert len(_queue(http_client, kind="join", q=joiner["name"])["items"]) == 1
        assert _queue(http_client, kind="new", q=joiner["name"])["items"] == []

    def test_the_detail_lists_the_requesters_tenancies_and_the_suggestions_size(
        self, http_client
    ):
        tenancy = new_tenancy(display_name=unique("Detail"))
        member = new_account(http_client)
        join(member["id"], tenancy)
        account = new_account(http_client)
        request = request_access(
            http_client, account["id"], name=display_name(tenancy)
        ).json()

        detail = http_client.get(
            f"/admin/tenancy-requests/{request['id']}", headers=admin()
        )

        assert_status_code(detail, 200)
        assert [t["path"] for t in detail.json()["requester_tenancies"]] == [PUBLIC]
        assert detail.json()["suggested_tenancy_members"] == 1

    def test_bad_paging_is_invalid_request(self, http_client):
        for params in (
            {"limit": 0},
            {"limit": 101},
            {"status": "everything"},
            {"limit": "x"},
        ):
            response = http_client.get(
                "/admin/tenancy-requests", params=params, headers=admin()
            )
            _refused(response, 400, "invalid_request")


class TestApproving:
    def test_into_an_existing_tenancy(self, http_client, mailpit):
        tenancy = new_tenancy(display_name=unique("Approved"))
        owner = new_account(http_client)
        join(owner["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        account = new_account(http_client)
        request = request_access(
            http_client, account["id"], name=display_name(tenancy)
        ).json()

        approved = _approve(http_client, request["id"], {"tenancy": tenancy})

        assert_status_code(approved, 200)
        body = approved.json()
        assert (body["status"], body["created_tenancy"]) == ("approved", False)
        assert body["tenancy"]["path"] == tenancy
        assert body["decided_by"]["id"] == ADMIN_ID
        assert tenancy in tenancies_of(http_client, account["id"])
        readable = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(account["id"], tenancy)
        )
        assert_status_code(readable, 200)
        text = newest_text(http_client, mailpit, account["email"])
        assert f"gave you access to {display_name(tenancy)} on DataMap." in text
        assert event_types(f"request_id = '{request['id']}'") == [
            "member_added",
            "request_approved",
            "request_created",
        ]
        (added,) = events(
            f"request_id = '{request['id']}' AND event_type = 'member_added'"
        )
        assert (added["actor_id"], added["tenancy"]) == (ADMIN_ID, tenancy)
        mine = http_client.get(
            f"/users/{account['id']}/tenancy-requests", headers=as_user(account["id"])
        ).json()
        assert (mine[0]["status"], mine[0]["tenancy"]["path"]) == ("approved", tenancy)
        _refused(
            _approve(http_client, request["id"], {"tenancy": tenancy}),
            409,
            "request_not_pending",
        )
        _refused(_decline(http_client, request["id"]), 409, "request_not_pending")

    def test_into_a_new_tenancy(self, http_client):
        account = new_account(http_client, confirmed=True)
        request = request_access(http_client, account["id"], name="Cerrado Flux").json()
        namespace, name = unique("cerrado"), unique("Cerrado Flux")

        approved = _approve(
            http_client,
            request["id"],
            {"new_tenancy": {"display_name": name, "namespace": namespace}},
        )

        assert_status_code(approved, 200)
        path = f"datamap/production/{namespace}"
        assert approved.json()["created_tenancy"] is True
        assert approved.json()["tenancy"] == {
            "path": path,
            "display_name": name,
            "is_default": False,
            "is_legacy": False,
        }
        assert (
            execute(
                f"SELECT is_enabled, display_name FROM tenancies WHERE name = '{path}'"
            )
            == f"t|{name}"
        )
        assert path in tenancies_of(http_client, account["id"])
        assert event_types(f"request_id = '{request['id']}'") == [
            "member_added",
            "request_approved",
            "request_created",
            "tenancy_created",
        ]

    def test_every_refusal(self, http_client):
        existing = new_tenancy(display_name=unique("Taken"))
        member = new_account(http_client, confirmed=True)
        join(member["id"], existing)
        request = request_access(http_client, member["id"]).json()["id"]
        fresh = {"display_name": unique("Fresh"), "namespace": unique("fresh")}

        _refused(
            _approve(http_client, request, {"tenancy": existing}), 409, "already_member"
        )
        _refused(
            _approve(
                http_client,
                request,
                {"new_tenancy": {**fresh, "namespace": existing.rsplit("/", 1)[1]}},
            ),
            409,
            "tenancy_exists",
        )
        _refused(
            _approve(
                http_client,
                request,
                {
                    "new_tenancy": {
                        **fresh,
                        "display_name": display_name(existing).lower(),
                    }
                },
            ),
            409,
            "display_name_taken",
        )
        _refused(
            _approve(
                http_client,
                request,
                {"new_tenancy": {**fresh, "namespace": "Not Valid"}},
            ),
            400,
            "namespace_invalid",
        )
        _refused(
            _approve(
                http_client, request, {"new_tenancy": {**fresh, "namespace": "public"}}
            ),
            400,
            "namespace_invalid",
        )
        _refused(
            _approve(http_client, request, {"tenancy": PUBLIC}),
            409,
            "public_tenancy_locked",
        )
        _refused(
            _approve(http_client, request, {"tenancy": LEGACY}),
            409,
            "legacy_tenancy_read_only",
        )
        _refused(
            _approve(http_client, request, {"tenancy": new_tenancy(enabled=False)}),
            409,
            "tenancy_disabled",
        )
        _refused(
            _approve(
                http_client,
                request,
                {"tenancy": f"datamap/production/{unique('none')}"},
            ),
            404,
            "tenancy_not_found",
        )
        _refused(_approve(http_client, request, {}), 400, "invalid_request")
        _refused(
            _approve(http_client, request, {"tenancy": existing, "new_tenancy": fresh}),
            400,
            "invalid_request",
        )

        unverified = new_account(http_client)
        other = request_access(http_client, unverified["id"]).json()["id"]
        _refused(
            _approve(http_client, other, {"new_tenancy": fresh}),
            409,
            "requester_email_unverified",
        )
        assert event_types(f"request_id = '{request}'") == ["request_created"]


class TestDeclining:
    def test_with_a_message_and_only_once(self, http_client, mailpit):
        account = new_account(http_client)
        request = request_access(http_client, account["id"]).json()

        declined = _decline(
            http_client, request["id"], {"message": "  Ask Alan to invite you.  "}
        )

        assert_status_code(declined, 200)
        assert declined.json()["status"] == "declined"
        assert declined.json()["decision_message"] == "Ask Alan to invite you."
        text = newest_text(http_client, mailpit, account["email"])
        assert "An administrator could not give you access to ATTO." in text
        assert "Ask Alan to invite you." in text
        _refused(_decline(http_client, request["id"]), 409, "request_not_pending")
        (declined_event,) = events(
            f"request_id = '{request['id']}' AND event_type = 'request_declined'"
        )
        assert declined_event["actor_id"] == ADMIN_ID

    def test_a_long_message_is_refused(self, http_client):
        account = new_account(http_client)
        request = request_access(http_client, account["id"]).json()

        _refused(
            _decline(http_client, request["id"], {"message": "x" * 1001}),
            400,
            "message_invalid",
        )

    def test_closed_requests_show_the_decision(self, http_client):
        account = new_account(http_client, name=unique("Closed"))
        request = request_access(http_client, account["id"]).json()
        assert_status_code(_decline(http_client, request["id"]), 200)

        (row,) = _queue(http_client, status="closed", q=account["name"])["items"]

        assert row["status"] == "declined"
        assert row["decision_message"] is None
        assert row["decided_by"]["id"] == ADMIN_ID
        assert _queue(http_client, status="open", q=account["name"])["items"] == []

    def test_the_closed_list_pages_with_the_total(self, http_client):
        name = unique("Paged")
        declined = []
        for _ in range(3):
            account = new_account(http_client, name=name)
            request = request_access(http_client, account["id"]).json()
            assert_status_code(_decline(http_client, request["id"]), 200)
            declined.append(request["id"])

        first = _queue(http_client, status="closed", q=name, limit=2, offset=0)
        second = _queue(http_client, status="closed", q=name, limit=2, offset=2)

        assert (first["total_count"], second["total_count"]) == (3, 3)
        assert [r["id"] for r in first["items"]] == declined[:0:-1]
        assert [r["id"] for r in second["items"]] == declined[:1]
