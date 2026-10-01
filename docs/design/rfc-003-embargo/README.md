# RFC 003 design, vendored

The layout for the dataset embargo, sharing and anonymous links, as designed in Claude Design. Copied here on 2026-10-01 so the people implementing plans 03 and 05 can read it without access to the design tool.

Source: https://claude.ai/design/p/7cd4706b-2943-4344-8d7c-212f40b88874 ("Email templates for Datamap"). Every file is a byte-exact copy of the project file at the etag below, checked against the size the project reports. The one exception is `brand/svg/datamap-mark.svg`: the design tool adds a C2PA provenance manifest when the file is read, and the copy here is the stored file without it (430 bytes, as listed).

`Embargo Feature.dc.html` is a design canvas, not a page to ship: `support.js` is the canvas runtime that renders it, and the `{{ … }}` placeholders and `<sc-for>` loops are filled from the `renderVals()` data at the end of the file. Read its source, or open it next to `support.js` in a browser. Its sections are anchored `#1a` … `#1j`; the plans cite them by those ids and by each screen's `data-screen-label`.

The emails are static HTML with sample data. The Jinja templates in `app/resources/email_templates/` reproduce their layout and copy; `emails/preview/*-dark.html` are the same messages with the dark-mode rules forced on (`@media all`), which is what `base.html`'s `@media (prefers-color-scheme: dark)` block must produce.

Where the design and a recorded decision in RFC 003 differ, the decision wins; the plans list each such place.

| File | Etag | Used by |
|---|---|---|
| `Embargo Feature.dc.html` | 1790885917525169 | plan 05, tasks 7–15 (sections 1a–1i); plan 03, task 8 (1j) |
| `support.js` | 1790800661513176 | renders the canvas; not used by the code |
| `emails/embargo-invitation.html` | 1790885916229676 | plan 03, task 8: `dataset_invitation` |
| `emails/embargo-reminder-owner.html` | 1790885916229676 | plan 03, task 8: `embargo_reminder`, owner variant |
| `emails/embargo-reminder-collaborator.html` | 1790881953019690 | plan 03, task 8: `embargo_reminder`, collaborator variant |
| `emails/embargo-ended-owner.html` | 1790885916229676 | plan 03, task 8: `embargo_ended`, owner variant |
| `emails/embargo-ended-collaborator.html` | 1790881953019690 | plan 03, task 8: `embargo_ended`, collaborator variant |
| `emails/invitation.html` | 1790802591351052 | reference only: the design the repo's `invitation.html` came from |
| `emails/notification.html` | 1790802591351052 | reference only: the design the repo's `notification.html` came from; plan 03 renders *access granted* with it |
| `emails/preview/*-dark.html` | same as the light file | plan 03, task 8: dark-mode check |
| `brand/svg/datamap-mark.svg` | 1790803127521597 | the mark the canvas shows in headers |
| `public/img/avatar-placeholder.svg` | 1790801623996033 | the avatar the canvas shows in headers |

`emails/invitation.html` and `emails/notification.html` still show "Notification preferences", "Unsubscribe" and a footer link to `/datasets`. Those were removed from the repo's templates on purpose (gatekeeper #125): the features do not exist and the page is `/app/datasets`. Do not copy them back.

## Sections and the tasks that build them

| Section | Screens | Plan 05 task |
|---|---|---|
| 1a | Create a dataset, *Who can see it* | 8 (`EmbargoFields`), 9 |
| 1b | Dataset details, owner under embargo | 7 (badge), 8 (embargo card, access card), 10 (Share button) |
| 1c | Share dialog, without embargo, typing, new anonymous link, link created once | 10 |
| 1d | Extend, End early, External DOI, Register external DOI, Hide from members, Remove access | 8, 10, 14 |
| 1e | Member view, open mode | 8 |
| 1f | Datasets list and *Shared with me* | 7 |
| 1g | Settings: embargo, access, history | 8 |
| 1h | Embargo ended banner | 8 |
| 1i | DOI landing, anonymous view (active, ended), accept invitation, already used | 11, 12, 13 |
| 1j | Emails | plan 03, task 8 |

Drawn but not built, since RFC 003 does not ask for them: the *Cite* button (1e), the *Not published* pill (1h), *Delete dataset* inside Settings (1g). The DOI page's "DataMap is data platform" is written "is a data platform".
