"""
S3-compatible storage backend (AWS S3, Backblaze B2, MinIO, etc.).
"""
import asyncio
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, BinaryIO
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import aiofiles

from backend.services.storage.base import (
    StorageBackend,
    StorageError,
    StorageConnectionError,
    StorageUploadError,
    StorageDownloadError,
    StorageNotFoundError
)


class S3Storage(StorageBackend):
    """S3-compatible storage backend."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize S3 storage.

        Config format:
        {
            "endpoint_url": "https://s3.us-west-002.backblazeb2.com",  # Optional for AWS S3
            "aws_access_key_id": "key_id",
            "aws_secret_access_key": "secret_key",
            "bucket_name": "my-backups",
            "region": "us-west-002",
            "prefix": "lab-backup/",  # Optional prefix for all objects
            "storage_class": "STANDARD",  # or GLACIER, etc.
            "server_side_encryption": "AES256"  # Optional
        }
        """
        super().__init__(config)
        self.bucket_name = config["bucket_name"]
        self.prefix = config.get("prefix", "")
        self.storage_class = config.get("storage_class", "STANDARD")
        self.server_side_encryption = config.get("server_side_encryption")

        # Initialize boto3 client
        session_config = {
            "aws_access_key_id": config["aws_access_key_id"],
            "aws_secret_access_key": config["aws_secret_access_key"],
            "region_name": config.get("region")
        }

        if "endpoint_url" in config:
            session_config["endpoint_url"] = config["endpoint_url"]

        self.session = boto3.session.Session()
        self.client = self.session.client('s3', **session_config)
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _get_object_key(self, path: str) -> str:
        """Get full S3 object key with prefix."""
        return f"{self.prefix}{path}".lstrip("/")

    async def _run_in_executor(self, func, *args):
        """Run blocking boto3 call in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    async def upload(
        self,
        source_path: Path,
        destination_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload a file to S3."""
        try:
            object_key = self._get_object_key(destination_path)

            # Calculate checksum
            hasher = hashlib.sha256()
            size = 0
            async with aiofiles.open(source_path, 'rb') as f:
                while chunk := await f.read(8192):
                    hasher.update(chunk)
                    size += len(chunk)

            checksum = hasher.hexdigest()

            # Upload file
            extra_args = {
                "StorageClass": self.storage_class,
                "Metadata": metadata or {}
            }

            if self.server_side_encryption:
                extra_args["ServerSideEncryption"] = self.server_side_encryption

            await self._run_in_executor(
                lambda: self.client.upload_file(
                    str(source_path),
                    self.bucket_name,
                    object_key,
                    ExtraArgs=extra_args
                )
            )

            return {
                "path": object_key,
                "size": size,
                "checksum": checksum
            }

        except ClientError as e:
            self.logger.error(f"Failed to upload file to S3: {e}")
            raise StorageUploadError(f"Upload failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error uploading to S3: {e}")
            raise StorageUploadError(f"Upload failed: {e}")

    async def upload_stream(
        self,
        stream: BinaryIO,
        destination_path: str,
        size: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload a file stream to S3."""
        try:
            object_key = self._get_object_key(destination_path)

            # Calculate checksum
            hasher = hashlib.sha256()
            data = stream.read()
            hasher.update(data)
            checksum = hasher.hexdigest()

            # Upload
            extra_args = {
                "StorageClass": self.storage_class,
                "Metadata": metadata or {}
            }

            if self.server_side_encryption:
                extra_args["ServerSideEncryption"] = self.server_side_encryption

            await self._run_in_executor(
                lambda: self.client.put_object(
                    Bucket=self.bucket_name,
                    Key=object_key,
                    Body=data,
                    **extra_args
                )
            )

            return {
                "path": object_key,
                "size": len(data),
                "checksum": checksum
            }

        except ClientError as e:
            self.logger.error(f"Failed to upload stream to S3: {e}")
            raise StorageUploadError(f"Upload failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error uploading stream to S3: {e}")
            raise StorageUploadError(f"Upload failed: {e}")

    async def download(
        self,
        source_path: str,
        destination_path: Path
    ) -> Dict[str, Any]:
        """Download a file from S3."""
        try:
            object_key = self._get_object_key(source_path)

            # Create parent directory
            destination_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            await self._run_in_executor(
                lambda: self.client.download_file(
                    self.bucket_name,
                    object_key,
                    str(destination_path)
                )
            )

            # Calculate checksum and size
            hasher = hashlib.sha256()
            size = 0
            async with aiofiles.open(destination_path, 'rb') as f:
                while chunk := await f.read(8192):
                    hasher.update(chunk)
                    size += len(chunk)

            return {
                "path": str(destination_path),
                "size": size,
                "checksum": hasher.hexdigest()
            }

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise StorageNotFoundError(f"File not found: {source_path}")
            self.logger.error(f"Failed to download file from S3: {e}")
            raise StorageDownloadError(f"Download failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error downloading from S3: {e}")
            raise StorageDownloadError(f"Download failed: {e}")

    async def download_stream(self, source_path: str) -> BinaryIO:
        """Download a file from S3 as a stream."""
        try:
            object_key = self._get_object_key(source_path)

            response = await self._run_in_executor(
                lambda: self.client.get_object(
                    Bucket=self.bucket_name,
                    Key=object_key
                )
            )

            return response['Body']

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise StorageNotFoundError(f"File not found: {source_path}")
            self.logger.error(f"Failed to download stream from S3: {e}")
            raise StorageDownloadError(f"Download failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error downloading stream from S3: {e}")
            raise StorageDownloadError(f"Download failed: {e}")

    async def delete(self, path: str) -> bool:
        """Delete a file from S3."""
        try:
            object_key = self._get_object_key(path)

            await self._run_in_executor(
                lambda: self.client.delete_object(
                    Bucket=self.bucket_name,
                    Key=object_key
                )
            )

            return True

        except ClientError as e:
            self.logger.error(f"Failed to delete file from S3: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error deleting from S3: {e}")
            return False

    async def list(
        self,
        prefix: str = "",
        recursive: bool = False
    ) -> list[Dict[str, Any]]:
        """List files in S3."""
        try:
            object_prefix = self._get_object_key(prefix)
            files = []

            # List objects
            paginator = self.client.get_paginator('list_objects_v2')
            pages = await self._run_in_executor(
                lambda: list(paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=object_prefix,
                    Delimiter="" if recursive else "/"
                ))
            )

            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Remove prefix from key
                        rel_key = obj['Key']
                        if rel_key.startswith(self.prefix):
                            rel_key = rel_key[len(self.prefix):]

                        files.append({
                            "path": rel_key,
                            "size": obj['Size'],
                            "modified": obj['LastModified'].timestamp()
                        })

            return files

        except ClientError as e:
            self.logger.error(f"Failed to list files in S3: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error listing S3 files: {e}")
            return []

    async def exists(self, path: str) -> bool:
        """Check if a file exists in S3."""
        try:
            object_key = self._get_object_key(path)

            await self._run_in_executor(
                lambda: self.client.head_object(
                    Bucket=self.bucket_name,
                    Key=object_key
                )
            )

            return True

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            self.logger.error(f"Error checking S3 object existence: {e}")
            return False
        except Exception:
            return False

    async def get_usage(self) -> Dict[str, int]:
        """Get storage usage statistics."""
        try:
            # Calculate total size of objects with our prefix
            total_size = 0
            paginator = self.client.get_paginator('list_objects_v2')
            pages = await self._run_in_executor(
                lambda: list(paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=self.prefix
                ))
            )

            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        total_size += obj['Size']

            # Note: S3 doesn't have a "capacity" concept, so we return 0
            return {
                "used": total_size,
                "capacity": 0,
                "available": 0
            }

        except Exception as e:
            self.logger.error(f"Failed to get S3 usage: {e}")
            return {"used": 0, "capacity": 0, "available": 0}

    async def test_connection(self) -> bool:
        """Test connection to S3."""
        try:
            # Try to head the bucket
            await self._run_in_executor(
                lambda: self.client.head_bucket(Bucket=self.bucket_name)
            )
            return True

        except (ClientError, NoCredentialsError) as e:
            self.logger.error(f"S3 connection test failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error testing S3 connection: {e}")
            return False
