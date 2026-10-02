from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.model.sharing import (
    GrantResult,
    InvitationPreview,
    InvitationView,
    PermissionView,
    AnonymousLinkView,
    AnonymousPage,
    ShareState,
    ShareUser,
)


class ShareUserResponse(BaseModel):
    id: UUID
    name: str
    email: str | None = None


class PermissionResponse(BaseModel):
    user: ShareUserResponse | None
    level: str
    granted_at: datetime
    granted_by: UUID | None = None
    invited_as: str | None = None


class InvitationResponse(BaseModel):
    id: UUID
    email: str | None = None
    orcid: str | None = None
    level: str
    created_at: datetime
    accepted_at: datetime | None = None
    accepted_by: ShareUserResponse | None = None
    revoked_at: datetime | None = None


class AnonymousLinkViewsResponse(BaseModel):
    count: int
    first_at: datetime | None = None
    last_at: datetime | None = None


class AnonymousLinkResponse(BaseModel):
    id: UUID
    label: str
    token_hint: str | None = None
    created_at: datetime
    revoked_at: datetime | None = None
    views: AnonymousLinkViewsResponse
    link: str | None = None


class TenancyAccessResponse(BaseModel):
    name: str
    path: str
    members: int
    members_can_edit: bool = True


class ShareStateResponse(BaseModel):
    owner: ShareUserResponse | None
    permissions: list[PermissionResponse]
    invitations: list[InvitationResponse]
    anonymous_links: list[AnonymousLinkResponse]
    tenancy: TenancyAccessResponse | None = None


class GrantRequestBody(BaseModel):
    level: str
    user_id: UUID | None = None
    email: str | None = None
    orcid: str | None = None


class GrantResultResponse(BaseModel):
    kind: Literal["permission", "invitation"]
    permission: PermissionResponse | None = None
    invitation: InvitationResponse | None = None
    link: str | None = None


class UpdatePermissionBody(BaseModel):
    level: str


class LinkResponse(BaseModel):
    link: str


class CreateAnonymousLinkBody(BaseModel):
    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
    ]


class AcceptInvitationBody(BaseModel):
    token: str = Field(..., min_length=1)


class AcceptResultResponse(BaseModel):
    dataset_id: UUID
    level: str


class ClaimResponse(BaseModel):
    accepted: list[AcceptResultResponse]


class InvitationPreviewResponse(BaseModel):
    state: Literal["pending", "accepted"]
    dataset_name: str
    inviter_name: str
    owner_name: str
    level: str
    invited_as: str
    embargo_until: datetime | None = None
    accepted_at: datetime | None = None
    dataset_id: UUID | None = None


def adapt_user(user: ShareUser | None) -> ShareUserResponse | None:
    if user is None:
        return None
    return ShareUserResponse(id=user.id, name=user.name, email=user.email)


def adapt_permission(permission: PermissionView) -> PermissionResponse:
    return PermissionResponse(
        user=adapt_user(permission.user),
        level=permission.level,
        granted_at=permission.granted_at,
        granted_by=permission.granted_by,
        invited_as=permission.invited_as,
    )


def adapt_invitation(invitation: InvitationView) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        orcid=invitation.orcid,
        level=invitation.level,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
        accepted_by=adapt_user(invitation.accepted_by),
        revoked_at=invitation.revoked_at,
    )


def adapt_anonymous_link(
    link: AnonymousLinkView, url: str | None = None
) -> AnonymousLinkResponse:
    return AnonymousLinkResponse(
        id=link.id,
        label=link.label,
        token_hint=link.token_hint,
        created_at=link.created_at,
        revoked_at=link.revoked_at,
        views=AnonymousLinkViewsResponse(
            count=link.views.count,
            first_at=link.views.first_at,
            last_at=link.views.last_at,
        ),
        link=url,
    )


def adapt_share_state(state: ShareState) -> ShareStateResponse:
    return ShareStateResponse(
        owner=adapt_user(state.owner),
        permissions=[adapt_permission(p) for p in state.permissions],
        invitations=[adapt_invitation(i) for i in state.invitations],
        anonymous_links=[adapt_anonymous_link(link) for link in state.anonymous_links],
        tenancy=TenancyAccessResponse(
            name=state.tenancy.name,
            path=state.tenancy.path,
            members=state.tenancy.members,
            members_can_edit=state.tenancy.members_can_edit,
        )
        if state.tenancy
        else None,
    )


def adapt_invitation_preview(preview: InvitationPreview) -> InvitationPreviewResponse:
    return InvitationPreviewResponse(
        state=preview.state,
        dataset_name=preview.dataset_name,
        inviter_name=preview.inviter_name,
        owner_name=preview.owner_name,
        level=preview.level,
        invited_as=preview.invited_as,
        embargo_until=preview.embargo_until,
        accepted_at=preview.accepted_at,
        dataset_id=preview.dataset_id,
    )


def adapt_grant_result(result: GrantResult) -> GrantResultResponse:
    if result.kind == "permission":
        return GrantResultResponse(
            kind="permission", permission=adapt_permission(result.permission)
        )
    return GrantResultResponse(
        kind="invitation",
        invitation=adapt_invitation(result.invitation),
        link=result.link,
    )


def adapt_anonymous_page(page: AnonymousPage) -> dict:
    if page.state == "published":
        return {"state": "published", "dataset_id": str(page.dataset_id)}
    when = page.embargo_until if page.state == "active" else page.embargo_ended_at
    key = "embargo_until" if page.state == "active" else "embargo_ended_at"
    return {
        "state": page.state,
        key: when.isoformat() if when else None,
        "dataset": {
            "name": page.name,
            "data": page.data,
            "versions": [
                {
                    "name": version.name,
                    "created_at": version.created_at.isoformat(),
                    "files_summary": {
                        "count": version.file_count,
                        "total_size_bytes": version.total_size_bytes,
                        "extensions": [
                            {
                                "extension": item.extension,
                                "count": item.count,
                                "total_size_bytes": item.total_size_bytes,
                            }
                            for item in version.extensions
                        ],
                    },
                }
                for version in page.versions
            ],
        },
    }
