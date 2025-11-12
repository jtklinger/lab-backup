"""
Main FastAPI application.
"""
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from contextlib import asynccontextmanager
from pathlib import Path

from backend.core.config import settings
from backend.api.v1 import auth, kvm, podman, storage, schedules, backups, jobs, settings as settings_api

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
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

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(settings_api.router, prefix=f"{settings.API_V1_PREFIX}/settings", tags=["Settings"])
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Authentication"])
app.include_router(kvm.router, prefix=f"{settings.API_V1_PREFIX}/kvm", tags=["KVM"])
app.include_router(podman.router, prefix=f"{settings.API_V1_PREFIX}/podman", tags=["Podman"])
app.include_router(storage.router, prefix=f"{settings.API_V1_PREFIX}/storage", tags=["Storage"])
app.include_router(schedules.router, prefix=f"{settings.API_V1_PREFIX}/schedules", tags=["Schedules"])
app.include_router(backups.router, prefix=f"{settings.API_V1_PREFIX}/backups", tags=["Backups"])
app.include_router(jobs.router, prefix=f"{settings.API_V1_PREFIX}/jobs", tags=["Jobs"])


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS if not settings.DEBUG else 1
    )
