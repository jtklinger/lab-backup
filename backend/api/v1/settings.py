"""
System settings API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.settings import SystemSetting
from backend.core.security import get_current_user, require_role

router = APIRouter()


class SettingCreate(BaseModel):
    """Setting creation/update model."""
    key: str
    value: Optional[str]
    value_type: str = "string"
    category: str
    description: Optional[str] = None
    is_secret: bool = False


class SettingResponse(BaseModel):
    """Setting response model."""
    id: int
    key: str
    value: Optional[str]
    value_type: str
    category: str
    description: Optional[str]
    is_secret: bool

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    """Bulk settings update model."""
    settings: Dict[str, Any]


class SetupWizardData(BaseModel):
    """Initial setup wizard data."""
    admin_username: str
    admin_email: EmailStr
    admin_password: str
    smtp_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[EmailStr] = None
    retention_daily: int = 7
    retention_weekly: int = 4
    retention_monthly: int = 12
    retention_yearly: int = 5


@router.get("/categories", response_model=List[str])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all setting categories."""
    stmt = select(SystemSetting.category).distinct()
    result = await db.execute(stmt)
    categories = [row[0] for row in result.all()]
    return categories


@router.get("/category/{category}", response_model=List[SettingResponse])
async def get_settings_by_category(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all settings in a category."""
    stmt = select(SystemSetting).where(SystemSetting.category == category)
    result = await db.execute(stmt)
    settings = result.scalars().all()

    # Mask secret values for non-admin users
    if current_user.role != UserRole.ADMIN:
        for setting in settings:
            if setting.is_secret and setting.value:
                setting.value = "********"

    return settings


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific setting by key."""
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found"
        )

    # Mask secret values for non-admin users
    if current_user.role != UserRole.ADMIN and setting.is_secret and setting.value:
        setting.value = "********"

    return setting


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    value: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Update a setting value."""
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found"
        )

    setting.value = SystemSetting.set_value(value)
    await db.commit()
    await db.refresh(setting)

    return setting


@router.post("", response_model=SettingResponse, status_code=status.HTTP_201_CREATED)
async def create_setting(
    setting_data: SettingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Create a new setting."""
    # Check if setting already exists
    stmt = select(SystemSetting).where(SystemSetting.key == setting_data.key)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setting already exists"
        )

    setting = SystemSetting(
        key=setting_data.key,
        value=SystemSetting.set_value(setting_data.value) if setting_data.value else None,
        value_type=setting_data.value_type,
        category=setting_data.category,
        description=setting_data.description,
        is_secret=setting_data.is_secret
    )

    db.add(setting)
    await db.commit()
    await db.refresh(setting)

    return setting


@router.put("/bulk", response_model=Dict[str, str])
async def bulk_update_settings(
    updates: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Bulk update multiple settings."""
    updated = []

    for key, value in updates.settings.items():
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = SystemSetting.set_value(value)
            updated.append(key)

    await db.commit()

    return {
        "message": f"Updated {len(updated)} settings",
        "updated": updated
    }


@router.get("/setup/status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    """Check if initial setup is complete."""
    # Check if admin user exists
    from backend.models.user import User
    stmt = select(User).where(User.role == UserRole.ADMIN)
    result = await db.execute(stmt)
    admin_exists = result.scalar_one_or_none() is not None

    # Check if any settings exist
    stmt = select(SystemSetting).limit(1)
    result = await db.execute(stmt)
    settings_exist = result.scalar_one_or_none() is not None

    return {
        "setup_complete": admin_exists and settings_exist,
        "admin_exists": admin_exists,
        "settings_exist": settings_exist
    }


@router.post("/setup/initialize")
async def initialize_setup(
    setup_data: SetupWizardData,
    db: AsyncSession = Depends(get_db)
):
    """Initialize system with setup wizard data."""
    # Check if setup is already complete
    from backend.models.user import User
    stmt = select(User).where(User.role == UserRole.ADMIN)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already initialized"
        )

    # Create admin user
    from backend.core.security import get_password_hash
    admin = User(
        username=setup_data.admin_username,
        email=setup_data.admin_email,
        password_hash=get_password_hash(setup_data.admin_password),
        role=UserRole.ADMIN,
        is_active=True
    )
    db.add(admin)

    # Create default settings
    default_settings = [
        # SMTP Settings
        ("smtp.enabled", setup_data.smtp_enabled, "boolean", "email", "Enable email notifications"),
        ("smtp.host", setup_data.smtp_host or "", "string", "email", "SMTP server host"),
        ("smtp.port", setup_data.smtp_port or 587, "integer", "email", "SMTP server port"),
        ("smtp.user", setup_data.smtp_user or "", "string", "email", "SMTP username", True),
        ("smtp.password", setup_data.smtp_password or "", "string", "email", "SMTP password", True),
        ("smtp.from_email", setup_data.smtp_from_email or "", "string", "email", "From email address"),
        ("smtp.tls", True, "boolean", "email", "Use TLS encryption"),

        # Retention Settings
        ("retention.daily", setup_data.retention_daily, "integer", "retention", "Days to keep daily backups"),
        ("retention.weekly", setup_data.retention_weekly, "integer", "retention", "Weeks to keep weekly backups"),
        ("retention.monthly", setup_data.retention_monthly, "integer", "retention", "Months to keep monthly backups"),
        ("retention.yearly", setup_data.retention_yearly, "integer", "retention", "Years to keep yearly backups"),

        # Alert Settings
        ("alerts.storage_threshold", 80, "integer", "alerts", "Storage usage alert threshold (%)"),
        ("alerts.on_backup_failure", True, "boolean", "alerts", "Alert on backup failures"),
        ("alerts.on_missed_schedule", True, "boolean", "alerts", "Alert on missed schedules"),

        # Backup Settings
        ("backup.compression", "zstd", "string", "backup", "Default compression algorithm"),
        ("backup.encryption_enabled", False, "boolean", "backup", "Enable backup encryption"),

        # System Settings
        ("system.setup_complete", True, "boolean", "system", "Initial setup completed"),
    ]

    for key, value, value_type, category, description, *is_secret in default_settings:
        setting = SystemSetting(
            key=key,
            value=SystemSetting.set_value(value),
            value_type=value_type,
            category=category,
            description=description,
            is_secret=is_secret[0] if is_secret else False
        )
        db.add(setting)

    await db.commit()

    return {
        "message": "System initialized successfully",
        "admin_username": setup_data.admin_username
    }
