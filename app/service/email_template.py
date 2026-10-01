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


_OPTIONAL_DEFAULTS: dict[EmailTemplate, dict[str, Any]] = {
    EmailTemplate.ANNOUNCEMENT: {"image_url": None, "image_alt": "", "highlights": []},
    EmailTemplate.DATASET_REMINDER: {"missing_fields": []},
    EmailTemplate.NOTIFICATION: {"actor_name": None, "details": []},
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
