import time
from datetime import timedelta, timezone

from tests.integration.fixtures.embargo import manual_doi
from tests.integration.fixtures.sharing import (
    create_user,
    dispatch,
    set_embargo,
    share,
)
from tests.integration.utils.database import execute
from tests.integration.utils.mailpit import Mailpit


def with_subject(messages: list[dict], fragment: str) -> list[dict]:
    return [message for message in messages if fragment in message["Subject"]]


def backdate_embargo_creation(dataset_id: str, days: int) -> None:
    execute(
        f"UPDATE dataset_access_events SET occurred_at = occurred_at - interval '{days} days' "
        f"WHERE dataset_id = '{dataset_id}' AND event_type = 'created'"
    )


def expired_events(dataset_id: str) -> str:
    return execute(
        "SELECT count(*) FROM dataset_access_events "
        f"WHERE dataset_id = '{dataset_id}' AND event_type = 'expired'"
    )


def share_with_a_reader(http_client, dataset_id: str) -> dict:
    reader = create_user(http_client)
    response = share(
        http_client, dataset_id, {"user_id": reader["id"], "level": "read"}
    )
    assert response.status_code == 201, response.text
    return reader


class TestEmbargoReminders:
    def test_a_reminder_already_past_when_the_embargo_was_set_is_never_sent(
        self, http_client, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()
        reader = share_with_a_reader(http_client, dataset["id"])
        set_embargo(
            http_client,
            dataset["id"],
            timedelta(days=4, hours=12),
            tz=timezone(timedelta(hours=-3)),
        )

        dispatch(http_client)

        Mailpit().wait_for(reader["email"], count=1)
        assert with_subject(Mailpit().messages_to(reader["email"]), "ends in") == []

    def test_a_reminder_reaches_each_person_exactly_once(
        self, http_client, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()
        reader = share_with_a_reader(http_client, dataset["id"])
        set_embargo(http_client, dataset["id"], timedelta(days=4, hours=12))
        backdate_embargo_creation(dataset["id"], days=30)

        dispatch(http_client)
        dispatch(http_client)

        messages = Mailpit().wait_for(reader["email"], count=2)
        reminders = with_subject(messages, "ends in 5 days")
        assert len(reminders) == 1
        text = Mailpit().message(reminders[0]["ID"])["Text"]
        assert "An embargo ends in 5 days." in text
        assert (
            "Integration Test User, the owner, is the person who can do that." in text
        )


class TestEmbargoEnd:
    def test_the_end_notice_goes_out_once_and_the_end_is_recorded_once(
        self, http_client, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()
        reader = share_with_a_reader(http_client, dataset["id"])
        set_embargo(http_client, dataset["id"], timedelta(seconds=3))
        time.sleep(3.5)

        dispatch(http_client)
        dispatch(http_client)

        messages = Mailpit().wait_for(reader["email"], count=2)
        notices = with_subject(messages, "has ended")
        assert len(notices) == 1
        text = Mailpit().message(notices[0]["ID"])["Text"]
        assert "The embargo on the dataset below ended today" in text
        assert "Your own access doesn't change." in text
        assert expired_events(dataset["id"]) == "1"

    def test_a_manual_doi_that_ends_the_embargo_tells_everyone_with_access_why(
        self, http_client, valid_headers, dataset_fixture
    ):
        dataset = dataset_fixture.create_test_dataset()
        reader = share_with_a_reader(http_client, dataset["id"])
        set_embargo(http_client, dataset["id"], timedelta(days=30))
        doi = manual_doi(http_client, dataset, valid_headers, end_embargo=True)
        assert doi.status_code in (200, 201), doi.text

        dispatch(http_client)
        dispatch(http_client)

        messages = Mailpit().wait_for(reader["email"], count=2)
        notices = with_subject(messages, "has ended")
        assert len(notices) == 1
        text = Mailpit().message(notices[0]["ID"])["Text"]
        assert "Registering the external DOI 10.82978/MANUAL" in text
        assert "ended the embargo on the dataset below today" in text
        assert expired_events(dataset["id"]) == "1"
