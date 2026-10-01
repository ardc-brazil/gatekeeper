import smtplib
import ssl
from email.message import EmailMessage

from app.metrics import metrics

_REFUSED_BY_SERVER = (
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
)


class DefiniteSendFailure(Exception):
    """The server certainly did not accept the message; it may be retried."""


class UncertainSendFailure(Exception):
    """The message may have been accepted; retrying could deliver it twice."""


def _refusal_summary(
    e: smtplib.SMTPRecipientsRefused
    | smtplib.SMTPSenderRefused
    | smtplib.SMTPDataError,
) -> str:
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        codes = sorted({code for code, _ in e.recipients.values()})
    else:
        codes = [e.smtp_code]
    return f"{type(e).__name__} {','.join(str(code) for code in codes)}"


class SmtpSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        starttls: bool,
        timeout_seconds: float = 10.0,
        smtp_factory=smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username or None
        self._password = password or None
        self._starttls = starttls
        self._timeout = timeout_seconds
        self._smtp_factory = smtp_factory

    def send(self, message: EmailMessage) -> None:
        with metrics.external_call("smtp", "send"):
            self._send(message)

    def _send(self, message: EmailMessage) -> None:
        try:
            connection = self._smtp_factory(
                self._host, self._port, timeout=self._timeout
            )
        except (OSError, smtplib.SMTPException) as e:
            raise DefiniteSendFailure(f"connect: {e}") from e

        try:
            try:
                if self._starttls:
                    connection.starttls(context=ssl.create_default_context())
                if self._username:
                    connection.login(self._username, self._password or "")
            except (OSError, smtplib.SMTPException) as e:
                raise DefiniteSendFailure(f"session: {e}") from e

            try:
                connection.send_message(message)
            except _REFUSED_BY_SERVER as e:
                raise DefiniteSendFailure(f"refused: {_refusal_summary(e)}") from e
            except (OSError, smtplib.SMTPException) as e:
                raise UncertainSendFailure(f"during send: {e}") from e
        finally:
            try:
                connection.quit()
            except (OSError, smtplib.SMTPException):
                pass
