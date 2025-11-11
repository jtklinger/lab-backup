"""
Application configuration management using Pydantic Settings.
"""
from typing import Optional, List
from pydantic import field_validator, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    APP_NAME: str = "Lab Backup System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Database
    DATABASE_URL: PostgresDsn
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 7200  # 2 hours

    # Storage
    BACKUP_BASE_PATH: str = "/backups"
    BACKUP_COMPRESSION: str = "zstd"  # gzip, zstd, none
    BACKUP_ENCRYPTION_ENABLED: bool = False
    MAX_BACKUP_SIZE_GB: int = 1000

    # Email/SMTP
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    SMTP_FROM_EMAIL: str = "backups@example.com"
    SMTP_FROM_NAME: str = "Lab Backup System"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    LOG_FILE: Optional[str] = "/var/log/lab-backup/app.log"
    SYSLOG_ENABLED: bool = False
    SYSLOG_HOST: Optional[str] = None
    SYSLOG_PORT: int = 514

    # Monitoring
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090

    # Retention Defaults (in days)
    RETENTION_DAILY: int = 7
    RETENTION_WEEKLY: int = 28
    RETENTION_MONTHLY: int = 365
    RETENTION_YEARLY: int = 1825  # 5 years
    RETENTION_ARCHIVAL: int = -1  # Never expire

    # Alerts
    ALERT_STORAGE_THRESHOLD: int = 80  # percentage
    ALERT_ON_BACKUP_FAILURE: bool = True
    ALERT_ON_MISSED_SCHEDULE: bool = True

    # libvirt
    LIBVIRT_DEFAULT_URI: str = "qemu:///system"
    LIBVIRT_TIMEOUT: int = 300

    # Podman
    PODMAN_DEFAULT_URI: str = "unix:///run/podman/podman.sock"
    PODMAN_TIMEOUT: int = 300

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


# Global settings instance
settings = Settings()
