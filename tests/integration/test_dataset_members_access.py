import pytest

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import (
    TENANCY,
    create_dataset,
    create_user,
    grant,
    headers_for,
    set_embargo,
)
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code


@pytest.fixture
def owner():
    return AuthFixture.valid_headers()


@pytest.fixture
def editor(http_client):
    user_id = create_user(http_client, ["datasets_write"], [TENANCY])
    return user_id, headers_for(user_id, TENANCY)


@pytest.fixture
def deleter(http_client):
    user_id = create_user(http_client, ["datasets_admin"], [TENANCY])
    return user_id, headers_for(user_id, TENANCY)


@pytest.fixture
def outsider(http_client):
    user_id = create_user(http_client, [], [])
    return user_id, headers_for(user_id, None)


def _members(http_client, dataset_id: str, headers: dict, can_edit: bool):
    return http_client.put(
        f"/datasets/{dataset_id}/members-access",
        json={"members_can_edit": can_edit},
        headers=headers,
    )


def _update(http_client, dataset_id: str, headers: dict):
    return http_client.put(
        f"/datasets/{dataset_id}",
        json={"name": "edited", "data": {}, "tenancy": TENANCY},
        headers=headers,
    )


def _tus(http_client, dataset_id: str, user_id: str):
    payload = create_tus_payload(
        user_id=user_id,
        dataset_id=dataset_id,
        filename="data.nc",
        file_size=10,
        file_type="application/x-netcdf",
    )
    return http_client.post(
        "/tus/hooks", json=payload, headers=AuthFixture.valid_headers()
    )


def _owner_file(http_client, dataset: dict, owner: dict) -> tuple[str, str]:
    assert_status_code(_tus(http_client, dataset["id"], config.user_id), 200)
    body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
    version = body["current_version"]
    return version["name"], version["files_in"][0]["id"]


class TestByDefault:
    def test_a_new_dataset_lets_members_edit_as_today(self, http_client, owner, editor):
        dataset = create_dataset(http_client, owner)
        _, headers = editor

        as_member = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        update = _update(http_client, dataset["id"], headers)

        assert_status_code(as_member, 200)
        assert as_member.json()["members_can_edit"] is True
        assert as_member.json()["access"]["can_edit"] is True
        assert_status_code(update, 200)


class TestReadOnly:
    def test_the_owner_makes_members_read_only(self, http_client, owner):
        dataset = create_dataset(http_client, owner)

        response = _members(http_client, dataset["id"], owner, False)

        assert_status_code(response, 200)
        body = response.json()
        assert body["members_can_edit"] is False
        assert body["access"]["level"] == "owner"
        assert body["access"]["can_edit"] is True
        detail = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        assert detail["members_can_edit"] is False

    def test_members_read_and_download_but_change_nothing(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        version, file_id = _owner_file(http_client, dataset, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        user_id, headers = editor

        read = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        download = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version}/files/{file_id}",
            headers=headers,
        )
        update = _update(http_client, dataset["id"], headers)
        new_version = http_client.post(
            f"/datasets/{dataset['id']}/versions",
            json={"datafilesPreviouslyUploaded": []},
            headers=headers,
        )
        upload = _tus(http_client, dataset["id"], user_id)

        assert_status_code(read, 200)
        body = read.json()
        assert body["access"]["level"] == "tenancy"
        assert body["access"]["can_edit"] is False
        assert body["access"]["can_share"] is False
        assert body["access"]["can_delete"] is False
        assert body["current_version"]["files_withheld"] is False
        assert len(body["current_version"]["files_in"]) == 1
        assert_status_code(download, 200)
        assert_status_code(update, 403)
        assert update.json() == {"detail": "forbidden"}
        assert_status_code(new_version, 403)
        assert upload.json().get("RejectUpload") is True
        assert upload.json()["HTTPResponse"]["StatusCode"] == 403

    def test_a_role_that_deletes_deletes_only_in_the_default_mode(
        self, http_client, owner, deleter
    ):
        _, headers = deleter
        read_only = create_dataset(http_client, owner)
        editable = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, read_only["id"], owner, False), 200)

        refused = http_client.delete(f"/datasets/{read_only['id']}", headers=headers)
        allowed = http_client.delete(f"/datasets/{editable['id']}", headers=headers)

        assert_status_code(refused, 403)
        assert_status_code(
            http_client.get(f"/datasets/{read_only['id']}", headers=owner), 200
        )
        assert_status_code(allowed, 200)

    def test_a_write_permission_still_edits(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        update = _update(http_client, dataset["id"], headers)

        assert_status_code(update, 200)

    def test_a_read_permission_does_not_borrow_the_roles_write(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        user_id, headers = editor
        grant(http_client, dataset["id"], user_id, "read")
        assert_status_code(_update(http_client, dataset["id"], headers), 200)

        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)

        assert_status_code(_update(http_client, dataset["id"], headers), 403)

    def test_lists_and_versions_carry_the_setting(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "read")
        version = dataset["current_version"]["name"]

        minimal = http_client.get(
            "/datasets/?shared=true&minimal=true", headers=headers
        )
        full = http_client.get("/datasets/?shared=true", headers=headers)
        by_version = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version}", headers=owner
        )

        for listing in (minimal, full):
            assert_status_code(listing, 200)
            item = next(
                i for i in listing.json()["content"] if i["id"] == dataset["id"]
            )
            assert item["members_can_edit"] is False
        assert_status_code(by_version, 200)
        assert by_version.json()["members_can_edit"] is False


class TestWithAnEmbargo:
    def test_the_setting_is_inert_during_the_embargo_and_decides_afterwards(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        assert_status_code(_members(http_client, dataset["id"], owner, False), 200)
        assert_status_code(
            set_embargo(http_client, dataset["id"], owner, visible=False), 200
        )
        _, headers = editor

        during = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        ended = http_client.post(
            f"/datasets/{dataset['id']}/embargo/end", headers=owner
        )
        after = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        update = _update(http_client, dataset["id"], headers)

        assert_status_code(during, 404)
        assert_status_code(ended, 200)
        assert_status_code(after, 200)
        assert after.json()["access"]["can_edit"] is False
        assert after.json()["members_can_edit"] is False
        assert_status_code(update, 403)

    def test_by_default_members_edit_again_after_the_embargo(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        http_client.post(f"/datasets/{dataset['id']}/embargo/end", headers=owner)
        _, headers = editor

        assert_status_code(_update(http_client, dataset["id"], headers), 200)

    def test_the_owner_changes_it_during_the_embargo(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        response = _members(http_client, dataset["id"], owner, False)

        assert_status_code(response, 200)
        assert response.json()["members_can_edit"] is False


class TestWhoMayChangeIt:
    def test_a_member_who_sees_the_dataset_is_forbidden(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        _, headers = editor

        response = _members(http_client, dataset["id"], headers, False)

        assert_status_code(response, 403)
        assert response.json() == {"detail": "forbidden"}

    def test_a_write_permission_is_forbidden(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        response = _members(http_client, dataset["id"], headers, False)

        assert_status_code(response, 403)
        assert response.json() == {"detail": "forbidden"}

    def test_a_member_who_cannot_see_the_dataset_gets_404(
        self, http_client, owner, editor
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = editor

        assert_status_code(_members(http_client, dataset["id"], headers, False), 404)

    def test_a_body_without_a_boolean_is_refused(self, http_client, owner):
        dataset = create_dataset(http_client, owner)

        for body in ({}, {"members_can_edit": "false"}, {"members_can_edit": 0}):
            response = http_client.put(
                f"/datasets/{dataset['id']}/members-access", json=body, headers=owner
            )
            assert_status_code(response, 422)
        detail = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        assert detail["members_can_edit"] is True


class TestHistoryAndShareState:
    def test_each_change_is_in_the_history_once(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        _members(http_client, dataset["id"], owner, False)
        _members(http_client, dataset["id"], owner, False)

        history = http_client.get(
            f"/datasets/{dataset['id']}/access-events", headers=owner
        )

        assert_status_code(history, 200)
        changes = [
            item
            for item in history.json()["items"]
            if item["event_type"] == "members_access_changed"
        ]
        assert len(changes) == 1
        assert changes[0]["old_value"] == {"members_can_edit": True}
        assert changes[0]["new_value"] == {"members_can_edit": False}
        assert changes[0]["actor"]["id"] == config.user_id
        assert changes[0]["subject"] is None

    def test_the_share_state_says_what_members_can_do(self, http_client, owner):
        dataset = create_dataset(http_client, owner)

        before = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
        _members(http_client, dataset["id"], owner, False)
        after = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        during = http_client.get(f"/datasets/{dataset['id']}/share", headers=owner)

        assert before.json()["tenancy"]["members_can_edit"] is True
        assert after.json()["tenancy"]["members_can_edit"] is False
        assert during.json()["tenancy"] is None
