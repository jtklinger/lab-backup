"""
Authentication API endpoints.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    get_current_user,
    decode_token
)
from backend.core.config import settings
from backend.services.audit_logger import AuditLogger

router = APIRouter()


class Token(BaseModel):
    """Token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    """User creation model."""
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.VIEWER


class UserResponse(BaseModel):
    """User response model."""
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: datetime | None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response model with user data."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


async def _authenticate_user(
    form_data: OAuth2PasswordRequestForm,
    db: AsyncSession,
    request: Request
):
    """Helper function to authenticate user."""
    audit_logger = AuditLogger(db)
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")

    # Get user by username
    stmt = select(User).where(User.username == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
        # Log failed login attempt (Issue #9)
        await audit_logger.log_authentication(
            action="LOGIN",
            username=form_data.username,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "incorrect_credentials"}
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        # Log failed login attempt for inactive user (Issue #9)
        await audit_logger.log_authentication(
            action="LOGIN",
            username=form_data.username,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "inactive_user"}
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    # Log successful login (Issue #9)
    await audit_logger.log_authentication(
        action="LOGIN",
        username=user.username,
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"user_id": user.id}
    )

    # Create tokens
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    # Refresh user to ensure all fields are loaded
    await db.refresh(user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/token", response_model=Token)
async def token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """OAuth2 compatible token endpoint."""
    return await _authenticate_user(form_data, db, request)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return JWT tokens with user data."""
    return await _authenticate_user(form_data, db, request)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
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
        is_active=True
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Log user registration (Issue #9)
    await audit_logger.log_configuration_change(
        action="CREATE",
        user_id=user.id,
        resource_type="USER",
        resource_id=user.id,
        new_value={"username": user.username, "email": user.email, "role": user.role.value},
        ip_address=ip_address
    )

    return user


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout user (client should discard tokens)."""
    audit_logger = AuditLogger(db)
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")

    # Log logout (Issue #9)
    await audit_logger.log_authentication(
        action="LOGOUT",
        username=current_user.username,
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"user_id": current_user.id}
    )

    return {"message": "Successfully logged out"}


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using a valid refresh token.
    Returns new access and refresh tokens.
    """
    try:
        # Decode and validate refresh token
        payload = decode_token(request.refresh_token)

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from database
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )

        # Create new tokens
        access_token = create_access_token(data={"sub": user.username})
        refresh_token = create_refresh_token(data={"sub": user.username})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
