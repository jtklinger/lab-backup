"""
Email notification service for backup verification results.

Sends detailed reports after backup verification completes, including:
- Verification status (passed/failed)
- Backup details (source, date, size)
- Verification metrics (table count, database size, duration)
- Error details if verification failed
- Next steps and recommendations
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)


class VerificationEmailService:
    """Service for sending backup verification email reports."""

    def __init__(self):
        """Initialize email service."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM
        self.smtp_tls = getattr(settings, 'SMTP_TLS', True)

    async def send_verification_report(
        self,
        backup_id: int,
        backup_name: str,
        source_name: str,
        backup_date: datetime,
        verification_success: bool,
        table_count: Optional[int] = None,
        size_bytes: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        error_message: Optional[str] = None,
        recipients: Optional[list[str]] = None
    ):
        """
        Send verification report email.

        Args:
            backup_id: Backup ID
            backup_name: Backup filename
            source_name: Name of backed up VM/container
            backup_date: When backup was created
            verification_success: Whether verification passed
            table_count: Number of tables verified
            size_bytes: Database size in bytes
            duration_seconds: Verification duration
            error_message: Error message if failed
            recipients: List of email addresses (defaults to SMTP_TO from settings)
        """
        if not self.smtp_host or not self.smtp_from:
            logger.warning("SMTP not configured - skipping verification email")
            return

        recipients = recipients or self._get_default_recipients()
        if not recipients:
            logger.warning("No email recipients configured - skipping verification email")
            return

        try:
            # Build email content
            subject = self._build_subject(verification_success, source_name)
            html_body = self._build_html_body(
                backup_id=backup_id,
                backup_name=backup_name,
                source_name=source_name,
                backup_date=backup_date,
                verification_success=verification_success,
                table_count=table_count,
                size_bytes=size_bytes,
                duration_seconds=duration_seconds,
                error_message=error_message
            )
            text_body = self._build_text_body(
                backup_id=backup_id,
                backup_name=backup_name,
                source_name=source_name,
                backup_date=backup_date,
                verification_success=verification_success,
                table_count=table_count,
                size_bytes=size_bytes,
                duration_seconds=duration_seconds,
                error_message=error_message
            )

            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_from
            msg['To'] = ', '.join(recipients)

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            await self._send_email(msg, recipients)

            logger.info(f"Verification report sent to {len(recipients)} recipient(s)")

        except Exception as e:
            logger.error(f"Failed to send verification email: {e}", exc_info=True)

    def _get_default_recipients(self) -> list[str]:
        """Get default email recipients from settings."""
        smtp_to = getattr(settings, 'SMTP_TO', None)
        if smtp_to:
            if isinstance(smtp_to, str):
                return [addr.strip() for addr in smtp_to.split(',')]
            elif isinstance(smtp_to, list):
                return smtp_to
        return []

    def _build_subject(self, success: bool, source_name: str) -> str:
        """Build email subject line."""
        status = "✓ PASSED" if success else "✗ FAILED"
        return f"Backup Verification {status}: {source_name}"

    def _build_html_body(
        self,
        backup_id: int,
        backup_name: str,
        source_name: str,
        backup_date: datetime,
        verification_success: bool,
        table_count: Optional[int],
        size_bytes: Optional[int],
        duration_seconds: Optional[int],
        error_message: Optional[str]
    ) -> str:
        """Build HTML email body."""
        status_color = "#4caf50" if verification_success else "#f44336"
        status_text = "PASSED" if verification_success else "FAILED"
        status_icon = "✓" if verification_success else "✗"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .info-table td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .info-table td:first-child {{ font-weight: bold; width: 40%; }}
        .metrics {{ background-color: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .error {{ background-color: #fff3cd; border-left: 4px solid #ff9800; padding: 15px; margin: 15px 0; }}
        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{status_icon} Backup Verification {status_text}</h1>
        </div>
        <div class="content">
            <h2>Verification Summary</h2>
            <table class="info-table">
                <tr>
                    <td>Source:</td>
                    <td>{source_name}</td>
                </tr>
                <tr>
                    <td>Backup ID:</td>
                    <td>#{backup_id}</td>
                </tr>
                <tr>
                    <td>Backup File:</td>
                    <td>{backup_name}</td>
                </tr>
                <tr>
                    <td>Backup Date:</td>
                    <td>{backup_date.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
                <tr>
                    <td>Verification Date:</td>
                    <td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
                <tr>
                    <td>Status:</td>
                    <td><strong style="color: {status_color}">{status_text}</strong></td>
                </tr>
            </table>
        """

        if verification_success:
            html += f"""
            <div class="metrics">
                <h3>Verification Metrics</h3>
                <table class="info-table">
                    <tr>
                        <td>Tables Verified:</td>
                        <td>{table_count or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td>Database Size:</td>
                        <td>{self._format_bytes(size_bytes) if size_bytes else 'N/A'}</td>
                    </tr>
                    <tr>
                        <td>Duration:</td>
                        <td>{duration_seconds or 'N/A'} seconds</td>
                    </tr>
                </table>
                <p><strong>Result:</strong> The backup was successfully restored to an isolated test environment
                and all integrity checks passed. This backup can be safely used for disaster recovery.</p>
            </div>
            """
        else:
            html += f"""
            <div class="error">
                <h3>⚠ Verification Failed</h3>
                <p><strong>Error:</strong></p>
                <pre>{error_message or 'Unknown error'}</pre>
                <p><strong>Action Required:</strong> Investigate the error above and consider creating a new backup.
                This backup may not be reliable for disaster recovery purposes.</p>
            </div>
            """

        html += """
            <div class="footer">
                <p>This is an automated message from Lab Backup System.<br>
                For more information, access the web interface or check the backup logs.</p>
            </div>
        </div>
    </div>
</body>
</html>
        """
        return html

    def _build_text_body(
        self,
        backup_id: int,
        backup_name: str,
        source_name: str,
        backup_date: datetime,
        verification_success: bool,
        table_count: Optional[int],
        size_bytes: Optional[int],
        duration_seconds: Optional[int],
        error_message: Optional[str]
    ) -> str:
        """Build plain text email body."""
        status = "PASSED" if verification_success else "FAILED"

        text = f"""
BACKUP VERIFICATION {status}
{'=' * 60}

Verification Summary
--------------------
Source:             {source_name}
Backup ID:          #{backup_id}
Backup File:        {backup_name}
Backup Date:        {backup_date.strftime('%Y-%m-%d %H:%M:%S UTC')}
Verification Date:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
Status:             {status}

"""

        if verification_success:
            text += f"""
Verification Metrics
--------------------
Tables Verified:    {table_count or 'N/A'}
Database Size:      {self._format_bytes(size_bytes) if size_bytes else 'N/A'}
Duration:           {duration_seconds or 'N/A'} seconds

Result: The backup was successfully restored to an isolated test environment
and all integrity checks passed. This backup can be safely used for
disaster recovery.
"""
        else:
            text += f"""
ERROR DETAILS
-------------
{error_message or 'Unknown error'}

ACTION REQUIRED: Investigate the error above and consider creating a
new backup. This backup may not be reliable for disaster recovery purposes.
"""

        text += """

---
This is an automated message from Lab Backup System.
For more information, access the web interface or check the backup logs.
"""
        return text

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

    async def _send_email(self, msg: MIMEMultipart, recipients: list[str]):
        """Send email via SMTP."""
        import asyncio

        def _send():
            """Blocking SMTP send operation."""
            if self.smtp_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)

            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)

            server.send_message(msg)
            server.quit()

        # Run blocking SMTP operation in thread pool
        await asyncio.get_event_loop().run_in_executor(None, _send)
