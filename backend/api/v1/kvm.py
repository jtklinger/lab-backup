"""
KVM/libvirt API endpoints.
"""
import logging
import subprocess
import tempfile
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional, Generic, TypeVar

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.infrastructure import KVMHost, VM, SSHKey
from backend.core.security import get_current_user, require_role
from backend.core.config import settings
from backend.core.encryption import (
    encrypt_ssh_private_key,
    decrypt_ssh_private_key,
    encrypt_password,
    decrypt_password
)
from backend.services.kvm.backup import KVMBackupService

logger = logging.getLogger(__name__)

router = APIRouter()

# Generic paginated response
T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model."""
    items: List[T]
    total: int
    limit: int
    offset: int


class StorageCapabilities(BaseModel):
    """Storage capabilities for a KVM host."""
    supports_file: bool
    file_storage_path: Optional[str] = None
    supports_rbd: bool
    rbd_default_pool: Optional[str] = None


def compute_storage_capabilities(config: Optional[dict]) -> Optional[StorageCapabilities]:
    """
    Compute storage capabilities from KVM host config.

    Returns None if config is missing or has no storage configuration.
    """
    if not config or "storage" not in config:
        return None

    storage_config = config.get("storage", {})

    # Check for file storage
    supports_file = "file_storage_path" in storage_config
    file_storage_path = storage_config.get("file_storage_path")

    # Check for RBD storage
    supports_rbd = "rbd" in storage_config and storage_config["rbd"] is not None
    rbd_default_pool = None
    if supports_rbd:
        rbd_default_pool = storage_config["rbd"].get("default_pool")

    return StorageCapabilities(
        supports_file=supports_file,
        file_storage_path=file_storage_path,
        supports_rbd=supports_rbd,
        rbd_default_pool=rbd_default_pool
    )


class KVMHostCreate(BaseModel):
    """KVM host creation model."""
    name: str
    hostname: str  # Hostname or IP address
    port: int = 22  # SSH port
    username: str = "root"
    auth_type: str = "SSH_KEY"  # SSH_KEY or PASSWORD
    password: Optional[str] = None  # Plain text password for auth_type="PASSWORD"
    ssh_key_path: Optional[str] = None  # Path to SSH key (frontend compatibility)
    is_active: bool = True

    @property
    def uri(self) -> str:
        """Generate libvirt URI from hostname and username."""
        # For password auth, use qemu+tcp:// with SASL
        # For SSH key auth, use qemu+ssh://
        if self.auth_type.lower() == "password":
            # TCP connection for password/SASL authentication
            # Default libvirt TLS port is 16514, non-TLS is 16509
            # Using TLS port for security
            return f"qemu+tcp://{self.hostname}/system"
        else:
            # SSH connection for key-based authentication
            return f"qemu+ssh://{self.username}@{self.hostname}/system"


class KVMHostResponse(BaseModel):
    """KVM host response model."""
    id: int
    name: str
    hostname: str
    port: int
    username: str
    auth_type: str
    ssh_key_path: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_connection: Optional[datetime] = None
    storage_capabilities: Optional[StorageCapabilities] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_db_model(cls, host: "KVMHost", storage_caps: Optional[StorageCapabilities] = None):
        """Create response from database model, parsing URI back to hostname."""
        # Parse URI - can be qemu+ssh://user@host/system or qemu+tcp://host/system
        uri = host.uri
        hostname = uri
        username = host.username or "root"
        port = 22

        # Parse qemu+ssh://user@host/system format
        if "qemu+ssh://" in uri:
            uri_part = uri.replace("qemu+ssh://", "")
            if "@" in uri_part:
                user_host = uri_part.split("/")[0]
                username, hostname = user_host.split("@", 1)
            port = 22
        # Parse qemu+tcp://host/system format
        elif "qemu+tcp://" in uri:
            uri_part = uri.replace("qemu+tcp://", "")
            hostname = uri_part.split("/")[0]
            # TCP port is typically 16514 for TLS or 16509 for non-TLS
            port = 16514

        return cls(
            id=host.id,
            name=host.name,
            hostname=hostname,
            port=port,
            username=username,
            auth_type=host.auth_type.upper() if host.auth_type else "SSH_KEY",
            ssh_key_path=None,  # SSH keys are stored separately
            is_active=host.enabled,
            created_at=host.created_at,
            last_connection=None,  # TODO: track last connection time
            storage_capabilities=storage_caps
        )


class VMResponse(BaseModel):
    """VM response model."""
    id: int
    kvm_host_id: int
    name: str
    uuid: str
    vcpus: Optional[int]
    memory: Optional[int]
    disk_size: Optional[int]
    state: str

    class Config:
        from_attributes = True


class SSHKeyCreate(BaseModel):
    """SSH key upload model."""
    private_key: str
    public_key: str
    key_type: str  # rsa, ed25519, etc.


class SSHKeyGenerate(BaseModel):
    """SSH key generation model."""
    key_type: str = "ed25519"  # or rsa
    key_size: Optional[int] = None  # For RSA keys (2048, 4096, etc.)


class SSHKeyResponse(BaseModel):
    """SSH key response model (without private key)."""
    id: int
    kvm_host_id: int
    public_key: str
    key_type: str
    created_at: datetime
    last_used: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/hosts", response_model=List[KVMHostResponse])
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all KVM hosts with dynamically detected storage capabilities."""
    stmt = select(KVMHost)
    result = await db.execute(stmt)
    hosts = result.scalars().all()

    # Create KVM service instance
    kvm_service = KVMBackupService()

    # Query storage capabilities dynamically for each host
    response = []
    for host in hosts:
        # Try to query actual storage pools from the host
        storage_caps = None
        if host.enabled:
            try:
                # Setup authentication (SSH key or password) from database if available
                if host.auth_type == "password":
                    await kvm_service.setup_auth_for_host(db, host.id)
                else:
                    await kvm_service.setup_ssh_key_for_host(db, host.id, host.uri)

                # Query storage capabilities
                caps_dict = await kvm_service.list_storage_pools(host.uri)
                # Convert to StorageCapabilities model
                storage_caps = StorageCapabilities(**caps_dict)
            except Exception as e:
                # Log error but don't fail the entire request
                logger.warning(f"Failed to query storage for host {host.name}: {e}")
                # Fall back to static config if dynamic detection fails
                storage_caps = compute_storage_capabilities(host.config)

        response.append(KVMHostResponse.from_db_model(host, storage_caps))

    return response


@router.post("/hosts", response_model=KVMHostResponse, status_code=status.HTTP_201_CREATED)
async def create_host(
    host_data: KVMHostCreate,
    skip_connection_test: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new KVM host."""
    # Normalize auth_type (frontend sends "SSH_KEY" or "PASSWORD", backend uses lowercase)
    auth_type_normalized = host_data.auth_type.lower()

    # Skip connection test for password auth because libvirt doesn't support interactive password prompts
    # User can test connection manually after creation using the test endpoint
    # For SSH key auth, test connection if not explicitly skipped
    if not skip_connection_test and auth_type_normalized != "password":
        kvm_service = KVMBackupService()
        if not await kvm_service.test_connection(host_data.uri):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to connect to KVM host. Please verify SSH key authentication is configured."
            )

    # Encrypt password if provided
    password_encrypted = None
    if auth_type_normalized == "password" and host_data.password:
        try:
            password_encrypted = encrypt_password(
                host_data.password,
                settings.SECRET_KEY
            )
        except Exception as e:
            logger.error(f"Failed to encrypt password: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to encrypt password"
            )

    host = KVMHost(
        name=host_data.name,
        uri=host_data.uri,
        username=host_data.username,
        auth_type=auth_type_normalized,
        password_encrypted=password_encrypted,
        config={},
        enabled=host_data.is_active
    )

    db.add(host)
    await db.commit()
    await db.refresh(host)

    return KVMHostResponse.from_db_model(host)


@router.put("/hosts/{host_id}", response_model=KVMHostResponse)
async def update_host(
    host_id: int,
    host_data: KVMHostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Update a KVM host."""
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    # Normalize auth_type to lowercase
    auth_type_normalized = host_data.auth_type.lower() if host_data.auth_type else "ssh_key"

    # Test connection if URI or auth changed
    if host_data.uri != host.uri or auth_type_normalized != host.auth_type:
        kvm_service = KVMBackupService()

        # For password auth, test with the provided password
        if auth_type_normalized == "password" and host_data.password:
            if not await kvm_service.test_connection(
                host_data.uri,
                password=host_data.password,
                username=host_data.username
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to connect to KVM host with provided credentials"
                )
        else:
            if not await kvm_service.test_connection(host_data.uri):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to connect to KVM host"
                )

    # Update password if provided (or clear if switching away from password auth)
    if auth_type_normalized == "password" and host_data.password:
        try:
            host.password_encrypted = encrypt_password(
                host_data.password,
                settings.SECRET_KEY
            )
        except Exception as e:
            logger.error(f"Failed to encrypt password: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to encrypt password"
            )
    elif auth_type_normalized != "password":
        # Clear password if not using password auth
        host.password_encrypted = None

    # Update host fields
    host.name = host_data.name
    host.uri = host_data.uri
    host.username = host_data.username
    host.auth_type = auth_type_normalized
    host.enabled = host_data.is_active

    await db.commit()
    await db.refresh(host)

    return KVMHostResponse.from_db_model(host)


@router.delete("/hosts/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Delete a KVM host and all associated VMs."""
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    await db.delete(host)
    await db.commit()

    logger.info(f"KVM host deleted: {host.name} (ID: {host_id})")

    return None


@router.post("/hosts/{host_id}/test")
async def test_host_connection(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test connection to a KVM host."""
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    kvm_service = KVMBackupService()

    try:
        # Setup authentication based on auth type
        if host.auth_type == "password":
            # Password auth uses qemu+tcp:// with SASL authentication
            from backend.core.encryption import decrypt_password
            if host.password_encrypted:
                try:
                    password = decrypt_password(host.password_encrypted, settings.SECRET_KEY)
                    # Test TCP connection with SASL/password authentication
                    logger.info(f"Testing qemu+tcp:// connection to {host.name} with password auth")
                    success = await kvm_service.test_connection(
                        host.uri,
                        password=password,
                        username=host.username
                    )
                    if not success:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Failed to connect to {host.name} via qemu+tcp://. Please verify: 1) libvirtd TCP listener is enabled on port 16514, 2) SASL authentication is configured, 3) Username and password are correct."
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Failed to test TCP connection for host {host.name}: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Connection failed: {str(e)}. Ensure libvirtd is configured for TCP connections with SASL authentication."
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No password stored for this host"
                )
        else:
            # For SSH key auth, setup key and test
            await kvm_service.setup_ssh_key_for_host(db, host.id, host.uri)
            success = await kvm_service.test_connection(host.uri)

        if success:
            return {"status": "success", "message": f"Successfully connected to {host.name}"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to connect to {host.name}. Please verify credentials and network connectivity."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing connection to host {host.name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


@router.get("/vms", response_model=PaginatedResponse[VMResponse])
async def list_all_vms(
    host_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all VMs across all KVM hosts, optionally filtered by host_id."""
    # Build base query
    stmt = select(VM)
    if host_id:
        stmt = stmt.where(VM.kvm_host_id == host_id)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Get paginated items
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/hosts/{host_id}/vms", response_model=List[VMResponse])
async def list_vms(
    host_id: int,
    sync: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List VMs on a KVM host."""
    # Get host
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    if sync:
        # Sync VMs from libvirt
        kvm_service = KVMBackupService()

        # Setup authentication (SSH key or password) from database if available
        if host.auth_type == "password":
            await kvm_service.setup_auth_for_host(db, host.id)
        else:
            await kvm_service.setup_ssh_key_for_host(db, host.id, host.uri)

        # List VMs from the host
        vms_data = await kvm_service.list_vms(host.uri)

        # Update database
        for vm_data in vms_data:
            stmt = select(VM).where(VM.uuid == vm_data["uuid"])
            result = await db.execute(stmt)
            vm = result.scalar_one_or_none()

            if vm:
                # Update existing
                vm.name = vm_data["name"]
                vm.state = vm_data["state"]
                vm.vcpus = vm_data["vcpus"]
                vm.memory = vm_data["memory"]
            else:
                # Create new
                vm = VM(
                    kvm_host_id=host.id,
                    name=vm_data["name"],
                    uuid=vm_data["uuid"],
                    vcpus=vm_data["vcpus"],
                    memory=vm_data["memory"],
                    state=vm_data["state"]
                )
                db.add(vm)

        await db.commit()

    # Return VMs from database
    stmt = select(VM).where(VM.kvm_host_id == host_id)
    result = await db.execute(stmt)
    vms = result.scalars().all()

    return vms


@router.post("/hosts/{host_id}/refresh")
async def refresh_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh VMs from KVM host by syncing with libvirt."""
    # Get host
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    # Sync VMs from libvirt
    kvm_service = KVMBackupService()
    try:
        # Setup authentication (SSH key or password) from database if available
        if host.auth_type == "password":
            await kvm_service.setup_auth_for_host(db, host.id)
        else:
            await kvm_service.setup_ssh_key_for_host(db, host.id, host.uri)

        # List VMs from the host
        vms_data = await kvm_service.list_vms(host.uri)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to KVM host: {str(e)}"
        )

    # Update database
    synced_count = 0
    for vm_data in vms_data:
        stmt = select(VM).where(VM.uuid == vm_data["uuid"])
        result = await db.execute(stmt)
        vm = result.scalar_one_or_none()

        if vm:
            # Update existing
            vm.name = vm_data["name"]
            vm.state = vm_data["state"]
            vm.vcpus = vm_data["vcpus"]
            vm.memory = vm_data["memory"]
        else:
            # Create new
            vm = VM(
                kvm_host_id=host.id,
                name=vm_data["name"],
                uuid=vm_data["uuid"],
                vcpus=vm_data["vcpus"],
                memory=vm_data["memory"],
                state=vm_data["state"]
            )
            db.add(vm)
        synced_count += 1

    await db.commit()

    return {
        "message": f"Successfully synced {synced_count} VMs from {host.name}",
        "count": synced_count
    }


@router.get("/vms/{vm_id}", response_model=VMResponse)
async def get_vm(
    vm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get VM details."""
    vm = await db.get(VM, vm_id)
    if not vm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VM not found"
        )
    return vm


# SSH Key Management Endpoints

@router.post("/hosts/{host_id}/ssh-keys", response_model=SSHKeyResponse, status_code=status.HTTP_201_CREATED)
async def upload_ssh_key(
    host_id: int,
    key_data: SSHKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Upload an existing SSH private key for a KVM host."""
    # Verify host exists
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    # Encrypt the private key
    try:
        encrypted_private_key = encrypt_ssh_private_key(
            key_data.private_key,
            settings.SECRET_KEY
        )
    except Exception as e:
        logger.error(f"Failed to encrypt SSH private key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt SSH private key"
        )

    # Create SSH key record
    ssh_key = SSHKey(
        kvm_host_id=host_id,
        private_key_encrypted=encrypted_private_key,
        public_key=key_data.public_key,
        key_type=key_data.key_type
    )

    db.add(ssh_key)
    await db.commit()
    await db.refresh(ssh_key)

    logger.info(f"SSH key uploaded for KVM host {host.name} (ID: {host_id})")

    return ssh_key


@router.post("/hosts/{host_id}/ssh-keys/generate", response_model=SSHKeyResponse, status_code=status.HTTP_201_CREATED)
async def generate_ssh_key(
    host_id: int,
    key_params: SSHKeyGenerate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Generate a new SSH key pair for a KVM host."""
    # Verify host exists
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    # Generate SSH key pair using ssh-keygen
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/id_{key_params.key_type}"

            # Build ssh-keygen command
            cmd = ["ssh-keygen", "-t", key_params.key_type, "-f", key_path, "-N", ""]

            # Add key size for RSA
            if key_params.key_type == "rsa" and key_params.key_size:
                cmd.extend(["-b", str(key_params.key_size)])

            # Generate key
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"ssh-keygen failed: {result.stderr}")

            # Read generated keys
            with open(key_path, 'r') as f:
                private_key = f.read()
            with open(f"{key_path}.pub", 'r') as f:
                public_key = f.read()

    except Exception as e:
        logger.error(f"Failed to generate SSH key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate SSH key: {str(e)}"
        )

    # Encrypt the private key
    try:
        encrypted_private_key = encrypt_ssh_private_key(
            private_key,
            settings.SECRET_KEY
        )
    except Exception as e:
        logger.error(f"Failed to encrypt SSH private key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt SSH private key"
        )

    # Create SSH key record
    ssh_key = SSHKey(
        kvm_host_id=host_id,
        private_key_encrypted=encrypted_private_key,
        public_key=public_key.strip(),
        key_type=key_params.key_type
    )

    db.add(ssh_key)
    await db.commit()
    await db.refresh(ssh_key)

    logger.info(f"SSH key generated for KVM host {host.name} (ID: {host_id})")

    return ssh_key


@router.get("/hosts/{host_id}/ssh-keys", response_model=List[SSHKeyResponse])
async def list_ssh_keys(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all SSH keys for a KVM host."""
    # Verify host exists
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    # Get SSH keys
    stmt = select(SSHKey).where(SSHKey.kvm_host_id == host_id)
    result = await db.execute(stmt)
    ssh_keys = result.scalars().all()

    return ssh_keys


@router.delete("/hosts/{host_id}/ssh-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ssh_key(
    host_id: int,
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Delete an SSH key."""
    # Get the SSH key
    ssh_key = await db.get(SSHKey, key_id)
    if not ssh_key or ssh_key.kvm_host_id != host_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSH key not found"
        )

    await db.delete(ssh_key)
    await db.commit()

    logger.info(f"SSH key deleted (ID: {key_id}) for KVM host (ID: {host_id})")

    return None


@router.get("/hosts/{host_id}/ssh-keys/{key_id}/public")
async def get_public_key(
    host_id: int,
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the public key for installation on the target host."""
    # Get the SSH key
    ssh_key = await db.get(SSHKey, key_id)
    if not ssh_key or ssh_key.kvm_host_id != host_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSH key not found"
        )

    return {
        "public_key": ssh_key.public_key,
        "key_type": ssh_key.key_type,
        "instructions": f"Add this public key to ~/.ssh/authorized_keys on the target host"
    }
