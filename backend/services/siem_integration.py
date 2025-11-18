"""
SIEM integration service for exporting audit logs to external security systems.

Supports:
- Syslog export (RFC 5424 format)
- CEF (Common Event Format)
- Configurable syslog server (host, port, protocol)
- Real-time and batch export

Related: Issue #9 - Enhanced Audit Logging System
"""

import logging
import socket
import json
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field

from backend.models.user import AuditLog

logger = logging.getLogger(__name__)


class SyslogConfig(BaseModel):
    """Syslog server configuration."""
    enabled: bool = Field(default=False, description="Enable syslog export")
    host: str = Field(default="localhost", description="Syslog server hostname")
    port: int = Field(default=514, ge=1, le=65535, description="Syslog server port")
    protocol: Literal["udp", "tcp"] = Field(default="udp", description="Transport protocol")
    format: Literal["rfc5424", "cef"] = Field(default="rfc5424", description="Log format")
    facility: int = Field(default=16, ge=0, le=23, description="Syslog facility (16=local0)")
    app_name: str = Field(default="lab-backup", description="Application name in syslog")


class SIEMIntegration:
    """Service for exporting audit logs to SIEM systems."""

    # Syslog severity mapping
    SEVERITY_MAP = {
        "DEBUG": 7,      # Debug
        "INFO": 6,       # Informational
        "WARNING": 4,    # Warning
        "ERROR": 3,      # Error
        "CRITICAL": 2    # Critical
    }

    # CEF severity mapping (0-10)
    CEF_SEVERITY_MAP = {
        "DEBUG": 2,
        "INFO": 5,
        "WARNING": 7,
        "ERROR": 8,
        "CRITICAL": 10
    }

    def __init__(self, config: SyslogConfig):
        """
        Initialize SIEM integration.

        Args:
            config: Syslog server configuration
        """
        self.config = config

    def export_audit_log(self, audit_log: AuditLog) -> bool:
        """
        Export a single audit log entry to SIEM.

        Args:
            audit_log: Audit log entry to export

        Returns:
            True if export succeeded, False otherwise
        """
        if not self.config.enabled:
            return False

        try:
            if self.config.format == "rfc5424":
                message = self._format_rfc5424(audit_log)
            else:  # cef
                message = self._format_cef(audit_log)

            return self._send_syslog(message, audit_log.severity)

        except Exception as e:
            logger.error(f"Failed to export audit log to SIEM: {e}", exc_info=True)
            return False

    def _format_rfc5424(self, audit_log: AuditLog) -> str:
        """
        Format audit log as RFC 5424 syslog message.

        RFC 5424 Format:
        <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG

        Args:
            audit_log: Audit log entry

        Returns:
            Formatted syslog message
        """
        # Calculate priority: (facility * 8) + severity
        severity = self.SEVERITY_MAP.get(audit_log.severity or "INFO", 6)
        priority = (self.config.facility * 8) + severity

        # Format timestamp (ISO 8601 with timezone)
        timestamp = audit_log.created_at.isoformat() if audit_log.created_at else datetime.utcnow().isoformat()

        # Hostname (use IP address if available)
        hostname = audit_log.ip_address or "-"

        # App name
        app_name = self.config.app_name

        # Process ID (use user_id if available)
        procid = str(audit_log.user_id) if audit_log.user_id else "-"

        # Message ID (action)
        msgid = audit_log.action or "-"

        # Structured data (JSON fields)
        structured_data = self._build_structured_data(audit_log)

        # Message (human-readable summary)
        msg = self._build_message_summary(audit_log)

        # Assemble RFC 5424 message
        syslog_msg = (
            f"<{priority}>1 {timestamp} {hostname} {app_name} {procid} {msgid} "
            f"{structured_data} {msg}"
        )

        return syslog_msg

    def _format_cef(self, audit_log: AuditLog) -> str:
        """
        Format audit log as CEF (Common Event Format) message.

        CEF Format:
        CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension

        Args:
            audit_log: Audit log entry

        Returns:
            Formatted CEF message
        """
        # CEF header fields
        version = "0"
        vendor = "TowerBan"
        product = "Lab Backup System"
        device_version = "1.0"
        signature_id = audit_log.action or "UNKNOWN"
        name = self._get_event_name(audit_log)
        severity = self.CEF_SEVERITY_MAP.get(audit_log.severity or "INFO", 5)

        # CEF extension (key=value pairs)
        extensions = []

        if audit_log.user_id:
            extensions.append(f"suser={audit_log.user_id}")

        if audit_log.ip_address:
            extensions.append(f"src={audit_log.ip_address}")

        if audit_log.request_method:
            extensions.append(f"requestMethod={audit_log.request_method}")

        if audit_log.request_path:
            extensions.append(f"requestUrl={audit_log.request_path}")

        if audit_log.response_status:
            extensions.append(f"requestClientApplication={audit_log.response_status}")

        if audit_log.resource_type:
            extensions.append(f"deviceCustomString1Label=ResourceType")
            extensions.append(f"deviceCustomString1={audit_log.resource_type}")

        if audit_log.resource_id:
            extensions.append(f"deviceCustomNumber1Label=ResourceID")
            extensions.append(f"deviceCustomNumber1={audit_log.resource_id}")

        if audit_log.duration_ms:
            extensions.append(f"deviceCustomNumber2Label=DurationMS")
            extensions.append(f"deviceCustomNumber2={audit_log.duration_ms}")

        if audit_log.user_agent:
            # CEF requires escaping for certain characters
            user_agent_escaped = audit_log.user_agent.replace("\\", "\\\\").replace("=", "\\=")
            extensions.append(f"requestClientApplication={user_agent_escaped}")

        # Add timestamp
        if audit_log.created_at:
            # CEF uses milliseconds since epoch
            timestamp_ms = int(audit_log.created_at.timestamp() * 1000)
            extensions.append(f"rt={timestamp_ms}")

        extension_str = " ".join(extensions)

        # Assemble CEF message
        cef_msg = f"CEF:{version}|{vendor}|{product}|{device_version}|{signature_id}|{name}|{severity}|{extension_str}"

        return cef_msg

    def _build_structured_data(self, audit_log: AuditLog) -> str:
        """
        Build RFC 5424 structured data section.

        Format: [sd-id key="value" key="value"]

        Args:
            audit_log: Audit log entry

        Returns:
            Structured data string
        """
        sd_elements = []

        # Add audit metadata
        if audit_log.resource_type or audit_log.resource_id or audit_log.details:
            fields = []

            if audit_log.resource_type:
                fields.append(f'resourceType="{audit_log.resource_type}"')

            if audit_log.resource_id:
                fields.append(f'resourceId="{audit_log.resource_id}"')

            if audit_log.response_status:
                fields.append(f'httpStatus="{audit_log.response_status}"')

            if audit_log.duration_ms:
                fields.append(f'durationMs="{audit_log.duration_ms}"')

            if fields:
                sd_elements.append(f"[audit {' '.join(fields)}]")

        # Add request data if present
        if audit_log.request_method or audit_log.request_path:
            fields = []

            if audit_log.request_method:
                fields.append(f'method="{audit_log.request_method}"')

            if audit_log.request_path:
                # Escape quotes in path
                path_escaped = audit_log.request_path.replace('"', '\\"')
                fields.append(f'path="{path_escaped}"')

            if fields:
                sd_elements.append(f"[request {' '.join(fields)}]")

        return "".join(sd_elements) if sd_elements else "-"

    def _build_message_summary(self, audit_log: AuditLog) -> str:
        """
        Build human-readable message summary.

        Args:
            audit_log: Audit log entry

        Returns:
            Message summary
        """
        parts = [audit_log.action]

        if audit_log.resource_type:
            parts.append(f"on {audit_log.resource_type}")

        if audit_log.resource_id:
            parts.append(f"#{audit_log.resource_id}")

        if audit_log.user_id:
            parts.append(f"by user {audit_log.user_id}")

        if audit_log.ip_address:
            parts.append(f"from {audit_log.ip_address}")

        return " ".join(parts)

    def _get_event_name(self, audit_log: AuditLog) -> str:
        """
        Get human-readable event name for CEF.

        Args:
            audit_log: Audit log entry

        Returns:
            Event name
        """
        action = audit_log.action or "Unknown Event"

        # Convert action to readable name
        name_map = {
            "AUTH_LOGIN_SUCCESS": "User Login Success",
            "AUTH_LOGIN_FAILURE": "User Login Failure",
            "AUTH_LOGOUT_SUCCESS": "User Logout",
            "CONFIG_CREATE_USER": "User Account Created",
            "CONFIG_UPDATE_STORAGE": "Storage Backend Updated",
            "BACKUP_CREATE_SUCCESS": "Backup Created Successfully",
            "BACKUP_DELETE_SUCCESS": "Backup Deleted",
            "RESTORE_SUCCESS": "Restore Completed",
            "ENCRYPTION_GENERATE": "Encryption Key Generated",
            "ENCRYPTION_ROTATE": "Encryption Key Rotated"
        }

        return name_map.get(action, action.replace("_", " ").title())

    def _send_syslog(self, message: str, severity: Optional[str] = None) -> bool:
        """
        Send syslog message to configured server.

        Args:
            message: Formatted syslog message
            severity: Log severity level

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if self.config.protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.sendto(message.encode('utf-8'), (self.config.host, self.config.port))
                    logger.debug(f"Sent audit log to syslog via UDP: {self.config.host}:{self.config.port}")
                    return True
                finally:
                    sock.close()

            else:  # tcp
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.settimeout(5.0)  # 5 second timeout
                    sock.connect((self.config.host, self.config.port))
                    # TCP syslog requires message framing (length prefix or newline)
                    framed_message = f"{len(message)} {message}"
                    sock.sendall(framed_message.encode('utf-8'))
                    logger.debug(f"Sent audit log to syslog via TCP: {self.config.host}:{self.config.port}")
                    return True
                finally:
                    sock.close()

        except socket.timeout:
            logger.warning(f"Timeout sending syslog to {self.config.host}:{self.config.port}")
            return False
        except socket.error as e:
            logger.warning(f"Socket error sending syslog: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending syslog: {e}", exc_info=True)
            return False


# Global SIEM integration instance
_siem_integration: Optional[SIEMIntegration] = None


def get_siem_integration() -> Optional[SIEMIntegration]:
    """
    Get global SIEM integration instance.

    Returns:
        SIEM integration instance or None if not configured
    """
    return _siem_integration


def configure_siem_integration(config: SyslogConfig):
    """
    Configure global SIEM integration.

    Args:
        config: Syslog configuration
    """
    global _siem_integration

    if config.enabled:
        _siem_integration = SIEMIntegration(config)
        logger.info(
            f"SIEM integration enabled: {config.format.upper()} "
            f"to {config.host}:{config.port} via {config.protocol.upper()}"
        )
    else:
        _siem_integration = None
        logger.info("SIEM integration disabled")
