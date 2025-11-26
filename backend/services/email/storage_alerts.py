"""
Email notification service for storage alerts.

Sends notifications when:
- Storage backend exceeds configured threshold
- Storage backend is nearly full (>95%)
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List

from backend.core.config import settings

logger = logging.getLogger(__name__)


class StorageAlertEmailService:
    """Service for sending storage alert emails."""

    def __init__(self):
        """Initialize email service."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM
        self.smtp_tls = getattr(settings, 'SMTP_TLS', True)

    async def send_storage_threshold_alert(
        self,
        backend_id: int,
        backend_name: str,
        backend_type: str,
        used_gb: float,
        capacity_gb: float,
        used_percent: float,
        threshold: int,
        recipients: Optional[List[str]] = None
    ):
        """
        Send alert when storage backend exceeds threshold.

        Args:
            backend_id: Storage backend ID
            backend_name: Storage backend name
            backend_type: Storage type (local, smb, s3, nfs)
            used_gb: Used storage in GB
            capacity_gb: Total capacity in GB
            used_percent: Percentage of capacity used
            threshold: Configured alert threshold percentage
            recipients: List of email addresses (defaults to SMTP_TO from settings)
        """
        if not self.smtp_host or not self.smtp_from:
            logger.warning("SMTP not configured - skipping storage threshold alert")
            return

        recipients = recipients or self._get_default_recipients()
        if not recipients:
            logger.warning("No email recipients configured - skipping storage threshold alert")
            return

        try:
            # Determine severity
            if used_percent >= 95:
                severity = "CRITICAL"
                icon = "🚨"
                priority = "1"
            elif used_percent >= 90:
                severity = "WARNING"
                icon = "⚠️"
                priority = "2"
            else:
                severity = "ALERT"
                icon = "⚠️"
                priority = "3"

            subject = f"{icon} STORAGE {severity}: '{backend_name}' at {used_percent:.1f}% capacity"

            html_body = self._build_threshold_alert_html(
                backend_id=backend_id,
                backend_name=backend_name,
                backend_type=backend_type,
                used_gb=used_gb,
                capacity_gb=capacity_gb,
                used_percent=used_percent,
                threshold=threshold,
                severity=severity
            )

            text_body = self._build_threshold_alert_text(
                backend_id=backend_id,
                backend_name=backend_name,
                backend_type=backend_type,
                used_gb=used_gb,
                capacity_gb=capacity_gb,
                used_percent=used_percent,
                threshold=threshold,
                severity=severity
            )

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_from
            msg['To'] = ', '.join(recipients)
            msg['X-Priority'] = priority

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            await self._send_email(msg, recipients)

            logger.info(f"Storage threshold alert sent for '{backend_name}' ({used_percent:.1f}%) to {len(recipients)} recipient(s)")

        except Exception as e:
            logger.error(f"Failed to send storage threshold alert: {e}", exc_info=True)

    def _get_default_recipients(self) -> List[str]:
        """Get default email recipients from settings."""
        smtp_to = getattr(settings, 'SMTP_TO', None)
        if smtp_to:
            if isinstance(smtp_to, str):
                return [addr.strip() for addr in smtp_to.split(',')]
            elif isinstance(smtp_to, list):
                return smtp_to
        return []

    def _build_threshold_alert_html(
        self,
        backend_id: int,
        backend_name: str,
        backend_type: str,
        used_gb: float,
        capacity_gb: float,
        used_percent: float,
        threshold: int,
        severity: str
    ) -> str:
        """Build HTML body for storage threshold alert."""
        available_gb = capacity_gb - used_gb

        # Choose color based on severity
        if severity == "CRITICAL":
            header_color = "#d32f2f"
            bar_color = "#d32f2f"
        elif severity == "WARNING":
            header_color = "#ff9800"
            bar_color = "#ff9800"
        else:
            header_color = "#2196f3"
            bar_color = "#2196f3"

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {header_color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
        .alert-box {{ background-color: #fff; border-left: 4px solid {header_color}; padding: 15px; margin: 15px 0; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .info-table td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        .info-table td:first-child {{ font-weight: bold; width: 40%; }}
        .progress-container {{ background-color: #e0e0e0; border-radius: 10px; height: 30px; overflow: hidden; margin: 15px 0; }}
        .progress-bar {{ background-color: {bar_color}; height: 100%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }}
        .action-box {{ background-color: #fff3e0; border-left: 4px solid #ff9800; padding: 15px; margin: 15px 0; }}
        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{'🚨' if severity == 'CRITICAL' else '⚠️'} Storage {severity}</h1>
            <p style="margin: 5px 0 0 0;">Threshold Exceeded</p>
        </div>
        <div class="content">
            <div class="alert-box">
                <h2 style="margin-top: 0; color: {header_color};">Storage Backend '{backend_name}' is running low on space</h2>
                <p>The storage backend has exceeded the configured alert threshold of <strong>{threshold}%</strong>.</p>
            </div>

            <h3>Storage Usage</h3>
            <div class="progress-container">
                <div class="progress-bar" style="width: {min(used_percent, 100):.1f}%">
                    {used_percent:.1f}%
                </div>
            </div>

            <table class="info-table">
                <tr>
                    <td>Backend Name:</td>
                    <td><strong>{backend_name}</strong></td>
                </tr>
                <tr>
                    <td>Backend ID:</td>
                    <td>#{backend_id}</td>
                </tr>
                <tr>
                    <td>Type:</td>
                    <td>{backend_type.upper()}</td>
                </tr>
                <tr>
                    <td>Used Storage:</td>
                    <td><strong>{used_gb:.2f} GB</strong></td>
                </tr>
                <tr>
                    <td>Total Capacity:</td>
                    <td>{capacity_gb:.2f} GB</td>
                </tr>
                <tr>
                    <td>Available:</td>
                    <td>{available_gb:.2f} GB</td>
                </tr>
                <tr>
                    <td>Usage Percentage:</td>
                    <td><strong style="color: {header_color};">{used_percent:.1f}%</strong></td>
                </tr>
                <tr>
                    <td>Alert Threshold:</td>
                    <td>{threshold}%</td>
                </tr>
                <tr>
                    <td>Alert Time:</td>
                    <td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
            </table>

            <div class="action-box">
                <h3 style="margin-top: 0;">⚠ Recommended Actions</h3>
                <ol>
                    <li><strong>Review Retention Policies:</strong> Consider adjusting retention policies to remove old backups</li>
                    <li><strong>Delete Old Backups:</strong> Manually delete backups that are no longer needed</li>
                    <li><strong>Expand Storage:</strong> Add more capacity to the storage backend if possible</li>
                    <li><strong>Add New Backend:</strong> Configure a new storage backend and migrate schedules</li>
                    <li><strong>Adjust Quotas:</strong> Review and adjust storage quota settings</li>
                </ol>
            </div>

            <div class="footer">
                <p>This is an automated storage alert from Lab Backup System.<br>
                For more information, access the web interface at <a href="http://localhost:8000/storage">http://localhost:8000/storage</a></p>
            </div>
        </div>
    </div>
</body>
</html>
        """

    def _build_threshold_alert_text(
        self,
        backend_id: int,
        backend_name: str,
        backend_type: str,
        used_gb: float,
        capacity_gb: float,
        used_percent: float,
        threshold: int,
        severity: str
    ) -> str:
        """Build plain text body for storage threshold alert."""
        available_gb = capacity_gb - used_gb
        icon = "🚨" if severity == "CRITICAL" else "⚠️"

        return f"""
{icon} STORAGE {severity} - THRESHOLD EXCEEDED
{'=' * 60}

Storage Backend '{backend_name}' is running low on space.
The storage backend has exceeded the configured alert threshold of {threshold}%.

STORAGE DETAILS
{'-' * 30}
Backend Name:      {backend_name}
Backend ID:        #{backend_id}
Type:              {backend_type.upper()}
Used Storage:      {used_gb:.2f} GB
Total Capacity:    {capacity_gb:.2f} GB
Available:         {available_gb:.2f} GB
Usage Percentage:  {used_percent:.1f}%
Alert Threshold:   {threshold}%
Alert Time:        {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

RECOMMENDED ACTIONS
{'-' * 30}
1. Review Retention Policies: Consider adjusting retention policies to remove old backups
2. Delete Old Backups: Manually delete backups that are no longer needed
3. Expand Storage: Add more capacity to the storage backend if possible
4. Add New Backend: Configure a new storage backend and migrate schedules
5. Adjust Quotas: Review and adjust storage quota settings

---
This is an automated storage alert from Lab Backup System.
For more information, access the web interface at http://localhost:8000/storage
"""

    async def _send_email(self, msg: MIMEMultipart, recipients: List[str]):
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
