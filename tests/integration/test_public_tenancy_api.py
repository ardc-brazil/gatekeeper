import pytest

from tests.integration.fixtures.account import (
    confirm_email_verification,
    newest_code,
    outbox,
    password_account,
    request_email_verification,
    unique_email,
)
from tests.integration.fixtures.embargo import grant
from tests.integration.fixtures.sharing import random_orcid
from tests.integration.fixtures.tenancy import (
    ADMIN_ID,
    PUBLIC,
    as_user,
    create_dataset,
    events,
    join,
    members_access,
    new_account,
    new_tenancy,
    roles_of,
    set_roles,
    tenancies_of,
    unique,
    update_dataset,
    upload,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


@pytest.fixture(scope="module")
def mailpit():
    return Mailpit()


def _lands_in_public_with_datasets_write(http_client, user_id: str) -> None:
    assert PUBLIC in tenancies_of(http_client, user_id)
    assert roles_of(user_id) == ["datasets_write"]
    assert (
        outbox(http_client, related_id=user_id, template="new_account_pending")["items"]
        == []
    )
    (added,) = events(f"user_id = '{user_id}' AND tenancy = '{PUBLIC}'")
    assert added["event_type"] == "member_added"
    assert added["actor_id"] == ""


class TestEveryCreationPath:
    def test_post_users(self, http_client):
        account = new_account(http_client)

        _lands_in_public_with_datasets_write(http_client, account["id"])

    def test_password_sign_up(self, http_client, mailpit):
        account = password_account(http_client, mailpit)

        _lands_in_public_with_datasets_write(http_client, account["id"])

    def test_orcid_email_verification(self, http_client, mailpit):
        orcid, email = random_orcid(), unique_email()
        started = request_email_verification(http_client, orcid, email)
        assert_status_code(started, 202)
        code = newest_code(http_client, mailpit, email)
        confirmed = confirm_email_verification(
            http_client, started.json()["challenge_id"], code
        )
        assert_status_code(confirmed, 200)

        _lands_in_public_with_datasets_write(http_client, confirmed.json()["user_id"])


class TestANewAccountWorksAtOnce:
    def test_it_creates_a_dataset_in_public_uploads_and_edits(self, http_client):
        account = new_account(http_client)

        dataset = create_dataset(http_client, account["id"], PUBLIC)
        uploaded = upload(http_client, account["id"], dataset)
        edited = update_dataset(http_client, account["id"], dataset)
        detail = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(account["id"], PUBLIC)
        )

        assert_status_code(uploaded, 200)
        assert uploaded.json().get("RejectUpload") is not True
        assert_status_code(edited, 200)
        assert detail.json()["name"] == "edited"
        assert len(detail.json()["current_version"]["files_in"]) == 1
        assert detail.json()["access"]["level"] == "owner"


class TestNewDatasetsAreClosed:
    @pytest.mark.parametrize("in_public", [True, False])
    def test_members_can_edit_is_false_when_the_request_omits_it(
        self, http_client, in_public
    ):
        owner = new_account(http_client)
        tenancy = PUBLIC if in_public else new_tenancy()
        join(owner["id"], tenancy)

        dataset = create_dataset(http_client, owner["id"], tenancy)
        detail = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(owner["id"], tenancy)
        )

        assert detail.json()["members_can_edit"] is False
        assert (
            execute(
                f"SELECT members_can_edit FROM datasets WHERE id = '{dataset['id']}'"
            )
            == "f"
        )


@pytest.fixture
def published(http_client):
    owner = new_account(http_client, name="Public Owner")
    dataset = create_dataset(http_client, owner["id"], PUBLIC)
    assert_status_code(upload(http_client, owner["id"], dataset), 200)
    return owner, dataset


class TestPublicIsReadOnlyForMembers:
    def test_another_member_reads_metadata_and_files_but_cannot_change_them(
        self, http_client, published
    ):
        _, dataset = published
        reader = new_account(http_client, name="Public Reader")
        headers = as_user(reader["id"], PUBLIC)

        detail = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        version = detail.json()["current_version"]
        download = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version['name']}/files/{version['files_in'][0]['id']}",
            headers=headers,
        )
        update = update_dataset(http_client, reader["id"], dataset)
        delete = http_client.delete(f"/datasets/{dataset['id']}", headers=headers)

        assert_status_code(detail, 200)
        assert detail.json()["access"]["level"] == "tenancy"
        assert detail.json()["access"]["can_edit"] is False
        assert detail.json()["members_can_edit"] is False
        assert_status_code(download, 200)
        assert_status_code(update, 403)
        assert update.json() == {"detail": "forbidden"}
        assert_status_code(delete, 401)

    def test_a_member_whose_role_deletes_is_refused_by_the_access_rule(
        self, http_client, published
    ):
        _, dataset = published
        deleter = new_account(http_client, name="Public Deleter")
        set_roles(http_client, deleter["id"], add=("datasets_admin",))

        delete = http_client.delete(
            f"/datasets/{dataset['id']}", headers=as_user(deleter["id"], PUBLIC)
        )

        assert_status_code(delete, 403)

    def test_the_owner_and_a_write_collaborator_edit(self, http_client, published):
        owner, dataset = published
        collaborator = new_account(http_client, name="Public Collaborator")
        grant(http_client, dataset["id"], collaborator["id"], "write")

        assert_status_code(update_dataset(http_client, owner["id"], dataset), 200)
        assert_status_code(
            update_dataset(http_client, collaborator["id"], dataset), 200
        )

    def test_opening_a_public_dataset_to_members_is_refused(
        self, http_client, published
    ):
        owner, dataset = published

        opened = members_access(http_client, owner["id"], dataset, True)
        closed = members_access(http_client, owner["id"], dataset, False)

        assert_status_code(opened, 400)
        assert opened.json() == {"detail": "public_members_cannot_edit"}
        assert_status_code(closed, 200)
        assert closed.json()["members_can_edit"] is False

    def test_a_public_dataset_whose_column_says_true_is_still_closed(
        self, http_client, published
    ):
        _, dataset = published
        execute(
            f"UPDATE datasets SET members_can_edit = true WHERE id = '{dataset['id']}'"
        )
        reader = new_account(http_client, name="Public Reader")

        update = update_dataset(http_client, reader["id"], dataset)
        detail = http_client.get(
            f"/datasets/{dataset['id']}", headers=as_user(reader["id"], PUBLIC)
        )

        assert_status_code(update, 403)
        assert detail.json()["members_can_edit"] is False

    def test_an_admin_moving_a_dataset_into_public_closes_it(self, http_client):
        tenancy = new_tenancy()
        join(ADMIN_ID, tenancy)
        dataset = create_dataset(http_client, ADMIN_ID, tenancy)
        assert_status_code(members_access(http_client, ADMIN_ID, dataset, True), 200)

        moved = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "moved", "data": {}, "tenancy": PUBLIC},
            headers=as_user(ADMIN_ID, tenancy),
        )

        assert_status_code(moved, 200)
        assert (
            execute(
                f"SELECT members_can_edit, tenancy FROM datasets WHERE id = '{dataset['id']}'"
            )
            == f"f|{PUBLIC}"
        )


class TestOutsidePublic:
    def test_a_member_edits_only_after_the_owner_opens_the_dataset(self, http_client):
        tenancy = new_tenancy()
        owner, member = new_account(http_client), new_account(http_client)
        join(owner["id"], tenancy)
        join(member["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)

        before = update_dataset(http_client, member["id"], dataset)
        opened = members_access(http_client, owner["id"], dataset, True)
        after = update_dataset(http_client, member["id"], dataset)

        assert_status_code(before, 403)
        assert_status_code(opened, 200)
        assert_status_code(after, 200)

    def test_no_one_but_an_admin_moves_a_dataset_out_of_the_tenancy(self, http_client):
        tenancy, elsewhere = new_tenancy(), new_tenancy()
        owner, editor, holder = (new_account(http_client) for _ in range(3))
        for account in (owner, editor, holder):
            join(account["id"], tenancy)
            join(account["id"], elsewhere)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        assert_status_code(members_access(http_client, owner["id"], dataset, True), 200)
        grant(http_client, dataset["id"], holder["id"], "write")

        for account in (owner, editor, holder):
            for target in (elsewhere, PUBLIC):
                moved = http_client.put(
                    f"/datasets/{dataset['id']}",
                    json={"name": "moved", "data": {}, "tenancy": target},
                    headers=as_user(account["id"], tenancy),
                )

                assert_status_code(moved, 400)
                assert moved.json() == {"detail": "tenancy_cannot_change"}
                assert (
                    execute(
                        f"SELECT name, tenancy FROM datasets WHERE id = '{dataset['id']}'"
                    )
                    == f"{dataset['name']}|{tenancy}"
                )

        for account in (owner, editor, holder):
            assert_status_code(update_dataset(http_client, account["id"], dataset), 200)
        assert (
            execute(f"SELECT name, tenancy FROM datasets WHERE id = '{dataset['id']}'")
            == f"edited|{tenancy}"
        )

    def test_an_admin_editing_as_a_member_moves_a_colleagues_dataset(self, http_client):
        tenancy, elsewhere = new_tenancy(), new_tenancy()
        owner = new_account(http_client)
        join(owner["id"], tenancy)
        join(ADMIN_ID, tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)
        assert_status_code(members_access(http_client, owner["id"], dataset, True), 200)

        moved = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "moved", "data": {}, "tenancy": elsewhere},
            headers=as_user(ADMIN_ID, tenancy),
        )

        assert_status_code(moved, 200)
        assert (
            execute(f"SELECT name, tenancy FROM datasets WHERE id = '{dataset['id']}'")
            == f"moved|{elsewhere}"
        )


class TestShareCandidates:
    def test_candidates_are_empty_for_a_dataset_in_public(self, http_client):
        owner = new_account(http_client)
        dataset = create_dataset(http_client, owner["id"], PUBLIC)
        name = unique("Zelda")
        new_account(http_client, name=name)

        response = http_client.get(
            f"/datasets/{dataset['id']}/share/candidates",
            params={"q": name},
            headers=as_user(owner["id"], PUBLIC),
        )

        assert_status_code(response, 200)
        assert response.json() == []

    def test_candidates_still_come_from_another_tenancy(self, http_client):
        tenancy = new_tenancy()
        owner = new_account(http_client)
        member = new_account(http_client, name=unique("Zelda"))
        join(owner["id"], tenancy)
        join(member["id"], tenancy)
        dataset = create_dataset(http_client, owner["id"], tenancy)

        response = http_client.get(
            f"/datasets/{dataset['id']}/share/candidates",
            params={"q": member["name"]},
            headers=as_user(owner["id"], tenancy),
        )

        assert [user["id"] for user in response.json()] == [member["id"]]


class TestSelfRoutes:
    @pytest.mark.parametrize("route", ["tenancies", "tenancy-requests"])
    def test_another_users_id_is_refused(self, http_client, route):
        caller, other = new_account(http_client), new_account(http_client)

        response = http_client.get(
            f"/users/{other['id']}/{route}", headers=as_user(caller["id"])
        )

        assert_status_code(response, 401)
        assert response.json() == {"detail": "not_authorized"}
