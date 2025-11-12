# Multi-stage build for Lab Backup System

# Stage 1: Base image with Python and system dependencies
# Using Ubuntu 24.04 for newer libvirt packages
FROM ubuntu:24.04 as base

# Install Python 3.12 and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    python3-pip \
    gcc \
    g++ \
    make \
    libpq-dev \
    libvirt-dev \
    libvirt0 \
    pkg-config \
    libguestfs-tools \
    qemu-utils \
    libyajl-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Stage 2: Application
FROM base as app

# Copy application code
COPY backend /app/backend
COPY alembic.ini /app/
COPY database /app/database
COPY generate-env.py /app/
COPY .env.minimal /app/
COPY docker/entrypoint.sh /app/entrypoint.sh
COPY docker/start-api.sh /app/start-api.sh
COPY docker/healthcheck.py /app/healthcheck.py

# Create necessary directories
RUN mkdir -p /backups /var/log/lab-backup /app/certs

# Make scripts executable
RUN chmod +x /app/entrypoint.sh /app/start-api.sh /app/healthcheck.py

# Set Python path
ENV PYTHONPATH=/app

# Create non-root user (but we need root for migrations)
RUN useradd -m labbackup && \
    chown -R labbackup:labbackup /app /backups /var/log/lab-backup

# Expose ports
EXPOSE 8000 8443

# Health check (supports both HTTP and HTTPS)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/healthcheck.py

# Use entrypoint for initialization
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (can be overridden)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
