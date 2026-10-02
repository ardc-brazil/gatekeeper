import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from tests.integration.config import config
from tests.integration.fixtures.auth import AuthFixture
from tests.integration.fixtures.embargo import (
    TENANCY,
    auto_doi,
    client_headers,
    create_dataset,
    create_user,
    grant,
    headers_for,
    make_findable,
    manual_doi,
    set_embargo,
    until,
)
from tests.integration.fixtures.tus_auth import create_tus_payload
from tests.integration.utils.assertions import assert_status_code


@pytest.fixture
def owner():
    return AuthFixture.valid_headers()


@pytest.fixture
def member(http_client):
    user_id = create_user(http_client, ["datasets_write"], [TENANCY])
    return user_id, headers_for(user_id, TENANCY)


@pytest.fixture
def outsider(http_client):
    user_id = create_user(http_client, [], [])
    return user_id, headers_for(user_id, None)


def _ids(response) -> list[str]:
    return [item["id"] for item in response.json()["content"]]


def _upload(
    http_client, dataset: dict, user_id: str = config.user_id
) -> tuple[str, str]:
    payload = create_tus_payload(
        user_id=user_id,
        dataset_id=dataset["id"],
        filename="data.nc",
        file_size=10,
        file_type="application/x-netcdf",
    )
    response = http_client.post(
        "/tus/hooks", json=payload, headers=AuthFixture.valid_headers()
    )
    assert_status_code(response, 200)
    version = dataset["current_version"]["name"]
    body = http_client.get(
        f"/datasets/{dataset['id']}", headers=headers_for(user_id, TENANCY)
    ).json()
    files = next(v for v in body["versions"] if v["name"] == version)["files_in"]
    return version, files[0]["id"]


def _download(http_client, dataset_id: str, version: str, file_id: str, headers):
    return http_client.get(
        f"/datasets/{dataset_id}/versions/{version}/files/{file_id}", headers=headers
    )


def _expires(response) -> list[str]:
    assert_status_code(response, 200)
    return parse_qs(urlparse(response.json()["url"]).query)["X-Amz-Expires"]


class TestHiddenEmbargo:
    def test_a_tenancy_member_does_not_know_it_exists(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        assert_status_code(
            set_embargo(http_client, dataset["id"], owner, visible=False), 200
        )

        _, headers = member
        assert_status_code(
            http_client.get(f"/datasets/{dataset['id']}", headers=headers), 404
        )
        listing = http_client.get("/datasets/?page_size=20", headers=headers)
        assert_status_code(listing, 200)
        assert dataset["id"] not in _ids(listing)

    def test_every_write_answers_404(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = member

        update = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "x", "data": {}, "tenancy": TENANCY},
            headers=headers,
        )
        version = http_client.post(
            f"/datasets/{dataset['id']}/versions",
            json={"datafilesPreviouslyUploaded": []},
            headers=headers,
        )
        assert_status_code(update, 404)
        assert_status_code(version, 404)

    def test_an_upload_from_the_tenancy_is_rejected(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, _ = member

        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset["id"],
            filename="a.nc",
            file_size=10,
            file_type="application/x-netcdf",
        )
        response = http_client.post(
            "/tus/hooks", json=payload, headers=AuthFixture.valid_headers()
        )

        assert response.json().get("RejectUpload") is True


class TestOpenEmbargo:
    def test_a_tenancy_member_sees_the_badge_but_not_the_files(
        self, http_client, owner, member
    ):
        dataset = create_dataset(http_client, owner)
        assert_status_code(
            set_embargo(http_client, dataset["id"], owner, visible=True), 200
        )
        _, headers = member

        response = http_client.get(f"/datasets/{dataset['id']}", headers=headers)

        assert_status_code(response, 200)
        body = response.json()
        assert body["embargo"]["active"] is True
        assert body["embargo"]["metadata_visible"] is True
        assert body["access"]["level"] == "tenancy"
        assert body["access"]["can_edit"] is False
        for version in body["versions"]:
            assert version["files_withheld"] is True
            assert version["files_in"] == []
            assert "count" in version["files_summary"]

    def test_a_write_is_forbidden_not_hidden(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=True)
        _, headers = member

        response = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "x", "data": {}, "tenancy": TENANCY},
            headers=headers,
        )

        assert_status_code(response, 403)
        assert response.json() == {"detail": "forbidden"}

    def test_an_upload_from_the_tenancy_is_forbidden(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=True)
        user_id, _ = member

        payload = create_tus_payload(
            user_id=user_id,
            dataset_id=dataset["id"],
            filename="a.nc",
            file_size=10,
            file_type="application/x-netcdf",
        )
        response = http_client.post(
            "/tus/hooks", json=payload, headers=AuthFixture.valid_headers()
        )

        assert_status_code(response, 403)
        assert response.json().get("RejectUpload") is True
        assert response.json()["HTTPResponse"]["StatusCode"] == 403

    def test_switching_the_mode_changes_what_the_tenancy_sees(
        self, http_client, owner, member
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = member

        hidden = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        opened = http_client.put(
            f"/datasets/{dataset['id']}/embargo/mode",
            json={"metadata_visible": True},
            headers=owner,
        )
        visible = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        closed = http_client.put(
            f"/datasets/{dataset['id']}/embargo/mode",
            json={"metadata_visible": False},
            headers=owner,
        )
        hidden_again = http_client.get(f"/datasets/{dataset['id']}", headers=headers)

        assert_status_code(hidden, 404)
        assert_status_code(opened, 200)
        assert opened.json()["metadata_visible"] is True
        assert_status_code(visible, 200)
        assert visible.json()["embargo"]["metadata_visible"] is True
        assert_status_code(closed, 200)
        assert closed.json()["metadata_visible"] is False
        assert_status_code(hidden_again, 404)


class TestDownloadUnderEmbargo:
    def test_a_tenancy_member_is_forbidden_under_an_open_embargo(
        self, http_client, owner, member
    ):
        dataset = create_dataset(http_client, owner)
        version, file_id = _upload(http_client, dataset)
        set_embargo(http_client, dataset["id"], owner, visible=True)
        _, headers = member

        response = _download(http_client, dataset["id"], version, file_id, headers)

        assert_status_code(response, 403)

    def test_a_tenancy_member_gets_404_under_a_hidden_embargo(
        self, http_client, owner, member
    ):
        dataset = create_dataset(http_client, owner)
        version, file_id = _upload(http_client, dataset)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = member

        response = _download(http_client, dataset["id"], version, file_id, headers)

        assert_status_code(response, 404)

    def test_the_owner_link_lasts_an_hour_under_embargo_and_a_week_without(
        self, http_client, owner
    ):
        dataset = create_dataset(http_client, owner)
        version, file_id = _upload(http_client, dataset)

        before = _download(http_client, dataset["id"], version, file_id, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        during = _download(http_client, dataset["id"], version, file_id, owner)

        assert _expires(before) == ["604800"]
        assert _expires(during) == ["3600"]


class TestAdminWithoutOwnership:
    @pytest.fixture
    def dataset_of_a_member(self, http_client):
        owner_id = create_user(http_client, ["datasets_write"], [TENANCY])
        return create_dataset(http_client, headers_for(owner_id, TENANCY)), owner_id

    def test_the_admin_does_not_see_a_hidden_embargo(
        self, http_client, dataset_of_a_member
    ):
        dataset, owner_id = dataset_of_a_member
        set_embargo(
            http_client, dataset["id"], headers_for(owner_id, TENANCY), visible=False
        )

        response = http_client.get(
            f"/datasets/{dataset['id']}", headers=AuthFixture.valid_headers()
        )

        assert_status_code(response, 404)

    def test_the_admin_sees_only_the_badge_of_an_open_embargo(
        self, http_client, dataset_of_a_member
    ):
        dataset, owner_id = dataset_of_a_member
        _upload(http_client, dataset, owner_id)
        set_embargo(
            http_client, dataset["id"], headers_for(owner_id, TENANCY), visible=True
        )

        response = http_client.get(
            f"/datasets/{dataset['id']}", headers=AuthFixture.valid_headers()
        )

        assert_status_code(response, 200)
        body = response.json()
        assert body["embargo"]["active"] is True
        assert body["access"]["level"] == "tenancy"
        assert body["access"]["can_manage_embargo"] is False
        version = body["current_version"]
        assert version["files_withheld"] is True
        assert version["files_in"] == []
        assert version["files_summary"]["count"] == 1


class TestOwnerAndPermissions:
    def test_the_owner_sees_everything(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert body["access"]["level"] == "owner"
        assert body["access"]["can_manage_embargo"] is True
        assert all(v["files_withheld"] is False for v in body["versions"])

    def test_someone_with_no_tenancy_and_a_read_permission_reads_it(
        self, http_client, owner, outsider
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "read")

        response = http_client.get(f"/datasets/{dataset['id']}", headers=headers)
        shared = http_client.get("/datasets/?shared=true", headers=headers)
        update = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "x", "data": {}, "tenancy": TENANCY},
            headers=headers,
        )

        assert_status_code(response, 200)
        assert response.json()["access"]["level"] == "read"
        assert dataset["id"] in _ids(shared)
        assert_status_code(update, 403)

    def test_someone_with_no_tenancy_finds_it_in_every_listing(
        self, http_client, owner, outsider
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "read")
        version = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()[
            "versions"
        ][0]["name"]

        listing = http_client.get("/datasets/", headers=headers)
        minimal = http_client.get("/datasets/?minimal=true", headers=headers)
        by_version = http_client.get(
            f"/datasets/{dataset['id']}/versions/{version}", headers=headers
        )

        assert_status_code(listing, 200)
        assert dataset["id"] in _ids(listing)
        item = next(i for i in minimal.json()["content"] if i["id"] == dataset["id"])
        assert item["embargo"]["active"] is True
        assert item["access"]["level"] == "read"
        assert_status_code(by_version, 200)

    def test_a_write_permission_can_edit_and_does_not_take_ownership(
        self, http_client, owner, outsider
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        update = http_client.put(
            f"/datasets/{dataset['id']}",
            json={"name": "edited by collaborator", "data": {}, "tenancy": ""},
            headers=headers,
        )
        as_owner = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert_status_code(update, 200)
        assert as_owner["name"] == "edited by collaborator"
        assert as_owner["access"]["level"] == "owner"
        assert as_owner["tenancy"] == TENANCY

    def test_a_permission_holder_extends_only_when_the_owner_is_disabled(
        self, http_client
    ):
        owner_id = create_user(http_client, ["datasets_write"], [TENANCY])
        owner_headers = headers_for(owner_id, TENANCY)
        dataset = create_dataset(http_client, owner_headers)
        set_embargo(http_client, dataset["id"], owner_headers, visible=False, days=10)
        reader_id = create_user(http_client, [], [])
        grant(http_client, dataset["id"], reader_id, "read")
        reader = headers_for(reader_id, None)
        body = {"until": until(60)}

        refused = http_client.post(
            f"/datasets/{dataset['id']}/embargo/extend", json=body, headers=reader
        )
        http_client.delete(f"/users/{owner_id}", headers=AuthFixture.valid_headers())
        allowed = http_client.post(
            f"/datasets/{dataset['id']}/embargo/extend", json=body, headers=reader
        )

        assert_status_code(refused, 403)
        assert_status_code(allowed, 200)

    def test_shared_lists_only_what_was_shared_not_the_tenancy(
        self, http_client, owner
    ):
        of_the_tenancy = create_dataset(http_client, owner)
        shared_with_them = create_dataset(http_client, owner)
        user_id = create_user(http_client, ["datasets_write"], [TENANCY])
        grant(http_client, shared_with_them["id"], user_id, "read")

        response = http_client.get(
            "/datasets/?shared=true", headers=headers_for(user_id, TENANCY)
        )

        assert_status_code(response, 200)
        assert of_the_tenancy["id"] not in _ids(response)
        assert shared_with_them["id"] in _ids(response)

    def test_a_write_permission_cannot_delete(self, http_client, owner, outsider):
        dataset = create_dataset(http_client, owner)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        response = http_client.delete(f"/datasets/{dataset['id']}", headers=headers)
        as_owner = http_client.get(f"/datasets/{dataset['id']}", headers=owner)

        assert_status_code(response, 403)
        assert_status_code(as_owner, 200)


class TestEmbargoRules:
    def _error(self, response) -> str:
        assert_status_code(response, 400)
        return response.json()["errors"][0]["code"]

    def test_the_cap_applies_on_creation_and_extension(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        assert (
            self._error(
                set_embargo(http_client, dataset["id"], owner, visible=False, days=91)
            )
            == "embargo_too_long"
        )

        set_embargo(http_client, dataset["id"], owner, visible=False, days=10)
        response = http_client.post(
            f"/datasets/{dataset['id']}/embargo/extend",
            json={"until": until(91)},
            headers=owner,
        )
        assert self._error(response) == "embargo_too_long"

    def test_a_date_in_the_past_is_refused(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        response = http_client.put(
            f"/datasets/{dataset['id']}/embargo",
            json={"until": until(-1), "metadata_visible": False},
            headers=owner,
        )
        assert self._error(response) == "embargo_until_in_past"

    def test_a_published_dataset_cannot_be_embargoed(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        assert auto_doi(http_client, dataset, owner).status_code in (200, 201)
        assert_status_code(make_findable(http_client, dataset, owner), 200)

        response = set_embargo(http_client, dataset["id"], owner, visible=False)

        assert self._error(response) == "embargo_dataset_published"

    def test_a_dataset_with_a_manual_doi_cannot_be_embargoed(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        assert manual_doi(http_client, dataset, owner).status_code in (200, 201)

        response = set_embargo(http_client, dataset["id"], owner, visible=False)

        assert self._error(response) == "embargo_manual_doi"

    def test_a_datamap_doi_keeps_the_embargo_and_writes_no_snapshot(
        self, http_client, owner
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        doi = auto_doi(http_client, dataset, owner)
        findable = make_findable(http_client, dataset, owner)
        snapshot = http_client.get(f"/datasets/{dataset['id']}/snapshot")
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert doi.status_code in (200, 201), doi.text
        assert self._error(findable) == "embargo_active"
        assert_status_code(snapshot, 404)
        assert body["embargo"]["active"] is True


class TestManualDoiUnderEmbargo:
    def _error(self, response) -> str:
        assert_status_code(response, 400)
        return response.json()["errors"][0]["code"]

    def test_it_is_refused_without_confirmation(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        response = manual_doi(http_client, dataset, owner)
        snapshot = http_client.get(f"/datasets/{dataset['id']}/snapshot")
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert self._error(response) == "embargo_manual_doi_ends_embargo"
        assert_status_code(snapshot, 404)
        assert body["embargo"]["active"] is True
        assert body["current_version"]["doi"] is None

    def test_a_write_holder_cannot_end_the_owners_embargo(
        self, http_client, owner, outsider
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        user_id, headers = outsider
        grant(http_client, dataset["id"], user_id, "write")

        response = manual_doi(http_client, dataset, headers, end_embargo=True)
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()

        assert_status_code(response, 403)
        assert body["embargo"]["active"] is True

    def test_the_owner_confirms_and_the_embargo_ends_with_the_snapshot_published(
        self, http_client, owner, member
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, member_headers = member

        response = manual_doi(http_client, dataset, owner, end_embargo=True)
        snapshot = http_client.get(f"/datasets/{dataset['id']}/snapshot")
        body = http_client.get(f"/datasets/{dataset['id']}", headers=owner).json()
        as_member = http_client.get(
            f"/datasets/{dataset['id']}", headers=member_headers
        )

        assert response.status_code in (200, 201), response.text
        assert_status_code(snapshot, 200)
        assert body["embargo"]["active"] is False
        assert_status_code(as_member, 200)

    def test_ending_early_gives_the_tenancy_its_access_back(
        self, http_client, owner, member
    ):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)
        _, headers = member

        ended = http_client.post(
            f"/datasets/{dataset['id']}/embargo/end", headers=owner
        )

        assert_status_code(ended, 200)
        assert ended.json()["active"] is False
        assert_status_code(
            http_client.get(f"/datasets/{dataset['id']}", headers=headers), 200
        )

    def test_only_the_owner_sets_an_embargo(self, http_client, owner, member):
        dataset = create_dataset(http_client, owner)
        _, headers = member

        assert_status_code(
            set_embargo(http_client, dataset["id"], headers, visible=False), 403
        )


class TestEmbargoStatus:
    def test_it_answers_the_client_without_a_user(self, http_client, owner):
        dataset = create_dataset(http_client, owner)
        set_embargo(http_client, dataset["id"], owner, visible=False)

        response = http_client.get(
            f"/datasets/{dataset['id']}/embargo-status", headers=client_headers()
        )

        assert_status_code(response, 200)
        assert response.json()["embargoed"] is True
        assert response.json()["until"] is not None

    def test_an_unknown_dataset_reveals_nothing(self, http_client):
        response = http_client.get(
            f"/datasets/{uuid.uuid4()}/embargo-status", headers=client_headers()
        )

        assert_status_code(response, 200)
        assert response.json() == {"embargoed": False, "until": None}

    def test_it_needs_client_credentials(self, http_client):
        response = http_client.get(f"/datasets/{uuid.uuid4()}/embargo-status")

        assert_status_code(response, 401)
