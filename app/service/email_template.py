from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "email_templates"


class EmailTemplate(str, Enum):
    INVITATION = "invitation"
    ANNOUNCEMENT = "announcement"
    DATASET_REMINDER = "dataset_reminder"
    NOTIFICATION = "notification"


_OPTIONAL_DEFAULTS: dict[EmailTemplate, dict[str, Any]] = {
    EmailTemplate.ANNOUNCEMENT: {"image_url": None, "image_alt": "", "highlights": []},
    EmailTemplate.DATASET_REMINDER: {"missing_fields": []},
    EmailTemplate.NOTIFICATION: {"actor_name": None, "details": []},
}


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str


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

    def render(self, template: EmailTemplate, context: dict[str, Any]) -> RenderedEmail:
        variables = {
            "site_url": self._site_url,
            "asset_url": f"{self._site_url}/img/email",
            "preferences_url": f"{self._site_url}/profile",
            "unsubscribe_url": f"{self._site_url}/unsubscribe",
            **_OPTIONAL_DEFAULTS.get(template, {}),
            **context,
        }
        jinja_template = self._env.get_template(f"{template.value}.html")
        subject = "".join(
            jinja_template.blocks["title"](jinja_template.new_context(variables))
        )
        return RenderedEmail(
            subject=subject.strip(), html=jinja_template.render(variables)
        )
