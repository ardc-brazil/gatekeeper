from types import SimpleNamespace

import pytest

from tests.integration.fixtures.account import (
    ADMIN_ADDRESS,
    newest_text,
    outbox,
    refused,
)
from tests.integration.fixtures.embargo import grant, set_embargo
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
    members_access,
    new_account,
    new_tenancy,
    permit,
    roles_of,
    tenancies_of,
    unique,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


@pytest.fixture
def world(http_client):
    tenancy = new_tenancy(display_name=unique("Invites"))
    owner = new_account(http_client, name=unique("Owner"))
    join(owner["id"], tenancy)
    dataset = create_dataset(http_client, owner["id"], tenancy)
    invitee = new_account(http_client, name=unique("Invitee"))
    return SimpleNamespace(
        tenancy=tenancy, owner=owner, dataset=dataset, invitee=invitee
    )


def _invite(http_client, inviter_id: str, dataset: dict, invitee_id: str):
    return http_client.post(
        f"/datasets/{dataset['id']}/tenancy-invitations",
        json={"user_id": invitee_id},
        headers=as_user(inviter_id, dataset["tenancy"]),
    )


def _invited(http_client, world) -> dict:
    response = _invite(
        http_client, world.owner["id"], world.dataset, world.invitee["id"]
    )
    assert_status_code(response, 201)
    return response.json()


def _withdraw(http_client, user_id: str, dataset: dict, invitation_id: str):
    return http_client.delete(
        f"/datasets/{dataset['id']}/tenancy-invitations/{invitation_id}",
        headers=as_user(user_id, dataset["tenancy"]),
    )


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


def _editor(http_client, world, name: str) -> dict:
    editor = new_account(http_client, name=unique(name))
    join(editor["id"], world.tenancy)
    grant(http_client, world.dataset["id"], editor["id"], "write")
    return editor


class TestWhoMayInvite:
    def test_the_owner_invites_and_the_invitee_and_admins_are_told(
        self, http_client, mailpit, world
    ):
        response = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        )

        assert_status_code(response, 201)
        body = response.json()
        assert body["user"]["id"] == world.invitee["id"]
        assert body["invited_by"]["id"] == world.owner["id"]
        assert body["can_withdraw"] is True
        text = newest_text(http_client, mailpit, world.invitee["email"])
        assert f"invited you to join {display_name(world.tenancy)} on DataMap" in text
        assert "This email cannot accept for you." in text
        assert body["id"] not in text
        assert "token" not in text.lower()
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
            world.owner["id"],
        )

    def test_a_write_collaborator_who_is_a_member_invites(self, http_client, world):
        editor = _editor(http_client, world, "Editor")

        response = _invite(
            http_client, editor["id"], world.dataset, world.invitee["id"]
        )

        assert_status_code(response, 201)

    def test_a_reader_a_members_can_edit_member_and_an_outside_collaborator_may_not(
        self, http_client, world
    ):
        reader = new_account(http_client)
        join(reader["id"], world.tenancy)
        grant(http_client, world.dataset["id"], reader["id"], "read")
        member = new_account(http_client)
        join(member["id"], world.tenancy)
        assert_status_code(
            members_access(http_client, world.owner["id"], world.dataset, True), 200
        )
        outsider = new_account(http_client)
        grant(http_client, world.dataset["id"], outsider["id"], "write")

        for inviter in (reader, member, outsider):
            refused(
                _invite(http_client, inviter["id"], world.dataset, world.invitee["id"]),
                403,
                "forbidden",
            )
        assert _status_of_any(world.tenancy) == ""

    def test_a_global_admin_without_access_to_the_dataset_is_not_let_through(
        self, http_client, world
    ):
        response = _invite(http_client, ADMIN_ID, world.dataset, world.invitee["id"])

        assert_status_code(response, 404)
        assert _status_of_any(world.tenancy) == ""

    def test_public_and_staging_cannot_be_invited_to(self, http_client):
        owner, invitee = new_account(http_client), new_account(http_client)
        join(owner["id"], LEGACY)
        in_public = create_dataset(http_client, owner["id"], PUBLIC)
        in_staging = create_dataset(http_client, owner["id"], LEGACY)

        refused(
            _invite(http_client, owner["id"], in_public, invitee["id"]),
            409,
            "public_tenancy_locked",
        )
        refused(
            _invite(http_client, owner["id"], in_staging, invitee["id"]),
            409,
            "legacy_tenancy_read_only",
        )

    def test_a_disabled_tenancy_cannot_be_invited_to(self, http_client, world):
        execute(
            f"UPDATE tenancies SET is_enabled = false WHERE name = '{world.tenancy}'"
        )

        response = _invite(
            http_client, world.owner["id"], world.dataset, world.invitee["id"]
        )

        refused(response, 409, "tenancy_disabled")

    def test_members_unknown_accounts_and_a_second_invitation(self, http_client, world):
        member = new_account(http_client)
        join(member["id"], world.tenancy)
        _invited(http_client, world)

        refused(
            _invite(http_client, world.owner["id"], world.dataset, member["id"]),
            409,
            "already_member",
        )
        refused(
            _invite(http_client, world.owner["id"], world.dataset, world.invitee["id"]),
            409,
            "invitation_pending",
        )
        refused(
            _invite(
                http_client,
                world.owner["id"],
                world.dataset,
                "00000000-0000-0000-0000-000000000000",
            ),
            404,
            "no_account",
        )
        assert _status_of_any(world.tenancy) == "pending"


class TestTheInvitee:
    def test_sees_accepts_and_joins(self, http_client, world):
        invitation = _invited(http_client, world)
        mine = as_user(world.invitee["id"])

        listed = http_client.get(
            f"/users/{world.invitee['id']}/tenancy-invitations", headers=mine
        )
        accepted = _accept(http_client, world.invitee["id"], invitation["id"])

        (pending,) = listed.json()
        assert pending["tenancy"]["path"] == world.tenancy
        assert pending["invited_by"]["id"] == world.owner["id"]
        assert pending["dataset"] == {
            "id": world.dataset["id"],
            "name": world.dataset["name"],
        }
        assert pending["datasets"] == 1
        assert_status_code(accepted, 200)
        assert accepted.json()["tenancy"]["path"] == world.tenancy
        assert world.tenancy in tenancies_of(http_client, world.invitee["id"])
        assert _status(invitation["id"]) == "accepted"
        assert event_types(f"invitation_id = '{invitation['id']}'") == [
            "invitation_accepted",
            "invitation_created",
            "member_added",
        ]
        read = http_client.get(
            f"/datasets/{world.dataset['id']}",
            headers=as_user(world.invitee["id"], world.tenancy),
        )
        assert_status_code(read, 200)
        refused(
            _accept(http_client, world.invitee["id"], invitation["id"]),
            404,
            "invitation_not_found",
        )

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
    def test_the_inviter_withdraws_and_another_editor_may_not(self, http_client, world):
        inviter = _editor(http_client, world, "Inviter")
        other_editor = _editor(http_client, world, "Other editor")
        invitation = _invite(
            http_client, inviter["id"], world.dataset, world.invitee["id"]
        ).json()

        refused_response = _withdraw(
            http_client, other_editor["id"], world.dataset, invitation["id"]
        )
        withdrawn = _withdraw(
            http_client, inviter["id"], world.dataset, invitation["id"]
        )

        refused(refused_response, 403, "forbidden")
        assert_status_code(withdrawn, 204)
        assert _status(invitation["id"]) == "withdrawn"
        refused(
            _withdraw(http_client, inviter["id"], world.dataset, invitation["id"]),
            404,
            "invitation_not_found",
        )

    def test_an_owner_with_only_datasets_write_withdraws_and_a_non_inviter_may_not(
        self, http_client, world
    ):
        editor = new_account(http_client)
        join(editor["id"], world.tenancy)
        permit(world.dataset["id"], editor["id"], "write")
        invitation = _invited(http_client, world)
        assert "datasets_shared" not in roles_of(world.owner["id"])
        assert "datasets_shared" not in roles_of(editor["id"])
        assert "datasets_write" in roles_of(editor["id"])

        not_theirs = _withdraw(
            http_client, editor["id"], world.dataset, invitation["id"]
        )
        withdrawn = _withdraw(
            http_client, world.owner["id"], world.dataset, invitation["id"]
        )

        refused(not_theirs, 403, "forbidden")
        assert_status_code(withdrawn, 204)
        assert _status(invitation["id"]) == "withdrawn"
        (event,) = events(
            f"invitation_id = '{invitation['id']}' "
            "AND event_type = 'invitation_withdrawn'"
        )
        assert event["actor_id"] == world.owner["id"]

    def test_an_admin_withdraws(self, http_client, world):
        invitation = _invited(http_client, world)

        withdrawn = http_client.delete(
            f"/admin/tenancy-invitations/{invitation['id']}", headers=admin()
        )

        assert_status_code(withdrawn, 204)
        assert _status(invitation["id"]) == "withdrawn"
        (event,) = events(
            f"invitation_id = '{invitation['id']}' "
            "AND event_type = 'invitation_withdrawn'"
        )
        assert event["actor_id"] == ADMIN_ID
        refused(
            http_client.delete(
                f"/admin/tenancy-invitations/{invitation['id']}", headers=admin()
            ),
            404,
            "invitation_not_found",
        )


class TestTheShareDialog:
    def test_the_share_state_carries_pending_invitations_and_whether_one_may_invite(
        self, http_client, world
    ):
        invitation = _invited(http_client, world)

        state = http_client.get(
            f"/datasets/{world.dataset['id']}/share",
            headers=as_user(world.owner["id"], world.tenancy),
        )

        assert_status_code(state, 200)
        body = state.json()
        assert body["can_invite_to_tenancy"] is True
        assert [i["id"] for i in body["tenancy_invitations"]] == [invitation["id"]]
        assert body["tenancy"]["name"] == display_name(world.tenancy)
        assert (body["tenancy"]["is_default"], body["tenancy"]["is_legacy"]) == (
            False,
            False,
        )
        assert body["tenancy"]["datasets"] == 1

    def test_an_embargoed_dataset_offers_no_tenancy_invitation(
        self, http_client, world
    ):
        headers = as_user(world.owner["id"], world.tenancy)
        assert_status_code(
            set_embargo(http_client, world.dataset["id"], headers, visible=False), 200
        )

        state = http_client.get(
            f"/datasets/{world.dataset['id']}/share", headers=headers
        )

        assert_status_code(state, 200)
        body = state.json()
        assert (body["tenancy"], body["can_invite_to_tenancy"]) == (None, False)

    def test_the_lookup_says_when_someone_was_already_invited(self, http_client, world):
        path = f"/datasets/{world.dataset['id']}/share/lookup"
        headers = as_user(world.owner["id"], world.tenancy)

        before = http_client.get(
            path, params={"value": world.invitee["email"]}, headers=headers
        )
        _invited(http_client, world)
        after = http_client.get(
            path, params={"value": world.invitee["email"]}, headers=headers
        )

        assert (before.json()["can_invite"], before.json()["invitation_pending"]) == (
            True,
            False,
        )
        assert (after.json()["can_invite"], after.json()["invitation_pending"]) == (
            False,
            True,
        )
