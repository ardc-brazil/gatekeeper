# Email templates

Jinja2 templates rendered by `EmailTemplateRenderer` (`app/service/email_template.py`).
`base.html` holds the header, footer and dark-mode styles; `_macros.html` the
building blocks (details panel, button, bullet list, notes). Values are
HTML-escaped, and a missing required variable raises `jinja2.UndefinedError`.

```python
renderer = EmailTemplateRenderer(site_url="https://datamap.pcs.usp.br")
email = renderer.render(EmailTemplate.INVITATION, {...})
email.subject, email.html
```

The renderer supplies `site_url` and `asset_url`. Images load from `{site_url}/img/email/`, which the webapp
serves from `public/img/email/`.

| Template | Required | Optional |
|---|---|---|
| `invitation` | `inviter_name`, `inviter_email`, `workspace_name`, `role`, `expires_on`, `accept_url` | |
| `announcement` | `title`, `preheader`, `published_on`, `body`, `cta_label`, `cta_url` | `image_url`, `image_alt`, `highlights` (list of str) |
| `dataset_reminder` | `dataset_title`, `draft_days`, `status`, `last_updated_on`, `files_summary`, `complete_url` | `missing_fields` (list of str) |
| `notification` | `title`, `preheader`, `message`, `cta_label`, `cta_url`, `reason` | `actor_name`, `details` (list of `{label, value}`) |
