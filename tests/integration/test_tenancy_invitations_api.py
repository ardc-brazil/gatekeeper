from types import SimpleNamespace

import pytest

from tests.integration.fixtures.account import (
    ADMIN_ADDRESS,
    newest_text,
    outbox,
    refused,
)
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
    invite,
    join,
    new_account,
    new_tenancy,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit

NOBODY = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


@pytest.fixture
def world(http_client):
    tenancy = new_tenancy(display_name=unique("Invites"))
    member = new_account(http_client, name=unique("Member"))
    join(member["id"], tenancy)
    invitee = new_account(http_client, name=unique("Invitee"))
    return SimpleNamespace(tenancy=tenancy, member=member, invitee=invitee)


def _base(user_id: str, tenancy: str) -> str:
    return f"/users/{user_id}/tenancies/{tenancy}"


def _members(
    http_client, user_id: str, tenancy: str, caller: str | None = None, **params
):
    return http_client.get(
        f"{_base(user_id, tenancy)}/members",
        params=params,
        headers=as_user(caller or user_id),
    )


def _pending(http_client, user_id: str, tenancy: str, caller: str | None = None):
    return http_client.get(
        f"{_base(user_id, tenancy)}/invitations", headers=as_user(caller or user_id)
    )


def _lookup(
    http_client,
    user_id: str,
    tenancy: str,
    value: str | None,
    caller: str | None = None,
):
    params = {} if value is None else {"value": value}
    return http_client.get(
        f"{_base(user_id, tenancy)}/lookup",
        params=params,
        headers=as_user(caller or user_id),
    )


def _invite_as(http_client, user_id: str, tenancy: str, invitee_id: str, caller: str):
    return http_client.post(
        f"{_base(user_id, tenancy)}/invitations",
        json={"user_id": invitee_id},
        headers=as_user(caller),
    )


def _withdraw(
    http_client,
    user_id: str,
    tenancy: str,
    invitation_id: str,
    caller: str | None = None,
):
    return http_client.delete(
        f"{_base(user_id, tenancy)}/invitations/{invitation_id}",
        headers=as_user(caller or user_id),
    )


def _every_route(
    http_client, user_id: str, tenancy: str, invitee_id: str, caller: str | None = None
) -> list:
    caller = caller or user_id
    return [
        _members(http_client, user_id, tenancy, caller),
        _pending(http_client, user_id, tenancy, caller),
        _lookup(http_client, user_id, tenancy, "someone@example.com", caller),
        _invite_as(http_client, user_id, tenancy, invitee_id, caller),
        _withdraw(http_client, user_id, tenancy, NOBODY, caller),
    ]


def _invited(http_client, world) -> dict:
    response = invite(
        http_client, world.member["id"], world.tenancy, world.invitee["id"]
    )
    assert_status_code(response, 201)
    return response.json()


def _accept(
    http_client, user_id: str, invitation_id: str, caller_id: str | None = None
):
    return http_client.post(
        f"/users/{user_id}/tenancy-invitations/{invitation_id}/accept",
        headers=as_user(caller_id or user_id),
    )


def _status(invitation_id: str) -> str:
    return execute(
        f"SELECT status FROM tenancy_invitations WHERE id = '{invitation_id}'"
    )


def _status_of_any(tenancy: str) -> str:
    return execute(
        f"SELECT string_agg(status::text, ',') FROM tenancy_invitations "
        f"WHERE tenancy = '{tenancy}'"
    )


class TestInviting:
    def test_a_member_invites_and_the_invitee_and_admins_are_told(
        self, http_client, mailpit, world
    ):
        response = invite(
            http_client, world.member["id"], world.tenancy, world.invitee["id"]
        )

        assert_status_code(response, 201)
        body = response.json()
        assert body["user"] == {
            "id": world.invitee["id"],
            "name": world.invitee["name"],
        }
        assert body["invited_by"] == {
            "id": world.member["id"],
            "name": world.member["name"],
        }
        assert body["can_withdraw"] is True
        text = newest_text(http_client, mailpit, world.invitee["email"])
        assert f"invited you to join {display_name(world.tenancy)} on DataMap." in text
        assert "This email cannot accept for you." in text
        assert body["id"] not in text
        assert "token" not in text.lower()
        assert "from the dataset" not in text
        assert "Dataset:" not in text
        sent = outbox(
            http_client, template="tenancy_invitation", related_id=body["id"]
        )["items"]
        assert [s["recipient"] for s in sent] == [world.invitee["email"]]
        notices = outbox(
            http_client, template="tenancy_invitation_notice", related_id=body["id"]
        )["items"]
        assert [n["recipient"] for n in notices] == [ADMIN_ADDRESS]
        (created,) = events(f"invitation_id = '{body['id']}'")
        assert (created["event_type"], created["actor_id"]) == (
            "invitation_created",
            world.member["id"],
        )

    def test_a_member_with_no_dataset_in_the_tenancy_invites(self, http_client, world):
        datasets = execute(
            f"SELECT count(*) FROM datasets WHERE tenancy = '{world.tenancy}'"
        )

        response = invite(
            http_client, world.member["id"], world.tenancy, world.invitee["id"]
        )

        assert datasets == "0"
        assert_status_code(response, 201)

    def test_a_non_member_gets_tenancy_not_found_on_every_route(
        self, http_client, world
    ):
        outsider = new_account(http_client)

        responses = _every_route(
            http_client, outsider["id"], world.tenancy, world.invitee["id"]
        )
        nowhere = _members(http_client, outsider["id"], "datamap/production/nowhere")

        for response in responses + [nowhere]:
            refused(response, 404, "tenancy_not_found")
        assert _status_of_any(world.tenancy) == ""

    def test_public_is_locked_on_every_route(self, http_client, world):
        for response in _every_route(
            http_client, world.member["id"], PUBLIC, world.invitee["id"]
        ):
            refused(response, 409, "public_tenancy_locked")

    def test_legacy_is_read_only(self, http_client, world):
        join(world.member["id"], LEGACY)

        response = invite(http_client, world.member["id"], LEGACY, world.invitee["id"])

        refused(response, 409, "legacy_tenancy_read_only")

    def test_a_disabled_tenancy_cannot_be_invited_to(self, http_client, world):
        execute(
            f"UPDATE tenancies SET is_enabled = false WHERE name = '{world.tenancy}'"
        )

        response = invite(
            http_client, world.member["id"], world.tenancy, world.invitee["id"]
        )

        refused(response, 409, "tenancy_disabled")
        assert _status_of_any(world.tenancy) == ""

    def test_members_unknown_accounts_and_a_second_invitation(self, http_client, world):
        other = new_account(http_client)
        join(other["id"], world.tenancy)
        _invited(http_client, world)

        refused(
            invite(http_client, world.member["id"], world.tenancy, other["id"]),
            409,
            "already_member",
        )
        refused(
            invite(http_client, world.member["id"], world.tenancy, world.invitee["id"]),
            409,
            "invitation_pending",
        )
        refused(
            invite(http_client, world.member["id"], world.tenancy, NOBODY),
            404,
            "no_account",
        )
        assert _status_of_any(world.tenancy) == "pending"

    def test_an_unparseable_body_is_invalid_request(self, http_client, world):
        response = http_client.post(
            f"{_base(world.member['id'], world.tenancy)}/invitations",
            json={"user_id": "nope"},
            headers=as_user(world.member["id"]),
        )

        refused(response, 400, "invalid_request")

    def test_another_users_id_is_refused_on_every_route(self, http_client, world):
        caller = new_account(http_client)
        join(caller["id"], world.tenancy)

        responses = _every_route(
            http_client,
            world.member["id"],
            world.tenancy,
            world.invitee["id"],
            caller=caller["id"],
        )

        for response in responses:
            assert_status_code(response, 401)
        assert _status_of_any(world.tenancy) == ""

    def test_an_admin_who_is_not_a_member_is_let_through(self, http_client, world):
        response = invite(http_client, ADMIN_ID, world.tenancy, world.invitee["id"])

        assert_status_code(response, 201)
        assert_status_code(_members(http_client, ADMIN_ID, world.tenancy), 200)


class TestTheMembersPage:
    def test_members_are_named_with_their_orcid_and_never_an_email(
        self, http_client, world
    ):
        orcid = random_orcid()
        holder = new_account(
            http_client,
            name=unique("Holder"),
            providers=[{"name": "orcid", "reference": orcid}],
        )
        join(holder["id"], world.tenancy)

        response = _members(http_client, world.member["id"], world.tenancy)

        assert_status_code(response, 200)
        body = response.json()
        assert (body["total_count"], body["limit"], body["offset"]) == (2, 50, 0)
        assert sorted(body["items"], key=lambda m: m["name"]) == sorted(
            [
                {"id": world.member["id"], "name": world.member["name"], "orcid": None},
                {"id": holder["id"], "name": holder["name"], "orcid": orcid},
            ],
            key=lambda m: m["name"],
        )
        assert "@" not in response.text

    def test_members_are_paged(self, http_client, world):
        join(new_account(http_client)["id"], world.tenancy)

        first = _members(
            http_client, world.member["id"], world.tenancy, limit=1, offset=0
        )
        beyond = _members(
            http_client, world.member["id"], world.tenancy, limit=101, offset=0
        )

        assert_status_code(first, 200)
        assert (len(first.json()["items"]), first.json()["total_count"]) == (1, 2)
        refused(beyond, 400, "invalid_request")

    def test_pending_invitations_say_who_and_whether_the_caller_may_withdraw(
        self, http_client, world
    ):
        invitation = _invited(http_client, world)
        other = new_account(http_client)
        join(other["id"], world.tenancy)

        as_inviter = _pending(http_client, world.member["id"], world.tenancy)
        as_other = _pending(http_client, other["id"], world.tenancy)

        assert_status_code(as_inviter, 200)
        assert as_inviter.json() == [
            {
                "id": invitation["id"],
                "user": {"id": world.invitee["id"], "name": world.invitee["name"]},
                "invited_by": {"id": world.member["id"], "name": world.member["name"]},
                "created_at": invitation["created_at"],
                "can_withdraw": True,
            }
        ]
        assert [i["can_withdraw"] for i in as_other.json()] == [False]
        assert "@" not in as_inviter.text


class TestLookup:
    def test_by_exact_email_orcid_unknown_and_malformed(self, http_client, world):
        orcid = random_orcid()
        holder = new_account(
            http_client, providers=[{"name": "orcid", "reference": orcid}]
        )
        caller, tenancy = world.member["id"], world.tenancy
        email = world.invitee["email"]

        by_email = _lookup(http_client, caller, tenancy, email.upper())
        by_orcid = _lookup(http_client, caller, tenancy, orcid)
        prefix = _lookup(http_client, caller, tenancy, email[:-1])
        unknown = _lookup(http_client, caller, tenancy, "ghost@example.com")
        malformed = _lookup(http_client, caller, tenancy, "not an address")
        missing = _lookup(http_client, caller, tenancy, None)

        assert_status_code(by_email, 200)
        assert by_email.json() == {
            "user": {
                "id": world.invitee["id"],
                "name": world.invitee["name"],
                "email": email,
            },
            "tenancy_member": False,
            "invitation_pending": False,
            "can_invite": True,
        }
        assert_status_code(by_orcid, 200)
        assert by_orcid.json()["user"] == {
            "id": holder["id"],
            "name": "Bruna Costa",
            "email": None,
        }
        refused(prefix, 404, "no_account")
        refused(unknown, 404, "no_account")
        refused(malformed, 400, "invalid_request")
        refused(missing, 400, "invalid_request")

    def test_says_when_someone_is_a_member_or_already_invited(self, http_client, world):
        caller, tenancy = world.member["id"], world.tenancy
        _invited(http_client, world)

        invited = _lookup(http_client, caller, tenancy, world.invitee["email"])
        member = _lookup(http_client, caller, tenancy, world.member["email"])

        assert (
            invited.json()["invitation_pending"],
            invited.json()["can_invite"],
        ) == (True, False)
        assert (member.json()["tenancy_member"], member.json()["can_invite"]) == (
            True,
            False,
        )


class TestTheInvitee:
    def test_sees_accepts_and_joins_once(self, http_client, world):
        invitation = _invited(http_client, world)

        listed = http_client.get(
            f"/users/{world.invitee['id']}/tenancy-invitations",
            headers=as_user(world.invitee["id"]),
        )
        accepted = _accept(http_client, world.invitee["id"], invitation["id"])
        again = _accept(http_client, world.invitee["id"], invitation["id"])

        (pending,) = listed.json()
        assert pending["tenancy"]["path"] == world.tenancy
        assert pending["invited_by"]["id"] == world.member["id"]
        assert "dataset" not in pending
        assert pending["datasets"] == 0
        assert_status_code(accepted, 200)
        assert accepted.json()["tenancy"]["path"] == world.tenancy
        assert world.tenancy in tenancies_of(http_client, world.invitee["id"])
        assert _status(invitation["id"]) == "accepted"
        assert event_types(f"invitation_id = '{invitation['id']}'") == [
            "invitation_accepted",
            "invitation_created",
            "member_added",
        ]
        memberships = execute(
            "SELECT count(*) FROM users_tenancies "
            f"WHERE user_id = '{world.invitee['id']}' AND tenancy = '{world.tenancy}'"
        )
        assert memberships == "1"
        refused(again, 404, "invitation_not_found")

    def test_a_dataset_of_the_tenancy_opens_once_joined(self, http_client, world):
        dataset = create_dataset(http_client, world.member["id"], world.tenancy)
        invitation = _invited(http_client, world)

        accepted = _accept(http_client, world.invitee["id"], invitation["id"])
        read = http_client.get(
            f"/datasets/{dataset['id']}",
            headers=as_user(world.invitee["id"], world.tenancy),
        )

        assert_status_code(accepted, 200)
        assert_status_code(read, 200)

    def test_accepting_when_already_a_member_adds_no_second_member(
        self, http_client, world
    ):
        invitation = _invited(http_client, world)
        join(world.invitee["id"], world.tenancy)

        accepted = _accept(http_client, world.invitee["id"], invitation["id"])

        assert_status_code(accepted, 200)
        assert _status(invitation["id"]) == "accepted"
        assert event_types(
            f"user_id = '{world.invitee['id']}' AND tenancy = '{world.tenancy}'"
        ) == ["invitation_accepted", "invitation_created"]

    def test_cannot_accept_into_a_tenancy_disabled_since(self, http_client, world):
        invitation = _invited(http_client, world)
        execute(
            f"UPDATE tenancies SET is_enabled = false WHERE name = '{world.tenancy}'"
        )

        refused(
            _accept(http_client, world.invitee["id"], invitation["id"]),
            409,
            "tenancy_disabled",
        )
        assert _status(invitation["id"]) == "pending"

    def test_only_the_invitee_accepts(self, http_client, world):
        invitation = _invited(http_client, world)
        other = new_account(http_client)

        someone_else = _accept(
            http_client, world.invitee["id"], invitation["id"], caller_id=other["id"]
        )
        on_their_own_id = _accept(http_client, other["id"], invitation["id"])

        assert_status_code(someone_else, 401)
        refused(on_their_own_id, 404, "invitation_not_found")
        assert _status(invitation["id"]) == "pending"

    def test_declines(self, http_client, world):
        invitation = _invited(http_client, world)

        declined = http_client.post(
            f"/users/{world.invitee['id']}/tenancy-invitations/{invitation['id']}/decline",
            headers=as_user(world.invitee["id"]),
        )

        assert_status_code(declined, 204)
        assert _status(invitation["id"]) == "declined"
        assert world.tenancy not in tenancies_of(http_client, world.invitee["id"])
        refused(
            _accept(http_client, world.invitee["id"], invitation["id"]),
            404,
            "invitation_not_found",
        )


class TestWithdrawing:
    def test_only_the_inviter_withdraws(self, http_client, world):
        other = new_account(http_client)
        join(other["id"], world.tenancy)
        invitation = _invited(http_client, world)

        not_theirs = _withdraw(
            http_client, other["id"], world.tenancy, invitation["id"]
        )
        withdrawn = _withdraw(
            http_client, world.member["id"], world.tenancy, invitation["id"]
        )
        again = _withdraw(
            http_client, world.member["id"], world.tenancy, invitation["id"]
        )

        refused(not_theirs, 403, "forbidden")
        assert_status_code(withdrawn, 204)
        refused(again, 404, "invitation_not_found")
        assert _status(invitation["id"]) == "withdrawn"
        (event,) = events(
            f"invitation_id = '{invitation['id']}' "
            "AND event_type = 'invitation_withdrawn'"
        )
        assert event["actor_id"] == world.member["id"]

    def test_an_invitation_of_another_tenancy_is_not_found(self, http_client, world):
        invitation = _invited(http_client, world)
        elsewhere = new_tenancy()
        join(world.member["id"], elsewhere)

        response = _withdraw(
            http_client, world.member["id"], elsewhere, invitation["id"]
        )

        refused(response, 404, "invitation_not_found")
        assert _status(invitation["id"]) == "pending"

    def test_an_admin_withdraws_through_the_admin_route(self, http_client, world):
        invitation = _invited(http_client, world)

        withdrawn = http_client.delete(
            f"/admin/tenancy-invitations/{invitation['id']}", headers=admin()
        )
        again = http_client.delete(
            f"/admin/tenancy-invitations/{invitation['id']}", headers=admin()
        )

        assert_status_code(withdrawn, 204)
        refused(again, 404, "invitation_not_found")
        assert _status(invitation["id"]) == "withdrawn"
        (event,) = events(
            f"invitation_id = '{invitation['id']}' "
            "AND event_type = 'invitation_withdrawn'"
        )
        assert event["actor_id"] == ADMIN_ID


class TestTheShareDialog:
    def test_the_share_state_is_dataset_sharing_only(self, http_client, world):
        dataset = create_dataset(http_client, world.member["id"], world.tenancy)
        _invited(http_client, world)

        state = http_client.get(
            f"/datasets/{dataset['id']}/share",
            headers=as_user(world.member["id"], world.tenancy),
        )

        assert_status_code(state, 200)
        body = state.json()
        assert "tenancy_invitations" not in body
        assert "can_invite_to_tenancy" not in body
        assert body["tenancy"]["name"] == display_name(world.tenancy)

    def test_the_dataset_routes_for_tenancy_invitations_are_gone(
        self, http_client, world
    ):
        dataset = create_dataset(http_client, world.member["id"], world.tenancy)
        headers = as_user(world.member["id"], world.tenancy)

        invited = http_client.post(
            f"/datasets/{dataset['id']}/tenancy-invitations",
            json={"user_id": world.invitee["id"]},
            headers=headers,
        )
        looked_up = http_client.get(
            f"/datasets/{dataset['id']}/share/lookup",
            params={"value": world.invitee["email"]},
            headers=headers,
        )

        for response in (invited, looked_up):
            assert response.status_code in (404, 405), response.status_code
        assert _status_of_any(world.tenancy) == ""
