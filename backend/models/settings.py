"""
System settings stored in database.
"""
from typing import Optional
from sqlalchemy import String, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SystemSetting(Base):
    """System-wide configuration settings stored in database."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def get_typed_value(self):
        """Return value with proper type conversion."""
        if self.value is None:
            return None

        if self.value_type == "boolean":
            return self.value.lower() in ("true", "1", "yes")
        elif self.value_type == "integer":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "json":
            import json
            return json.loads(self.value)
        else:
            return self.value

    @classmethod
    def set_value(cls, value):
        """Convert value to string for storage."""
        if isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, (dict, list)):
            import json
            return json.dumps(value)
        else:
            return str(value)
