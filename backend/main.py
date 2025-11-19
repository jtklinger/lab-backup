"""
Main FastAPI application.
"""
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from backend.core.config import settings
from backend.core.logging_handler import setup_logging, setup_database_logging, setup_file_logging
from backend.api.v1 import auth, kvm, podman, storage, schedules, backups, jobs, logs, settings as settings_api, compliance, audit, dashboard

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Setup SIEM integration (Issue #9)
    try:
        from backend.services.siem_integration import configure_siem_integration, SyslogConfig
        siem_config = SyslogConfig(
            enabled=settings.SIEM_ENABLED,
            host=settings.SIEM_HOST or "localhost",
            port=settings.SIEM_PORT,
            protocol=settings.SIEM_PROTOCOL,
            format=settings.SIEM_FORMAT,
            facility=settings.SIEM_FACILITY,
            app_name=settings.APP_NAME
        )
        configure_siem_integration(siem_config)
        if settings.SIEM_ENABLED:
            print(f"🔐 SIEM integration enabled: {settings.SIEM_FORMAT.upper()} to {settings.SIEM_HOST}:{settings.SIEM_PORT}")
    except Exception as e:
        print(f"⚠️  Failed to setup SIEM integration: {e}")

    # Setup database logging (uses dedicated connection pool to avoid concurrency issues)
    try:
        setup_database_logging()
        print("📊 Database logging handler configured")
    except Exception as e:
        print(f"⚠️  Failed to setup database logging: {e}")

    # Setup file logging with rotation
    try:
        setup_file_logging()
        print("📄 File logging handler configured")
    except Exception as e:
        print(f"⚠️  Failed to setup file logging: {e}")

    # TODO: In-memory logging still disabled due to SSL issues
    # Database logging works fine (separate thread) but in-memory logging
    # causes SSL connections to hang when attached to fastapi/sqlalchemy loggers
    # try:
    #     setup_logging()
    #     print("📊 In-memory logging handler configured")
    # except Exception as e:
    #     print(f"⚠️  Failed to setup in-memory logging: {e}")

    yield
    # Shutdown
    print("Shutting down...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise backup solution for KVM VMs and Podman containers",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add audit logging middleware (Issue #9)
from backend.middleware.audit_middleware import AuditLoggingMiddleware
app.add_middleware(AuditLoggingMiddleware)

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(settings_api.router, prefix=f"{settings.API_V1_PREFIX}/settings", tags=["Settings"])
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Authentication"])
app.include_router(dashboard.router, prefix=f"{settings.API_V1_PREFIX}/dashboard", tags=["Dashboard"])
app.include_router(kvm.router, prefix=f"{settings.API_V1_PREFIX}/kvm", tags=["KVM"])
app.include_router(podman.router, prefix=f"{settings.API_V1_PREFIX}/podman", tags=["Podman"])
app.include_router(storage.router, prefix=f"{settings.API_V1_PREFIX}/storage", tags=["Storage"])
app.include_router(schedules.router, prefix=f"{settings.API_V1_PREFIX}/schedules", tags=["Schedules"])
app.include_router(backups.router, prefix=f"{settings.API_V1_PREFIX}/backups", tags=["Backups"])
app.include_router(jobs.router, prefix=f"{settings.API_V1_PREFIX}/jobs", tags=["Jobs"])
app.include_router(logs.router, prefix=f"{settings.API_V1_PREFIX}/logs", tags=["Logs"])
app.include_router(compliance.router, prefix=f"{settings.API_V1_PREFIX}/compliance", tags=["Compliance"])
app.include_router(audit.router, prefix=f"{settings.API_V1_PREFIX}/audit", tags=["Audit"])


@app.get("/")
async def root():
    """Root endpoint - redirects to setup or app."""
    from backend.models.base import AsyncSessionLocal
    from backend.models.user import User, UserRole
    from sqlalchemy import select

    # Check if admin user exists
    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.role == UserRole.ADMIN).limit(1)
        result = await db.execute(stmt)
        admin_exists = result.scalar_one_or_none() is not None

    if not admin_exists:
        return RedirectResponse(url="/setup")
    else:
        return RedirectResponse(url="/static/app.html")


@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    """Serve setup wizard page."""
    setup_file = Path(__file__).parent / "static" / "setup.html"
    if setup_file.exists():
        return HTMLResponse(content=setup_file.read_text())
    return HTMLResponse(content="<h1>Setup page not found</h1>", status_code=404)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/test-logging")
async def test_logging():
    """Test endpoint to verify logging is working."""
    import logging
    from backend.core.logging_handler import get_log_handler

    # Generate some test log messages
    logger = logging.getLogger("backend.test")
    logger.info("Test INFO message")
    logger.warning("Test WARNING message")
    logger.error("Test ERROR message")

    # Get log stats
    handler = get_log_handler()
    stats = handler.get_stats()
    recent_logs = handler.get_logs(limit=10)

    return {
        "stats": stats,
        "recent_logs": recent_logs,
        "handler_in_root": handler in logging.getLogger().handlers
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS if not settings.DEBUG else 1
    )
