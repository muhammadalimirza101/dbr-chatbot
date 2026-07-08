"""User management — admin only. All changes audit-logged."""

from fastapi import APIRouter, HTTPException, status
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.models import User
from app.schemas.dashboard import UserAdminOut, UserCreate, UserUpdate
from app.services.audit import record_audit
from app.services.auth import hash_password

router = APIRouter(prefix="/users", tags=["users"])

_email_adapter = TypeAdapter(EmailStr)


@router.get("", response_model=list[UserAdminOut])
async def list_users(admin: AdminUser, db: DbSession) -> list[UserAdminOut]:
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return [UserAdminOut.model_validate(u) for u in users]


@router.post("", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, admin: AdminUser, db: DbSession) -> UserAdminOut:
    try:
        email = _email_adapter.validate_python(body.email).lower()
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email"
        ) from None
    exists = (
        await db.execute(select(User.id).where(User.email == email))
    ).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already in use")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    await record_audit(
        db, user_id=admin.id, action="user_created", entity_type="user",
        entity_id=user.id, details={"role": body.role.value},
    )
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: int, body: UserUpdate, admin: AdminUser, db: DbSession
) -> UserAdminOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        changes.get("is_active") is False or "role" in changes
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cannot change your own role or deactivate yourself",
        )

    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
        await record_audit(
            db, user_id=admin.id, action="password_reset", entity_type="user",
            entity_id=user.id,
        )
    for field, value in changes.items():
        setattr(user, field, value)
    if changes:
        await record_audit(
            db, user_id=admin.id, action="user_updated", entity_type="user",
            entity_id=user.id, details={"fields": sorted(changes)},
        )
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.model_validate(user)
