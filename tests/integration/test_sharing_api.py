import uuid

from tests.integration.config import config
from tests.integration.fixtures.embargo import client_headers, headers_for
from tests.integration.fixtures.sharing import (
    create_user,
    dispatch,
    random_orcid,
    share,
    token_of,
)
from tests.integration.utils.assertions import assert_status_code
from tests.integration.utils.mailpit import Mailpit


class TestShareWithAnAccountOutsideTheTenancy:
    def test_a_user_with_no_tenancy_and_no_role_reads_the_dataset_once_shared(
        self, http_client, embargoed_dataset
    ):
        outsider = create_user(http_client)
        dataset_id = embargoed_dataset["id"]
        headers = headers_for(outsider["id"], None)

        before = http_client.get(f"/datasets/{dataset_id}", headers=headers)
        assert before.status_code in (401, 404), before.text

        grant = share(
            http_client,
            dataset_id,
            {"email": outsider["email"].upper(), "level": "read"},
        )
        assert_status_code(grant, 201)
        assert grant.json()["kind"] == "permission"
        assert grant.json()["permission"]["user"]["id"] == outsider["id"]
        assert "invitation" not in grant.json()

        after = http_client.get(f"/datasets/{dataset_id}", headers=headers)
        assert_status_code(after, 200)
        assert after.json()["access"]["level"] == "read"

        shared = http_client.get("/datasets/?shared=true", headers=headers)
        assert_status_code(shared, 200)
        assert dataset_id in [item["id"] for item in shared.json()["content"]]

        cannot_edit = http_client.put(
            f"/datasets/{dataset_id}",
            json={"name": "x", "data": {}, "tenancy": embargoed_dataset["tenancy"]},
            headers=headers,
        )
        assert_status_code(cannot_edit, 403)

    def test_raising_the_level_lets_the_holder_edit(
        self, http_client, valid_headers, embargoed_dataset
    ):
        outsider = create_user(http_client)
        dataset_id = embargoed_dataset["id"]
        share(http_client, dataset_id, {"user_id": outsider["id"], "level": "read"})

        raised = http_client.put(
            f"/datasets/{dataset_id}/share/permissions/{outsider['id']}",
            json={"level": "write"},
            headers=valid_headers,
        )

        assert_status_code(raised, 200)
        assert raised.json()["level"] == "write"
        body = http_client.get(
            f"/datasets/{dataset_id}", headers=headers_for(outsider["id"], None)
        ).json()
        assert body["access"]["level"] == "write"
        assert body["access"]["can_edit"] is True

    def test_revoking_takes_the_access_away(
        self, http_client, valid_headers, embargoed_dataset
    ):
        outsider = create_user(http_client)
        dataset_id = embargoed_dataset["id"]
        share(http_client, dataset_id, {"user_id": outsider["id"], "level": "read"})

        revoke = http_client.delete(
            f"/datasets/{dataset_id}/share/permissions/{outsider['id']}",
            headers=valid_headers,
        )
        assert_status_code(revoke, 204)

        after = http_client.get(
            f"/datasets/{dataset_id}", headers=headers_for(outsider["id"], None)
        )
        assert_status_code(after, 404)

    def test_sharing_twice_with_the_same_account_is_refused(
        self, http_client, embargoed_dataset
    ):
        outsider = create_user(http_client)
        body = {"user_id": outsider["id"], "level": "read"}
        assert_status_code(share(http_client, embargoed_dataset["id"], body), 201)

        again = share(http_client, embargoed_dataset["id"], body)

        assert_status_code(again, 400)
        assert again.json()["errors"][0]["code"] == "already_has_access"

    def test_the_owner_cannot_share_with_themself(self, http_client, embargoed_dataset):
        response = share(
            http_client,
            embargoed_dataset["id"],
            {"user_id": config.user_id, "level": "read"},
        )

        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "cannot_share_with_owner"

    def test_the_share_state_lists_permissions_and_invitations(
        self, http_client, valid_headers, embargoed_dataset
    ):
        dataset_id = embargoed_dataset["id"]
        reader = create_user(http_client)
        share(http_client, dataset_id, {"user_id": reader["id"], "level": "read"})
        share(
            http_client,
            dataset_id,
            {"email": f"nobody_{uuid.uuid4().hex[:6]}@example.org", "level": "read"},
        )

        state = http_client.get(f"/datasets/{dataset_id}/share", headers=valid_headers)

        assert_status_code(state, 200)
        body = state.json()
        assert body["owner"]["id"] == config.user_id
        assert [p["user"]["id"] for p in body["permissions"]] == [reader["id"]]
        assert len(body["invitations"]) == 1
        assert body["invitations"][0]["accepted_at"] is None
        assert body["tenancy"] is None

    def test_someone_who_cannot_see_the_dataset_gets_404_on_its_share_state(
        self, http_client, embargoed_dataset
    ):
        outsider = create_user(http_client)

        response = http_client.get(
            f"/datasets/{embargoed_dataset['id']}/share",
            headers=headers_for(outsider["id"], None),
        )

        assert response.status_code in (401, 404), response.text

    def test_an_invalid_orcid_is_refused(self, http_client, embargoed_dataset):
        response = share(
            http_client,
            embargoed_dataset["id"],
            {"orcid": "0000-0002-1825-0098", "level": "read"},
        )

        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "invalid_orcid"

    def test_two_targets_at_once_are_refused(self, http_client, embargoed_dataset):
        response = share(
            http_client,
            embargoed_dataset["id"],
            {"email": "a@example.org", "orcid": random_orcid(), "level": "read"},
        )

        assert_status_code(response, 400)
        assert response.json()["errors"][0]["code"] == "share_target_ambiguous"


class TestInvitations:
    def invite(self, http_client, dataset_id: str, email: str | None = None) -> str:
        response = share(
            http_client,
            dataset_id,
            {
                "email": email or f"invitee_{uuid.uuid4().hex[:6]}@example.org",
                "level": "write",
            },
        )
        assert_status_code(response, 201)
        assert response.json()["kind"] == "invitation"
        assert "permission" not in response.json()
        return token_of(response.json()["link"])

    def test_the_link_is_accepted_once_by_any_account(
        self, http_client, valid_headers, embargoed_dataset
    ):
        token = self.invite(http_client, embargoed_dataset["id"])
        first = create_user(http_client)
        second = create_user(http_client)

        accepted = http_client.post(
            "/invitations/accept",
            json={"token": token},
            headers=headers_for(first["id"], None),
        )
        assert_status_code(accepted, 200)
        assert accepted.json() == {
            "dataset_id": embargoed_dataset["id"],
            "level": "write",
        }

        again = http_client.post(
            "/invitations/accept",
            json={"token": token},
            headers=headers_for(second["id"], None),
        )
        assert_status_code(again, 409)
        assert again.json()["detail"] == "invitation_already_accepted"

        dataset = http_client.get(
            f"/datasets/{embargoed_dataset['id']}",
            headers=headers_for(first["id"], None),
        )
        assert_status_code(dataset, 200)
        assert dataset.json()["access"]["level"] == "write"

        state = http_client.get(
            f"/datasets/{embargoed_dataset['id']}/share", headers=valid_headers
        ).json()
        assert state["invitations"][0]["accepted_by"]["id"] == first["id"]
        assert [p["user"]["id"] for p in state["permissions"]] == [first["id"]]
        assert state["permissions"][0]["invited_as"] == state["invitations"][0]["email"]

    def test_an_unknown_token_is_not_found(self, http_client):
        user = create_user(http_client)

        response = http_client.post(
            "/invitations/accept",
            json={"token": "not-a-token"},
            headers=headers_for(user["id"], None),
        )

        assert_status_code(response, 404)

    def test_the_email_carries_the_link_and_the_record_masks_it(
        self, http_client, valid_headers, embargoed_dataset
    ):
        invitee = f"invitee_{uuid.uuid4().hex[:8]}@example.org"
        token = self.invite(http_client, embargoed_dataset["id"], invitee)

        dispatch(http_client)
        messages = Mailpit().wait_for(invitee)

        assert len(messages) == 1
        assert "shared a dataset with you" in messages[0]["Subject"]
        text = Mailpit().message(messages[0]["ID"])["Text"]
        assert f"http://localhost:3000/invitations/{token}" in text
        record = http_client.get(
            f"/admin/emails/?recipient={invitee}", headers=valid_headers
        )
        assert_status_code(record, 200)
        detail = http_client.get(
            f"/admin/emails/{record.json()['items'][0]['id']}", headers=valid_headers
        ).json()
        assert detail["status"] == "sent"
        assert token not in detail["body_text"]
        assert token not in str(detail["context"])

    def test_a_pending_invitation_is_claimed_when_its_orcid_signs_in(
        self, http_client, embargoed_dataset
    ):
        orcid = random_orcid()
        invite = share(
            http_client,
            embargoed_dataset["id"],
            {"orcid": f"https://orcid.org/{orcid}", "level": "read"},
        )
        assert_status_code(invite, 201)
        assert invite.json()["invitation"]["orcid"] == orcid
        user = create_user(
            http_client, providers=[{"name": "orcid", "reference": orcid}]
        )

        claim = http_client.post(
            f"/users/{user['id']}/invitations/claim",
            headers=headers_for(user["id"], None),
        )

        assert_status_code(claim, 200)
        assert claim.json()["accepted"] == [
            {"dataset_id": embargoed_dataset["id"], "level": "read"}
        ]
        again = http_client.post(
            f"/users/{user['id']}/invitations/claim",
            headers=headers_for(user["id"], None),
        )
        assert again.json()["accepted"] == []


class TestInvitationPreview:
    def test_it_describes_the_invitation_before_and_after_acceptance(
        self, http_client, embargoed_dataset
    ):
        invitee = f"preview_{uuid.uuid4().hex[:8]}@example.org"
        token = TestInvitations().invite(http_client, embargoed_dataset["id"], invitee)

        pending = http_client.get(f"/invitations/{token}", headers=client_headers())

        assert_status_code(pending, 200)
        body = pending.json()
        assert body["state"] == "pending"
        assert body["dataset_name"] == embargoed_dataset["name"]
        assert body["level"] == "write"
        assert body["invited_as"] == invitee
        assert body["embargo_until"] is not None
        assert body["accepted_at"] is None
        assert body["dataset_id"] is None

        user = create_user(http_client)
        http_client.post(
            "/invitations/accept",
            json={"token": token},
            headers=headers_for(user["id"], None),
        )
        accepted = http_client.get(f"/invitations/{token}", headers=client_headers())

        assert_status_code(accepted, 200)
        assert accepted.json()["state"] == "accepted"
        assert accepted.json()["accepted_at"] is not None
        assert accepted.json()["dataset_id"] == embargoed_dataset["id"]

    def test_a_revoked_invitation_is_not_found(
        self, http_client, valid_headers, embargoed_dataset
    ):
        response = share(
            http_client,
            embargoed_dataset["id"],
            {"email": f"revoked_{uuid.uuid4().hex[:6]}@example.org", "level": "read"},
        )
        token = token_of(response.json()["link"])
        invitation_id = response.json()["invitation"]["id"]

        revoke = http_client.delete(
            f"/datasets/{embargoed_dataset['id']}/share/invitations/{invitation_id}",
            headers=valid_headers,
        )
        assert_status_code(revoke, 204)

        preview = http_client.get(f"/invitations/{token}", headers=client_headers())
        assert_status_code(preview, 404)

    def test_it_needs_client_credentials(self, http_client, no_auth_headers):
        assert_status_code(
            http_client.get("/invitations/anything", headers=no_auth_headers), 401
        )
