import uuid
from datetime import datetime, timezone

import pytest

from tests.integration.fixtures.account import disable, newest_text
from tests.integration.fixtures.embargo import grant
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.fixtures.tenancy import (
    ADMIN_ID,
    LEGACY,
    PUBLIC,
    admin,
    as_user,
    create_dataset,
    display_name,
    events,
    join,
    new_account,
    new_tenancy,
    set_roles,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit

SOMEONE = str(uuid.uuid4())


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _refused(response, status: int, detail: str) -> None:
    assert_status_code(response, status)
    assert response.json() == {"detail": detail}, response.json()


def _members_path(tenancy: str) -> str:
    return f"/admin/tenancies/{tenancy}/members"


def _add(http_client, tenancy: str, user_id: str):
    return http_client.post(
        _members_path(tenancy), json={"user_id": user_id}, headers=admin()
    )


def _remove(http_client, tenancy: str, user_id: str):
    return http_client.delete(f"{_members_path(tenancy)}/{user_id}", headers=admin())


def _create(http_client, display: str, namespace: str):
    return http_client.post(
        "/admin/tenancies",
        json={"display_name": display, "namespace": namespace},
        headers=admin(),
    )


def _search(http_client, q: str):
    return http_client.get("/admin/users", params={"q": q}, headers=admin())


def _epoch(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _is_member(user_id: str, tenancy: str) -> bool:
    return (
        execute(
            "SELECT count(*) FROM users_tenancies "
            f"WHERE user_id = '{user_id}' AND tenancy = '{tenancy}'"
        )
        == "1"
    )


class TestOnlyAdmins:
    ROUTES = (
        ("get", "/admin/tenancy-requests/counts", None),
        ("get", "/admin/tenancy-requests", None),
        ("get", f"/admin/tenancy-requests/{SOMEONE}", None),
        ("post", f"/admin/tenancy-requests/{SOMEONE}/approve", {"tenancy": PUBLIC}),
        ("post", f"/admin/tenancy-requests/{SOMEONE}/decline", {}),
        ("get", "/admin/tenancies", None),
        ("post", "/admin/tenancies", {"display_name": "X", "namespace": "x-1"}),
        ("get", f"/admin/tenancies/{PUBLIC}/members", None),
        ("get", f"/admin/tenancies/{PUBLIC}/members/{SOMEONE}", None),
        ("post", f"/admin/tenancies/{PUBLIC}/members", {"user_id": SOMEONE}),
        ("delete", f"/admin/tenancies/{PUBLIC}/members/{SOMEONE}", None),
        ("delete", f"/admin/tenancy-invitations/{SOMEONE}", None),
        ("get", "/admin/users?q=ana", None),
    )

    def test_a_users_write_account_gets_401_on_every_admin_route(self, http_client):
        account = new_account(http_client)
        set_roles(http_client, account["id"], add=("users_write",))
        headers = as_user(account["id"])

        for method, path, body in self.ROUTES:
            response = getattr(http_client, method)(path, json=body, headers=headers)
            assert (
                response.status_code == 401
            ), f"{method.upper()} {path}: {response.status_code}"

    def test_the_retired_membership_routes_are_gone_even_for_an_admin(
        self, http_client
    ):
        account = new_account(http_client)
        body = {"tenancies": ["datamap/production/data-amazon"]}

        added = http_client.post(
            f"/users/{account['id']}/tenancies", json=body, headers=admin()
        )
        removed = http_client.delete(
            f"/users/{account['id']}/tenancies", json=body, headers=admin()
        )

        assert added.status_code in (404, 405)
        assert removed.status_code in (404, 405)
        assert tenancies_of(http_client, account["id"]) == [PUBLIC]

    def test_tenancies_routes_lock_public(self, http_client):
        renamed = http_client.put(
            f"/tenancies/{PUBLIC}",
            json={"name": "x", "is_enabled": False},
            headers=admin(),
        )
        disabled = http_client.delete(f"/tenancies/{PUBLIC}", headers=admin())

        _refused(renamed, 409, "public_tenancy_locked")
        _refused(disabled, 409, "public_tenancy_locked")


class TestTheList:
    def test_public_first_legacy_last_with_counts(self, http_client):
        created = new_tenancy(display_name=unique("Listed"))
        response = http_client.get("/admin/tenancies", headers=admin())

        assert_status_code(response, 200)
        rows = response.json()
        paths = [row["path"] for row in rows]
        assert paths[0] == PUBLIC
        assert rows[0]["is_default"] is True
        assert rows[0]["members"] >= 1
        legacy_start = min(i for i, row in enumerate(rows) if row["is_legacy"])
        assert all(row["is_legacy"] for row in rows[legacy_start:])
        assert LEGACY in paths[legacy_start:]
        assert created in paths[1:legacy_start]
        (row,) = [r for r in rows if r["path"] == created]
        assert row == {
            "path": created,
            "display_name": display_name(created),
            "members": 0,
            "datasets": 0,
            "is_default": False,
            "is_legacy": False,
            "is_enabled": True,
        }


class TestCreating:
    def test_a_tenancy_is_created_once_with_its_event(self, http_client):
        namespace, display = unique("atto"), unique("ATTO")

        created = _create(http_client, display, namespace)

        assert_status_code(created, 201)
        path = f"datamap/production/{namespace}"
        assert created.json()["path"] == path
        assert created.json()["is_enabled"] is True
        (event,) = events(f"tenancy = '{path}'")
        assert (event["event_type"], event["actor_id"]) == ("tenancy_created", ADMIN_ID)
        _refused(
            _create(http_client, unique("Other"), namespace), 409, "tenancy_exists"
        )
        _refused(
            _create(http_client, display.lower(), unique("other")),
            409,
            "display_name_taken",
        )
        _refused(_create(http_client, "Fine", "Bad NS"), 400, "namespace_invalid")
        _refused(_create(http_client, "Fine", "public"), 400, "namespace_invalid")
        _refused(
            _create(http_client, "   ", unique("fine")), 400, "display_name_invalid"
        )


class TestMembers:
    def test_adding_a_member_emails_them_and_lists_them(self, http_client, mailpit):
        tenancy = new_tenancy(display_name=unique("Members"))
        account = new_account(http_client)

        added = _add(http_client, tenancy, account["id"])

        assert_status_code(added, 201)
        assert added.json()["id"] == account["id"]
        assert added.json()["invited_by"] is None
        assert tenancy in tenancies_of(http_client, account["id"])
        text = newest_text(http_client, mailpit, account["email"])
        assert f"gave you access to {display_name(tenancy)} on DataMap." in text
        (event,) = events(f"tenancy = '{tenancy}' AND user_id = '{account['id']}'")
        assert (event["event_type"], event["actor_id"]) == ("member_added", ADMIN_ID)
        listed = http_client.get(_members_path(tenancy), headers=admin()).json()
        assert listed["members"]["total_count"] == 1
        assert listed["members"]["items"][0]["id"] == account["id"]
        assert listed["invitations"] == []

    def test_adding_refusals(self, http_client):
        tenancy = new_tenancy()
        account = new_account(http_client)
        assert_status_code(_add(http_client, tenancy, account["id"]), 201)

        _refused(_add(http_client, tenancy, account["id"]), 409, "already_member")
        _refused(_add(http_client, PUBLIC, account["id"]), 409, "public_tenancy_locked")
        _refused(
            _add(http_client, LEGACY, account["id"]), 409, "legacy_tenancy_read_only"
        )
        _refused(
            _add(http_client, new_tenancy(enabled=False), account["id"]),
            409,
            "tenancy_disabled",
        )
        _refused(
            _add(http_client, f"datamap/production/{unique('none')}", account["id"]),
            404,
            "tenancy_not_found",
        )
        _refused(_add(http_client, tenancy, SOMEONE), 404, "no_account")

    def test_paging_members(self, http_client):
        tenancy = new_tenancy()
        for _ in range(3):
            join(new_account(http_client)["id"], tenancy)

        page = http_client.get(
            _members_path(tenancy), params={"limit": 2, "offset": 2}, headers=admin()
        ).json()["members"]

        assert (
            page["total_count"],
            len(page["items"]),
            page["limit"],
            page["offset"],
        ) == (3, 1, 2, 2)

    def test_a_member_with_no_added_event_is_a_member_since_their_account(
        self, http_client
    ):
        tenancy = new_tenancy()
        account = new_account(http_client)
        execute(
            "UPDATE users SET created_at = created_at - interval '3 days' "
            f"WHERE id = '{account['id']}'"
        )
        join(account["id"], tenancy)

        listed = http_client.get(_members_path(tenancy), headers=admin())

        assert_status_code(listed, 200)
        (member,) = listed.json()["members"]["items"]
        created = float(
            execute(
                "SELECT extract(epoch FROM created_at) FROM users "
                f"WHERE id = '{account['id']}'"
            )
        )
        assert abs(_epoch(member["since"]) - created) < 0.001, member["since"]

    @pytest.mark.parametrize("tenancy", [PUBLIC, LEGACY])
    def test_public_and_legacy_list_no_invitations(self, http_client, tenancy):
        account = new_account(http_client)
        execute(
            "INSERT INTO tenancy_invitations (tenancy, user_id, status) "
            f"VALUES ('{tenancy}', '{account['id']}', 'pending')"
        )

        listed = http_client.get(
            _members_path(tenancy), params={"limit": 1}, headers=admin()
        )

        assert_status_code(listed, 200)
        assert listed.json()["invitations"] == []


class TestRemoving:
    def test_impact_removal_and_what_the_member_keeps(self, http_client):
        tenancy = new_tenancy()
        owner, member = new_account(http_client), new_account(http_client)
        join(owner["id"], tenancy)
        assert_status_code(_add(http_client, tenancy, member["id"]), 201)
        theirs = create_dataset(http_client, member["id"], tenancy)
        shared = create_dataset(http_client, owner["id"], tenancy)
        grant(http_client, shared["id"], member["id"], "read")

        impact = http_client.get(
            f"{_members_path(tenancy)}/{member['id']}", headers=admin()
        )
        removed = _remove(http_client, tenancy, member["id"])
        next_call = http_client.get(
            f"/datasets/{shared['id']}", headers=as_user(member["id"], tenancy)
        )
        still_theirs = http_client.get(
            f"/datasets/{theirs['id']}", headers=as_user(member["id"])
        )

        assert_status_code(impact, 200)
        assert impact.json()["datasets_in_tenancy"] == 2
        assert impact.json()["shared_with_user"] == 1
        assert impact.json()["owned_by_user"] == 1
        assert impact.json()["member_since"]
        assert_status_code(removed, 204)
        assert_status_code(next_call, 401)
        assert next_call.json()["detail"].startswith("unauthorized_tenancy")
        assert_status_code(still_theirs, 200)
        assert tenancy not in tenancies_of(http_client, member["id"])
        (event,) = events(f"tenancy = '{tenancy}' AND event_type = 'member_removed'")
        assert (event["user_id"], event["actor_id"]) == (member["id"], ADMIN_ID)
        _refused(_remove(http_client, tenancy, member["id"]), 404, "member_not_found")
        _refused(
            http_client.get(
                f"{_members_path(tenancy)}/{member['id']}", headers=admin()
            ),
            404,
            "member_not_found",
        )

    def test_public_and_legacy_are_locked_and_unknown_is_not_found(self, http_client):
        account = new_account(http_client)

        _refused(
            _remove(http_client, PUBLIC, account["id"]), 409, "public_tenancy_locked"
        )
        _refused(
            _remove(http_client, LEGACY, ADMIN_ID), 409, "legacy_tenancy_read_only"
        )
        _refused(
            _remove(http_client, f"datamap/production/{unique('none')}", account["id"]),
            404,
            "tenancy_not_found",
        )
        assert _is_member(account["id"], PUBLIC)

    def test_a_member_of_a_disabled_tenancy_can_be_removed(self, http_client):
        tenancy = new_tenancy(enabled=False)
        account = new_account(http_client)
        join(account["id"], tenancy)

        removed = _remove(http_client, tenancy, account["id"])

        assert_status_code(removed, 204)
        assert not _is_member(account["id"], tenancy)

    def test_removing_someone_who_joined_by_invitation_revokes_it(self, http_client):
        tenancy = new_tenancy()
        owner = new_account(http_client, name=unique("Owner"))
        invitee = new_account(http_client)
        join(owner["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        invitation = http_client.post(
            f"/datasets/{dataset['id']}/tenancy-invitations",
            json={"user_id": invitee["id"]},
            headers=as_user(owner["id"], tenancy),
        ).json()
        pending = http_client.get(_members_path(tenancy), headers=admin()).json()[
            "invitations"
        ]
        assert_status_code(
            http_client.post(
                f"/users/{invitee['id']}/tenancy-invitations/{invitation['id']}/accept",
                headers=as_user(invitee["id"]),
            ),
            200,
        )
        listed = http_client.get(_members_path(tenancy), headers=admin()).json()

        removed = _remove(http_client, tenancy, invitee["id"])

        assert [i["id"] for i in pending] == [invitation["id"]]
        (joined,) = [m for m in listed["members"]["items"] if m["id"] == invitee["id"]]
        assert joined["invited_by"]["name"] == owner["name"]
        assert_status_code(removed, 204)
        assert (
            execute(
                f"SELECT status FROM tenancy_invitations WHERE id = '{invitation['id']}'"
            )
            == "revoked"
        )


class TestUserSearch:
    def test_by_name_email_and_orcid_enabled_only(self, http_client):
        orcid = random_orcid()
        found = new_account(
            http_client,
            name=unique("Searchable"),
            providers=[{"name": "orcid", "reference": orcid}],
        )
        gone = new_account(http_client, name=unique("Searchable"))
        disable(http_client, gone["id"])

        by_name = _search(http_client, found["name"])
        by_email = _search(http_client, found["email"])
        by_orcid = _search(http_client, orcid)
        not_disabled = _search(http_client, gone["name"])

        expected = [{"id": found["id"], "name": found["name"], "email": found["email"]}]
        assert by_name.json() == expected
        assert by_email.json() == expected
        assert by_orcid.json() == expected
        assert not_disabled.json() == []
        _refused(_search(http_client, " a "), 400, "invalid_request")

    def test_percent_and_underscore_are_matched_literally(self, http_client):
        tag = unique("Literal")
        underscored = new_account(http_client, name=f"{tag}_x")
        new_account(http_client, name=f"{tag}yx")

        by_underscore = _search(http_client, f"{tag}_x")
        by_percent = _search(http_client, f"{tag}%x")

        assert_status_code(by_underscore, 200)
        assert [hit["id"] for hit in by_underscore.json()] == [underscored["id"]]
        assert by_percent.json() == []
