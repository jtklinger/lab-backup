# Multi-stage build for Lab Backup System

# Stage 1: Base image with Python and system dependencies
# Using Ubuntu 24.04 for newer libvirt packages
FROM ubuntu:24.04 as base

# Install Python 3.11 and system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
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

# Set python3.11 as default python and upgrade pip
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && python3 -m pip install --upgrade pip

WORKDIR /app

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Stage 2: Application
FROM base as app

# Copy application code
COPY backend /app/backend
COPY alembic.ini /app/
COPY database /app/database
COPY generate-env.py /app/
COPY .env.minimal /app/
COPY docker/entrypoint.sh /app/entrypoint.sh

# Create necessary directories
RUN mkdir -p /backups /var/log/lab-backup

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set Python path
ENV PYTHONPATH=/app

# Create non-root user (but we need root for migrations)
RUN useradd -m -u 1000 labbackup && \
    chown -R labbackup:labbackup /app /backups /var/log/lab-backup

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Use entrypoint for initialization
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (can be overridden)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
