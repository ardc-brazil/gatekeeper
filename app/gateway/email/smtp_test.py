import smtplib
import socket
import unittest
from email.message import EmailMessage
from unittest.mock import MagicMock, Mock

from app.gateway.email.smtp import (
    DefiniteSendFailure,
    SmtpSender,
    UncertainSendFailure,
)


def _message() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "DataMap <datamap@example.com>"
    message["To"] = "someone@example.com"
    message["Subject"] = "Hello"
    message.set_content("Hi")
    return message


class TestSmtpSender(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.factory = Mock(return_value=self.connection)

    def sender(self, **overrides) -> SmtpSender:
        options = dict(
            host="smtp.example.com",
            port=587,
            username="datamap@example.com",
            password="app-password",
            starttls=True,
            timeout_seconds=7,
            smtp_factory=self.factory,
        )
        options.update(overrides)
        return SmtpSender(**options)

    def test_it_upgrades_logs_in_sends_and_quits(self):
        message = _message()

        self.sender().send(message)

        self.factory.assert_called_once_with(
            "smtp.example.com", 587, timeout=7, local_hostname=None
        )
        self.connection.starttls.assert_called_once()
        self.connection.login.assert_called_once_with(
            "datamap@example.com", "app-password"
        )
        self.connection.send_message.assert_called_once_with(message)
        self.connection.quit.assert_called_once()

    def test_it_greets_the_server_with_the_public_hostname(self):
        self.sender(local_hostname="datamap.pcs.usp.br").send(_message())

        self.factory.assert_called_once_with(
            "smtp.example.com", 587, timeout=7, local_hostname="datamap.pcs.usp.br"
        )

    def test_without_credentials_it_does_not_log_in(self):
        self.sender(username=None, password=None, starttls=False).send(_message())

        self.connection.starttls.assert_not_called()
        self.connection.login.assert_not_called()

    def test_a_refused_connection_is_definite(self):
        self.factory.side_effect = ConnectionRefusedError("refused")

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_wrong_credentials_are_definite(self):
        self.connection.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"5.7.8 Username and Password not accepted"
        )

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_a_recipient_the_server_refuses_is_definite(self):
        self.connection.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {"someone@example.com": (550, b"no such user")}
        )

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_content_the_server_refuses_is_definite(self):
        self.connection.send_message.side_effect = smtplib.SMTPDataError(
            552, b"message too big"
        )

        with self.assertRaises(DefiniteSendFailure):
            self.sender().send(_message())

    def test_a_disconnect_while_sending_is_uncertain(self):
        self.connection.send_message.side_effect = smtplib.SMTPServerDisconnected(
            "Connection unexpectedly closed"
        )

        with self.assertRaises(UncertainSendFailure):
            self.sender().send(_message())

    def test_a_timeout_while_sending_is_uncertain(self):
        self.connection.send_message.side_effect = socket.timeout("timed out")

        with self.assertRaises(UncertainSendFailure):
            self.sender().send(_message())

    def test_an_uncertain_send_closes_the_socket_without_waiting_on_quit(self):
        self.connection.send_message.side_effect = socket.timeout("timed out")

        with self.assertRaises(UncertainSendFailure):
            self.sender().send(_message())

        self.connection.quit.assert_not_called()
        self.connection.close.assert_called_once()

    def test_a_failing_quit_after_a_send_is_not_a_failure(self):
        self.connection.quit.side_effect = smtplib.SMTPServerDisconnected("gone")

        self.sender().send(_message())

        self.connection.send_message.assert_called_once()

    def test_a_refused_recipient_does_not_leak_the_address(self):
        self.connection.send_message.side_effect = smtplib.SMTPRecipientsRefused(
            {
                "someone@example.com": (
                    550,
                    b"5.1.1 <someone@example.com> does not exist",
                )
            }
        )

        with self.assertRaises(DefiniteSendFailure) as context:
            self.sender().send(_message())

        self.assertNotIn("someone@example.com", str(context.exception))
        self.assertIn("550", str(context.exception))

    def test_a_refused_sender_does_not_leak_the_address(self):
        self.connection.send_message.side_effect = smtplib.SMTPSenderRefused(
            553, b"5.1.8 sender address rejected", "someone@example.com"
        )

        with self.assertRaises(DefiniteSendFailure) as context:
            self.sender().send(_message())

        self.assertNotIn("someone@example.com", str(context.exception))
        self.assertIn("553", str(context.exception))

    def test_a_data_refusal_does_not_leak_the_address(self):
        self.connection.send_message.side_effect = smtplib.SMTPDataError(
            554, b"rejected <someone@example.com>"
        )

        with self.assertRaises(DefiniteSendFailure) as context:
            self.sender().send(_message())

        self.assertNotIn("someone@example.com", str(context.exception))
        self.assertIn("554", str(context.exception))
