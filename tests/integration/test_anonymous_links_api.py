import time
from datetime import timedelta

from tests.integration.fixtures.embargo import client_headers, manual_doi
from tests.integration.fixtures.embargo import set_embargo as embargo_for
from tests.integration.fixtures.sharing import set_embargo, token_of
from tests.integration.fixtures.tenancy import (
    PUBLIC,
    as_user,
    create_dataset,
    new_account,
    roles_of,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.database import execute


def create_link(http_client, valid_headers, dataset_id: str) -> dict:
    response = http_client.post(
        f"/datasets/{dataset_id}/anonymous-links",
        json={"label": "JGR, round 1"},
        headers=valid_headers,
    )
    assert_status_code(response, 201)
    return response.json()


def link_state(http_client, valid_headers, dataset_id: str) -> dict:
    state = http_client.get(f"/datasets/{dataset_id}/share", headers=valid_headers)
    assert_status_code(state, 200)
    return state.json()["anonymous_links"][0]


class TestAnonymousLinks:
    def test_the_page_redacts_authorship_and_lists_no_files(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = token_of(link["link"])

        page = http_client.get(f"/anonymous/{token}", headers=client_headers())

        assert_status_code(page, 200)
        body = page.json()
        assert body["state"] == "active"
        assert body["embargo_until"] is not None
        assert "dataset_id" not in body
        data = body["dataset"]["data"]
        assert data["authors"] == [{"name": "[redacted]", "email": "[redacted]"}]
        assert data["institution"] == "[redacted]"
        assert data["title"] == "[redacted]"
        assert data["description"] == "Dataset created for integration testing"
        assert body["dataset"]["name"] == embargoed_dataset["name"]
        for version in body["dataset"]["versions"]:
            assert set(version) == {"name", "created_at", "files_summary"}
            assert set(version["files_summary"]) == {
                "count",
                "total_size_bytes",
                "extensions",
            }

        listed = link_state(http_client, valid_headers, embargoed_dataset["id"])
        assert listed["views"]["count"] == 1
        assert listed["token_hint"] == f"{token[:4]}…{token[-4:]}"
        assert listed["link"] is None

    def test_the_link_is_shown_once_at_creation(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])

        assert link["link"].startswith("http://localhost:3000/anonymous/")
        assert link["views"]["count"] == 0
        listed = link_state(http_client, valid_headers, embargoed_dataset["id"])
        assert listed["id"] == link["id"]
        assert listed["link"] is None

    def test_a_revoked_link_is_not_found(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = token_of(link["link"])

        revoke = http_client.delete(
            f"/datasets/{embargoed_dataset['id']}/anonymous-links/{link['id']}",
            headers=valid_headers,
        )
        assert_status_code(revoke, 204)

        page = http_client.get(f"/anonymous/{token}", headers=client_headers())
        assert_status_code(page, 404)
        listed = link_state(http_client, valid_headers, embargoed_dataset["id"])
        assert listed["revoked_at"] is not None
        assert listed["views"]["count"] == 0

    def test_after_the_embargo_an_unpublished_dataset_stays_anonymised(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = token_of(link["link"])
        end = http_client.post(
            f"/datasets/{embargoed_dataset['id']}/embargo/end", headers=valid_headers
        )
        assert_status_code(end, 200)

        page = http_client.get(f"/anonymous/{token}", headers=client_headers())

        assert_status_code(page, 200)
        body = page.json()
        assert body["state"] == "ended"
        assert body["embargo_ended_at"] is not None
        assert "embargo_until" not in body
        assert "dataset_id" not in body
        assert body["dataset"]["data"]["institution"] == "[redacted]"
        assert body["dataset"]["data"]["description"] == (
            "Dataset created for integration testing"
        )
        listed = link_state(http_client, valid_headers, embargoed_dataset["id"])
        assert listed["views"]["count"] == 1

    def test_once_published_the_link_leads_to_the_public_page(
        self, http_client, valid_headers, embargoed_dataset
    ):
        link = create_link(http_client, valid_headers, embargoed_dataset["id"])
        token = token_of(link["link"])
        doi = manual_doi(
            http_client, embargoed_dataset, valid_headers, end_embargo=True
        )
        assert doi.status_code in (200, 201), doi.text

        page = http_client.get(f"/anonymous/{token}", headers=client_headers())

        assert_status_code(page, 200)
        assert page.json() == {
            "state": "published",
            "dataset_id": embargoed_dataset["id"],
        }
        listed = link_state(http_client, valid_headers, embargoed_dataset["id"])
        assert listed["views"]["count"] == 1

    def test_no_link_without_an_embargo(
        self, http_client, valid_headers, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()

        response = http_client.post(
            f"/datasets/{dataset['id']}/anonymous-links",
            json={"label": "x"},
            headers=valid_headers,
        )

        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "embargo_not_active"

    def test_no_link_once_the_embargo_has_ended(
        self, http_client, valid_headers, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()
        set_embargo(http_client, dataset["id"], timedelta(seconds=1))
        time.sleep(1.5)

        response = http_client.post(
            f"/datasets/{dataset['id']}/anonymous-links",
            json={"label": "x"},
            headers=valid_headers,
        )

        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "embargo_not_active"

    def test_a_blank_label_is_refused(
        self, http_client, valid_headers, embargoed_dataset
    ):
        response = http_client.post(
            f"/datasets/{embargoed_dataset['id']}/anonymous-links",
            json={"label": "   "},
            headers=valid_headers,
        )

        assert_status_code(response, 422)

    def test_the_page_needs_client_credentials(self, http_client, no_auth_headers):
        response = http_client.get("/anonymous/anything", headers=no_auth_headers)

        assert_status_code(response, 401)

    def test_an_unknown_token_is_not_found(self, http_client):
        response = http_client.get("/anonymous/not-a-token", headers=client_headers())

        assert_status_code(response, 404)

    def test_views_record_no_reviewer_identity(self):
        columns = execute(
            "SELECT string_agg(column_name, ',' ORDER BY column_name) "
            "FROM information_schema.columns "
            "WHERE table_name = 'dataset_anonymous_link_views'"
        )

        assert columns == "id,link_id,outcome,viewed_at"


class TestAnOwnerWithOnlyDatasetsWrite:
    def test_revokes_their_link_and_another_account_is_refused(self, http_client):
        owner, stranger = new_account(http_client), new_account(http_client)
        assert roles_of(owner["id"]) == ["datasets_write"]
        dataset = create_dataset(http_client, owner["id"], PUBLIC)
        headers = as_user(owner["id"], PUBLIC)
        assert_status_code(
            embargo_for(http_client, dataset["id"], headers, visible=False), 200
        )
        link = create_link(http_client, headers, dataset["id"])
        path = f"/datasets/{dataset['id']}/anonymous-links/{link['id']}"

        by_stranger = http_client.delete(path, headers=as_user(stranger["id"], PUBLIC))
        still_active = link_state(http_client, headers, dataset["id"])["revoked_at"]
        by_owner = http_client.delete(path, headers=headers)

        assert_status_code(by_stranger, 404)
        assert still_active is None
        assert_status_code(by_owner, 204)
        assert link_state(http_client, headers, dataset["id"])["revoked_at"] is not None

    def test_a_member_who_can_see_the_dataset_is_refused_with_403(self, http_client):
        owner, member = new_account(http_client), new_account(http_client)
        dataset = create_dataset(http_client, owner["id"], PUBLIC)
        headers = as_user(owner["id"], PUBLIC)
        assert_status_code(
            embargo_for(http_client, dataset["id"], headers, visible=True), 200
        )
        link = create_link(http_client, headers, dataset["id"])
        member_headers = as_user(member["id"], PUBLIC)

        seen = http_client.get(f"/datasets/{dataset['id']}", headers=member_headers)
        by_member = http_client.delete(
            f"/datasets/{dataset['id']}/anonymous-links/{link['id']}",
            headers=member_headers,
        )

        assert_status_code(seen, 200)
        assert_status_code(by_member, 403)
        assert by_member.json() == {"detail": "forbidden"}
        assert link_state(http_client, headers, dataset["id"])["revoked_at"] is None

    def test_revokes_through_a_path_with_upper_case_ids(self, http_client):
        owner = new_account(http_client)
        dataset = create_dataset(http_client, owner["id"], PUBLIC)
        headers = as_user(owner["id"], PUBLIC)
        assert_status_code(
            embargo_for(http_client, dataset["id"], headers, visible=False), 200
        )
        link = create_link(http_client, headers, dataset["id"])

        revoked = http_client.delete(
            f"/datasets/{dataset['id'].upper()}/anonymous-links/{link['id'].upper()}",
            headers=headers,
        )

        assert_status_code(revoked, 204)
