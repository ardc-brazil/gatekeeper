import html as html_entities
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.service.email_text import html_to_text

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "email_templates"


class EmailTemplate(str, Enum):
    INVITATION = "invitation"
    ANNOUNCEMENT = "announcement"
    DATASET_REMINDER = "dataset_reminder"
    NOTIFICATION = "notification"
    DATASET_INVITATION = "dataset_invitation"
    EMBARGO_REMINDER = "embargo_reminder"
    EMBARGO_ENDED = "embargo_ended"
    SIGN_UP_CODE = "sign_up_code"
    EMAIL_VERIFICATION_CODE = "email_verification_code"
    PASSWORD_RESET = "password_reset"
    SIGN_UP_EXISTING_ACCOUNT = "sign_up_existing_account"
    TENANCY_REQUEST_RECEIVED = "tenancy_request_received"
    TENANCY_ACCESS_GRANTED = "tenancy_access_granted"
    TENANCY_REQUEST_DECLINED = "tenancy_request_declined"
    TENANCY_INVITATION = "tenancy_invitation"
    TENANCY_INVITATION_NOTICE = "tenancy_invitation_notice"


_OPTIONAL_DEFAULTS: dict[EmailTemplate, dict[str, Any]] = {
    EmailTemplate.ANNOUNCEMENT: {"image_url": None, "image_alt": "", "highlights": []},
    EmailTemplate.DATASET_REMINDER: {"missing_fields": []},
    EmailTemplate.NOTIFICATION: {"actor_name": None, "details": []},
    EmailTemplate.DATASET_INVITATION: {
        "inviter_email": None,
        "embargo_until_date": None,
        "note": None,
    },
    EmailTemplate.EMBARGO_REMINDER: {
        "owner_email": None,
        "owner_active": True,
        "people_with_access": [],
        "anonymous_link_count": 0,
        "later_offsets": [],
        "others_notified": False,
        "shared_by_name": None,
    },
    EmailTemplate.EMBARGO_ENDED: {
        "owner_email": None,
        "doi": None,
        "doi_registered": False,
        "ended_early": False,
        "ended_by_manual_doi": False,
        "anonymous_link_count": 0,
        "shared_by_name": None,
    },
    EmailTemplate.TENANCY_REQUEST_DECLINED: {"decision_message": None},
}


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str = ""


class EmailTemplateRenderer:
    """Renders the transactional email templates in resources/email_templates.

    Undefined variables raise instead of rendering blank, so a missing field
    fails at the call site rather than in someone's inbox.
    """

    def __init__(self, site_url: str, templates_dir: Path = TEMPLATES_DIR) -> None:
        self._site_url = site_url.rstrip("/")
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @property
    def site_url(self) -> str:
        return self._site_url

    def render(self, template: EmailTemplate, context: dict[str, Any]) -> RenderedEmail:
        variables = {
            "site_url": self._site_url,
            "asset_url": f"{self._site_url}/img/email",
            **_OPTIONAL_DEFAULTS.get(template, {}),
            **context,
        }
        jinja_template = self._env.get_template(f"{template.value}.html")
        subject = "".join(
            jinja_template.blocks["title"](jinja_template.new_context(variables))
        )
        html = jinja_template.render(variables)
        return RenderedEmail(
            subject=html_entities.unescape(subject.strip()),
            html=html,
            text=self._text(template, variables, html),
        )

    def _text(
        self, template: EmailTemplate, variables: dict[str, Any], html: str
    ) -> str:
        name = f"{template.value}.txt"
        if name not in self._env.list_templates():
            return html_to_text(html)
        return self._env.get_template(name).render(variables).strip()
