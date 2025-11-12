"""
SSL/TLS certificate management for secure HTTPS connections.

Supports:
- Self-signed certificate generation for development/internal use
- Custom certificate configuration
- Certificate validation and renewal checks
"""
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CertificateManager:
    """Manages SSL/TLS certificates for the application."""

    def __init__(self, cert_dir: str = "/app/certs"):
        """
        Initialize certificate manager.

        Args:
            cert_dir: Directory to store certificates
        """
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)

        self.cert_file = self.cert_dir / "server.crt"
        self.key_file = self.cert_dir / "server.key"
        self.ca_file = self.cert_dir / "ca.crt"  # For Let's Encrypt chain

    def generate_self_signed_cert(
        self,
        hostname: str = "localhost",
        days_valid: int = 365,
        organization: str = "Lab Backup System",
        force: bool = False
    ) -> Tuple[Path, Path]:
        """
        Generate a self-signed SSL certificate.

        Args:
            hostname: Common name for the certificate
            days_valid: Number of days the certificate is valid
            organization: Organization name in certificate
            force: Force regeneration even if certificate exists

        Returns:
            Tuple of (cert_path, key_path)
        """
        if not force and self.cert_file.exists() and self.key_file.exists():
            logger.info(f"Self-signed certificate already exists at {self.cert_file}")
            return self.cert_file, self.key_file

        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID, ExtensionOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
            import ipaddress

            logger.info(f"Generating self-signed certificate for {hostname}")

            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # Build subject and issuer (same for self-signed)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "State"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "City"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ])

            # Build Subject Alternative Names (SANs)
            san_list = [x509.DNSName(hostname)]

            # Add localhost variations
            if hostname != "localhost":
                san_list.extend([
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                ])

            # Add IP address SANs
            try:
                san_list.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))
                san_list.append(x509.IPAddress(ipaddress.IPv6Address("::1")))

                # Try to add the hostname as IP if it's a valid IP
                try:
                    if ":" in hostname:
                        san_list.append(x509.IPAddress(ipaddress.IPv6Address(hostname)))
                    else:
                        san_list.append(x509.IPAddress(ipaddress.IPv4Address(hostname)))
                except ValueError:
                    pass  # hostname is not an IP address

            except Exception as e:
                logger.warning(f"Failed to add IP SANs: {e}")

            # Create certificate
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
                .add_extension(
                    x509.SubjectAlternativeName(san_list),
                    critical=False,
                )
                .add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True,
                )
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_encipherment=True,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .add_extension(
                    x509.ExtendedKeyUsage([
                        x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    ]),
                    critical=True,
                )
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            # Write private key
            with open(self.key_file, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))

            # Set proper permissions on key file
            os.chmod(self.key_file, 0o600)

            # Write certificate
            with open(self.cert_file, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

            logger.info(f"✅ Self-signed certificate generated successfully")
            logger.info(f"   Certificate: {self.cert_file}")
            logger.info(f"   Private Key: {self.key_file}")
            logger.info(f"   Valid for: {days_valid} days")
            logger.info(f"   Hostname: {hostname}")

            return self.cert_file, self.key_file

        except ImportError:
            logger.error("cryptography package not installed. Cannot generate certificates.")
            logger.error("Install with: pip install cryptography")
            raise
        except Exception as e:
            logger.error(f"Failed to generate self-signed certificate: {e}")
            raise

    def validate_certificate(self, cert_path: Optional[Path] = None) -> dict:
        """
        Validate an SSL certificate and return its details.

        Args:
            cert_path: Path to certificate file (default: self.cert_file)

        Returns:
            Dictionary with certificate details
        """
        cert_path = cert_path or self.cert_file

        if not cert_path.exists():
            return {
                "valid": False,
                "error": "Certificate file not found"
            }

        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend

            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read(), default_backend())

            now = datetime.utcnow()
            is_valid = cert.not_valid_before <= now <= cert.not_valid_after
            days_until_expiry = (cert.not_valid_after - now).days

            # Extract subject information
            subject_attrs = {}
            for attr in cert.subject:
                subject_attrs[attr.oid._name] = attr.value

            # Extract SANs
            san_list = []
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                san_list = [str(name) for name in san_ext.value]
            except x509.ExtensionNotFound:
                pass

            return {
                "valid": is_valid,
                "subject": subject_attrs,
                "issuer": {attr.oid._name: attr.value for attr in cert.issuer},
                "not_before": cert.not_valid_before.isoformat(),
                "not_after": cert.not_valid_after.isoformat(),
                "days_until_expiry": days_until_expiry,
                "expired": days_until_expiry < 0,
                "expires_soon": 0 < days_until_expiry < 30,
                "serial_number": cert.serial_number,
                "san": san_list,
                "self_signed": cert.issuer == cert.subject,
            }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }

    def get_certificate_paths(self) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Get paths to certificate and key files if they exist.

        Returns:
            Tuple of (cert_path, key_path) or (None, None) if not found
        """
        if self.cert_file.exists() and self.key_file.exists():
            return self.cert_file, self.key_file
        return None, None

    def setup_certificates(
        self,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        hostname: str = "localhost",
        auto_generate: bool = True
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Set up SSL certificates for the application.

        If custom cert/key paths are provided, use those.
        Otherwise, check for existing certificates or auto-generate if enabled.

        Args:
            cert_path: Path to custom certificate file
            key_path: Path to custom private key file
            hostname: Hostname for certificate generation
            auto_generate: Auto-generate self-signed cert if none exists

        Returns:
            Tuple of (cert_path, key_path) or (None, None) if SSL disabled
        """
        # Use custom certificates if provided
        if cert_path and key_path:
            custom_cert = Path(cert_path)
            custom_key = Path(key_path)

            if custom_cert.exists() and custom_key.exists():
                logger.info(f"Using custom SSL certificate: {custom_cert}")
                return custom_cert, custom_key
            else:
                logger.error(f"Custom certificate or key not found")
                raise FileNotFoundError(
                    f"Certificate or key file not found: {cert_path}, {key_path}"
                )

        # Check for existing certificates
        existing_cert, existing_key = self.get_certificate_paths()
        if existing_cert and existing_key:
            # Validate existing certificate
            cert_info = self.validate_certificate(existing_cert)

            if cert_info.get("valid"):
                if cert_info.get("expires_soon"):
                    logger.warning(
                        f"⚠️  Certificate expires in {cert_info['days_until_expiry']} days"
                    )
                logger.info(f"Using existing SSL certificate: {existing_cert}")
                return existing_cert, existing_key
            elif cert_info.get("expired"):
                logger.warning("Existing certificate has expired, generating new one")
            else:
                logger.warning(f"Invalid certificate: {cert_info.get('error')}")

        # Auto-generate self-signed certificate if enabled
        if auto_generate:
            logger.info("Auto-generating self-signed SSL certificate")
            return self.generate_self_signed_cert(hostname=hostname)

        # No certificates available
        logger.warning("No SSL certificates configured")
        return None, None
