import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from harambeeone_api.config import get_settings
from harambeeone_api.database import get_session
from harambeeone_api.models import SchoolMembership

Role = Literal["owner", "bursar", "cashier", "auditor"]
Permission = Literal[
    "school:read",
    "school:manage",
    "periods:read",
    "periods:manage",
    "periods:reopen",
    "students:read",
    "students:write",
    "fees:read",
    "fees:write",
    "payments:read",
    "payments:write",
    "reconciliation:read",
    "reconciliation:write",
    "reports:read",
    "audit:read",
    "sponsors:read",
    "sponsors:write",
    "support:read",
    "support:write",
    "support:approve",
]

ALL_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        "school:read",
        "school:manage",
        "periods:read",
        "periods:manage",
        "periods:reopen",
        "students:read",
        "students:write",
        "fees:read",
        "fees:write",
        "payments:read",
        "payments:write",
        "reconciliation:read",
        "reconciliation:write",
        "reports:read",
        "audit:read",
        "sponsors:read",
        "sponsors:write",
        "support:read",
        "support:write",
        "support:approve",
    }
)
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    "owner": ALL_PERMISSIONS,
    "bursar": ALL_PERMISSIONS - {"sponsors:write", "periods:reopen", "support:approve"},
    "cashier": frozenset(
        {
            "school:read",
            "periods:read",
            "students:read",
            "fees:read",
            "payments:read",
            "payments:write",
        }
    ),
    "auditor": frozenset(
        {
            "school:read",
            "periods:read",
            "students:read",
            "fees:read",
            "payments:read",
            "reconciliation:read",
            "reports:read",
            "audit:read",
            "sponsors:read",
            "support:read",
        }
    ),
}
ROLE_ALIASES = {"owner_bursar": "owner"}


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None


@dataclass(frozen=True)
class SchoolContext:
    user: AuthenticatedUser
    school_id: uuid.UUID
    role: Role

    @property
    def actor(self) -> str:
        return self.user.email or str(self.user.id)

    def assert_school(self, requested_school_id: uuid.UUID) -> None:
        if requested_school_id != self.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this institution",
            )


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = token.strip()

    settings = get_settings()
    request = Request(
        f"{str(settings.supabase_url).rstrip('/')}/auth/v1/user",
        headers={
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:  # noqa: S310 - fixed trusted Supabase URL
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is invalid or has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    try:
        return AuthenticatedUser(id=uuid.UUID(payload["id"]), email=payload.get("email"))
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase returned an invalid user identity",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def get_school_context(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SchoolContext:
    membership = session.scalar(
        select(SchoolMembership).where(SchoolMembership.auth_user_id == user.id)
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete institution setup before using the bursar workspace",
        )
    role_name = ROLE_ALIASES.get(membership.role, membership.role)
    if role_name not in ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your institution role is not recognized",
        )
    return SchoolContext(user=user, school_id=membership.school_id, role=cast(Role, role_name))


def require_permission(permission: Permission):
    def authorize(
        context: Annotated[SchoolContext, Depends(get_school_context)],
    ) -> SchoolContext:
        if permission not in ROLE_PERMISSIONS[context.role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your institution role does not permit this action",
            )
        return context

    return authorize
