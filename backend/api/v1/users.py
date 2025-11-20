"""
User Management API endpoints.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.core.security import (
    get_current_user,
    require_role,
    get_password_hash,
    verify_password
)
from backend.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

router = APIRouter()


class UserCreate(BaseModel):
    """User creation model."""
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class UserUpdate(BaseModel):
    """User update model."""
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """User response model."""
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[UserResponse], dependencies=[Depends(require_role(UserRole.ADMIN))])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all users (admin only).
    """
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role(UserRole.ADMIN))])
async def create_user(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new user (admin only).
    """
    audit_logger = AuditLogger(db)
    ip_address = request.client.host if request.client else "unknown"

    # Check if username exists
    stmt = select(User).where(User.username == user_data.username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Check if email exists
    stmt = select(User).where(User.email == user_data.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
        is_active=user_data.is_active
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Log user creation
    await audit_logger.log_configuration_change(
        action="CREATE_USER",
        user_id=current_user.id,
        resource_type="USER",
        resource_id=user.id,
        new_value={
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "is_active": user.is_active
        },
        ip_address=ip_address
    )

    return user


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_role(UserRole.ADMIN))])
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user by ID (admin only).
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    return user


@router.put("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update user by ID (admin only).
    """
    audit_logger = AuditLogger(db)
    ip_address = request.client.host if request.client else "unknown"

    # Get user
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    # Prevent deleting last admin
    if user.role == UserRole.ADMIN and user_data.role != UserRole.ADMIN:
        stmt = select(User).where(User.role == UserRole.ADMIN, User.is_active == True)
        result = await db.execute(stmt)
        active_admins = result.scalars().all()
        if len(active_admins) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change role of last active admin"
            )

    # Store old values for audit log
    old_values = {
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active
    }

    # Update fields
    if user_data.email is not None:
        # Check if email is already taken by another user
        stmt = select(User).where(User.email == user_data.email, User.id != user_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        user.email = user_data.email

    if user_data.password is not None and user_data.password.strip():
        user.password_hash = get_password_hash(user_data.password)

    if user_data.role is not None:
        user.role = user_data.role

    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    await db.commit()
    await db.refresh(user)

    # Log user update
    new_values = {
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active
    }

    await audit_logger.log_configuration_change(
        action="UPDATE_USER",
        user_id=current_user.id,
        resource_type="USER",
        resource_id=user.id,
        old_value=old_values,
        new_value=new_values,
        ip_address=ip_address
    )

    return user


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_role(UserRole.ADMIN))])
async def patch_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Partially update user by ID (admin only).
    This is used for quick toggles like is_active.
    """
    return await update_user(request, user_id, user_data, db, current_user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_user(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete user by ID (admin only).
    """
    audit_logger = AuditLogger(db)
    ip_address = request.client.host if request.client else "unknown"

    # Get user
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    # Prevent deleting yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # Prevent deleting last admin
    if user.role == UserRole.ADMIN:
        stmt = select(User).where(User.role == UserRole.ADMIN, User.is_active == True)
        result = await db.execute(stmt)
        active_admins = result.scalars().all()
        if len(active_admins) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete last active admin"
            )

    # Log user deletion before deleting
    await audit_logger.log_configuration_change(
        action="DELETE_USER",
        user_id=current_user.id,
        resource_type="USER",
        resource_id=user.id,
        old_value={
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "is_active": user.is_active
        },
        ip_address=ip_address
    )

    # Delete user
    await db.delete(user)
    await db.commit()

    return None
