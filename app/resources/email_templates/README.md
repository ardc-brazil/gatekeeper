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
| `sign_up_code` | `name`, `code`, `expires_in_minutes` | |
| `email_verification_code` | `name`, `code`, `orcid`, `expires_in_minutes` | |
| `password_reset` | `name`, `link` | |
| `sign_up_existing_account` | `name`, `link` | |
| `tenancy_request_received` | `requester_name`, `requester_email`, `email_confirmed`, `requested_name`, `reason`, `requested_at`, `review_url` | |
| `tenancy_access_granted` | `user_name`, `admin_name`, `tenancy_display_name`, `tenancy_path`, `datasets_count`, `open_url` | |
| `tenancy_request_declined` | `user_name`, `requested_name`, `open_url` | `decision_message` |
| `tenancy_invitation` | `invitee_name`, `inviter_name`, `tenancy_display_name`, `tenancy_path`, `dataset_name`, `open_url` | |
| `tenancy_invitation_notice` | `inviter_name`, `invitee_name`, `invitee_email`, `tenancy_display_name`, `tenancy_path`, `dataset_name`, `tenancy_url` | |
