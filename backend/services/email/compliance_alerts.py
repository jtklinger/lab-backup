"""
Email notification service for compliance alerts.

Sends notifications when:
- VMs/containers transition to RED (non-compliant) status
- Daily compliance summary report
- Weekly compliance trends

Related: Issue #8 - Build Compliance Tracking System
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.core.config import settings

logger = logging.getLogger(__name__)


class ComplianceEmailService:
    """Service for sending compliance email alerts."""

    def __init__(self):
        """Initialize email service."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM
        self.smtp_tls = getattr(settings, 'SMTP_TLS', True)

    async def send_red_status_alert(
        self,
        entity_type: str,  # "VM" or "Container"
        entity_id: int,
        entity_name: str,
        compliance_reason: str,
        last_successful_backup: Optional[datetime] = None,
        recipients: Optional[List[str]] = None
    ):
        """
        Send alert when entity transitions to RED status.

        Args:
            entity_type: Type of entity (VM or Container)
            entity_id: Entity ID
            entity_name: Entity name
            compliance_reason: Why entity is non-compliant
            last_successful_backup: Timestamp of last successful backup
            recipients: List of email addresses (defaults to SMTP_TO from settings)
        """
        if not self.smtp_host or not self.smtp_from:
            logger.warning("SMTP not configured - skipping compliance alert")
            return

        recipients = recipients or self._get_default_recipients()
        if not recipients:
            logger.warning("No email recipients configured - skipping compliance alert")
            return

        try:
            subject = f"🚨 COMPLIANCE ALERT: {entity_type} '{entity_name}' is NON-COMPLIANT"

            html_body = self._build_red_alert_html(
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                compliance_reason=compliance_reason,
                last_successful_backup=last_successful_backup
            )

            text_body = self._build_red_alert_text(
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                compliance_reason=compliance_reason,
                last_successful_backup=last_successful_backup
            )

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_from
            msg['To'] = ', '.join(recipients)
            msg['X-Priority'] = '1'  # High priority

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            await self._send_email(msg, recipients)

            logger.info(f"RED status alert sent for {entity_type} '{entity_name}' to {len(recipients)} recipient(s)")

        except Exception as e:
            logger.error(f"Failed to send compliance alert email: {e}", exc_info=True)

    async def send_daily_compliance_summary(
        self,
        dashboard_data: Dict[str, Any],
        non_compliant_entities: Dict[str, List[Dict[str, Any]]],
        recipients: Optional[List[str]] = None
    ):
        """
        Send daily compliance summary report.

        Args:
            dashboard_data: Dashboard data from ComplianceService.get_compliance_dashboard()
            non_compliant_entities: Non-compliant entities from ComplianceService.get_non_compliant_entities()
            recipients: List of email addresses (defaults to SMTP_TO from settings)
        """
        if not self.smtp_host or not self.smtp_from:
            logger.warning("SMTP not configured - skipping daily compliance summary")
            return

        recipients = recipients or self._get_default_recipients()
        if not recipients:
            logger.warning("No email recipients configured - skipping daily compliance summary")
            return

        try:
            # Calculate summary metrics
            total_vms = dashboard_data['vms']['total']
            total_containers = dashboard_data['containers']['total']
            red_vms = dashboard_data['vms']['red']
            red_containers = dashboard_data['containers']['red']
            yellow_vms = dashboard_data['vms']['yellow']
            yellow_containers = dashboard_data['containers']['yellow']

            total_red = red_vms + red_containers
            total_yellow = yellow_vms + yellow_containers

            # Determine alert level for subject line
            if total_red > 0:
                alert_icon = "🚨"
                alert_level = "CRITICAL"
            elif total_yellow > 0:
                alert_icon = "⚠️"
                alert_level = "WARNING"
            else:
                alert_icon = "✓"
                alert_level = "HEALTHY"

            subject = f"{alert_icon} Daily Compliance Report - {alert_level}"

            html_body = self._build_daily_summary_html(
                dashboard_data=dashboard_data,
                non_compliant_entities=non_compliant_entities
            )

            text_body = self._build_daily_summary_text(
                dashboard_data=dashboard_data,
                non_compliant_entities=non_compliant_entities
            )

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_from
            msg['To'] = ', '.join(recipients)

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            await self._send_email(msg, recipients)

            logger.info(f"Daily compliance summary sent to {len(recipients)} recipient(s)")

        except Exception as e:
            logger.error(f"Failed to send daily compliance summary: {e}", exc_info=True)

    def _get_default_recipients(self) -> List[str]:
        """Get default email recipients from settings."""
        smtp_to = getattr(settings, 'SMTP_TO', None)
        if smtp_to:
            if isinstance(smtp_to, str):
                return [addr.strip() for addr in smtp_to.split(',')]
            elif isinstance(smtp_to, list):
                return smtp_to
        return []

    def _build_red_alert_html(
        self,
        entity_type: str,
        entity_id: int,
        entity_name: str,
        compliance_reason: str,
        last_successful_backup: Optional[datetime]
    ) -> str:
        """Build HTML body for RED status alert."""
        last_backup_str = (
            last_successful_backup.strftime('%Y-%m-%d %H:%M:%S UTC')
            if last_successful_backup
            else "Never"
        )

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #d32f2f; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
        .alert-box {{ background-color: #ffebee; border-left: 4px solid #d32f2f; padding: 15px; margin: 15px 0; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .info-table td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .info-table td:first-child {{ font-weight: bold; width: 40%; }}
        .action-box {{ background-color: #fff3e0; border-left: 4px solid #ff9800; padding: 15px; margin: 15px 0; }}
        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Compliance Alert - NON-COMPLIANT</h1>
        </div>
        <div class="content">
            <div class="alert-box">
                <h2 style="margin-top: 0; color: #d32f2f;">Backup Compliance Violation Detected</h2>
                <p>The following {entity_type.lower()} has transitioned to <strong>RED</strong> (non-compliant) status and requires immediate attention.</p>
            </div>

            <h3>{entity_type} Details</h3>
            <table class="info-table">
                <tr>
                    <td>Name:</td>
                    <td><strong>{entity_name}</strong></td>
                </tr>
                <tr>
                    <td>ID:</td>
                    <td>#{entity_id}</td>
                </tr>
                <tr>
                    <td>Type:</td>
                    <td>{entity_type}</td>
                </tr>
                <tr>
                    <td>Status:</td>
                    <td><strong style="color: #d32f2f;">RED - Non-Compliant</strong></td>
                </tr>
                <tr>
                    <td>Reason:</td>
                    <td>{compliance_reason}</td>
                </tr>
                <tr>
                    <td>Last Successful Backup:</td>
                    <td>{last_backup_str}</td>
                </tr>
                <tr>
                    <td>Alert Date:</td>
                    <td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
            </table>

            <div class="action-box">
                <h3 style="margin-top: 0;">⚠ Action Required</h3>
                <ol>
                    <li><strong>Verify Backup Schedule:</strong> Ensure a backup schedule is configured and enabled</li>
                    <li><strong>Check {entity_type} Status:</strong> Verify the {entity_type.lower()} is running and accessible</li>
                    <li><strong>Review Backup Logs:</strong> Check recent job logs for backup failures</li>
                    <li><strong>Trigger Manual Backup:</strong> If needed, initiate a manual backup immediately</li>
                    <li><strong>Escalate if Persistent:</strong> Contact your backup administrator if issue persists</li>
                </ol>
                <p><strong>Impact:</strong> This {entity_type.lower()} is not protected and data loss may occur in case of failure.</p>
            </div>

            <div class="footer">
                <p>This is an automated compliance alert from Lab Backup System.<br>
                For more information, access the web interface at <a href="http://localhost:8000">http://localhost:8000</a></p>
            </div>
        </div>
    </div>
</body>
</html>
        """

    def _build_red_alert_text(
        self,
        entity_type: str,
        entity_id: int,
        entity_name: str,
        compliance_reason: str,
        last_successful_backup: Optional[datetime]
    ) -> str:
        """Build plain text body for RED status alert."""
        last_backup_str = (
            last_successful_backup.strftime('%Y-%m-%d %H:%M:%S UTC')
            if last_successful_backup
            else "Never"
        )

        return f"""
🚨 COMPLIANCE ALERT - NON-COMPLIANT
{'=' * 60}

Backup Compliance Violation Detected
-------------------------------------
The following {entity_type.lower()} has transitioned to RED (non-compliant) status
and requires immediate attention.

{entity_type} Details
{'-' * 30}
Name:                   {entity_name}
ID:                     #{entity_id}
Type:                   {entity_type}
Status:                 RED - Non-Compliant
Reason:                 {compliance_reason}
Last Successful Backup: {last_backup_str}
Alert Date:             {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

ACTION REQUIRED
{'-' * 30}
1. Verify Backup Schedule: Ensure a backup schedule is configured and enabled
2. Check {entity_type} Status: Verify the {entity_type.lower()} is running and accessible
3. Review Backup Logs: Check recent job logs for backup failures
4. Trigger Manual Backup: If needed, initiate a manual backup immediately
5. Escalate if Persistent: Contact your backup administrator if issue persists

IMPACT: This {entity_type.lower()} is not protected and data loss may occur in case of failure.

---
This is an automated compliance alert from Lab Backup System.
For more information, access the web interface at http://localhost:8000
"""

    def _build_daily_summary_html(
        self,
        dashboard_data: Dict[str, Any],
        non_compliant_entities: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """Build HTML body for daily compliance summary."""
        vms = dashboard_data['vms']
        containers = dashboard_data['containers']
        red_vms = non_compliant_entities['vms']
        red_containers = non_compliant_entities['containers']

        # Calculate health percentage
        total_entities = vms['total'] + containers['total']
        green_entities = vms['green'] + containers['green']
        health_pct = (green_entities / total_entities * 100) if total_entities > 0 else 0

        # Determine overall status color
        if vms['red'] + containers['red'] > 0:
            status_color = "#d32f2f"
            status_text = "CRITICAL"
        elif vms['yellow'] + containers['yellow'] > 0:
            status_color = "#ff9800"
            status_text = "WARNING"
        else:
            status_color = "#4caf50"
            status_text = "HEALTHY"

        # Build non-compliant entities section
        red_section = ""
        if red_vms or red_containers:
            red_section = "<h3>🚨 Non-Compliant Entities (Requires Immediate Action)</h3>"

            if red_vms:
                red_section += "<h4>Virtual Machines</h4><ul>"
                for vm in red_vms:
                    last_backup = vm.get('last_backup', 'Never')
                    red_section += f"<li><strong>{vm['name']}</strong> (ID: {vm['id']})<br>Reason: {vm['reason']}<br>Last Backup: {last_backup}</li>"
                red_section += "</ul>"

            if red_containers:
                red_section += "<h4>Containers</h4><ul>"
                for container in red_containers:
                    last_backup = container.get('last_backup', 'Never')
                    red_section += f"<li><strong>{container['name']}</strong> (ID: {container['id']})<br>Reason: {container['reason']}<br>Last Backup: {last_backup}</li>"
                red_section += "</ul>"

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
        .summary-box {{ background-color: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }}
        .stat-card {{ background-color: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 5px; text-align: center; }}
        .stat-value {{ font-size: 32px; font-weight: bold; margin: 10px 0; }}
        .stat-label {{ font-size: 14px; color: #666; }}
        .status-bar {{ display: flex; height: 30px; border-radius: 5px; overflow: hidden; margin: 15px 0; }}
        .status-segment {{ display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold; }}
        .green {{ background-color: #4caf50; }}
        .yellow {{ background-color: #ff9800; }}
        .red {{ background-color: #d32f2f; }}
        .grey {{ background-color: #9e9e9e; }}
        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Daily Compliance Report - {status_text}</h1>
            <p style="margin: 5px 0 0 0;">Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
        <div class="content">
            <div class="summary-box">
                <h2>Overall Compliance: {health_pct:.1f}%</h2>
                <div class="status-bar">
                    <div class="status-segment green" style="width: {vms['green'] + containers['green']}/{total_entities * 100 if total_entities > 0 else 100}%">GREEN: {vms['green'] + containers['green']}</div>
                    <div class="status-segment yellow" style="width: {vms['yellow'] + containers['yellow']}/{total_entities * 100 if total_entities > 0 else 100}%">YELLOW: {vms['yellow'] + containers['yellow']}</div>
                    <div class="status-segment red" style="width: {vms['red'] + containers['red']}/{total_entities * 100 if total_entities > 0 else 100}%">RED: {vms['red'] + containers['red']}</div>
                    <div class="status-segment grey" style="width: {vms['grey'] + containers['grey']}/{total_entities * 100 if total_entities > 0 else 100}%">GREY: {vms['grey'] + containers['grey']}</div>
                </div>
            </div>

            <h3>Virtual Machines ({vms['total']} total)</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" style="color: #4caf50;">{vms['green']}</div>
                    <div class="stat-label">GREEN - Compliant</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #ff9800;">{vms['yellow']}</div>
                    <div class="stat-label">YELLOW - Warning</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #d32f2f;">{vms['red']}</div>
                    <div class="stat-label">RED - Non-Compliant</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #9e9e9e;">{vms['grey']}</div>
                    <div class="stat-label">GREY - No Policy</div>
                </div>
            </div>

            <h3>Containers ({containers['total']} total)</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" style="color: #4caf50;">{containers['green']}</div>
                    <div class="stat-label">GREEN - Compliant</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #ff9800;">{containers['yellow']}</div>
                    <div class="stat-label">YELLOW - Warning</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #d32f2f;">{containers['red']}</div>
                    <div class="stat-label">RED - Non-Compliant</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #9e9e9e;">{containers['grey']}</div>
                    <div class="stat-label">GREY - No Policy</div>
                </div>
            </div>

            {red_section}

            <div class="footer">
                <p>This is an automated daily compliance report from Lab Backup System.<br>
                For more details, access the web interface at <a href="http://localhost:8000/compliance">http://localhost:8000/compliance</a></p>
            </div>
        </div>
    </div>
</body>
</html>
        """

    def _build_daily_summary_text(
        self,
        dashboard_data: Dict[str, Any],
        non_compliant_entities: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """Build plain text body for daily compliance summary."""
        vms = dashboard_data['vms']
        containers = dashboard_data['containers']
        red_vms = non_compliant_entities['vms']
        red_containers = non_compliant_entities['containers']

        total_entities = vms['total'] + containers['total']
        green_entities = vms['green'] + containers['green']
        health_pct = (green_entities / total_entities * 100) if total_entities > 0 else 0

        text = f"""
📊 DAILY COMPLIANCE REPORT
{'=' * 60}
Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

Overall Compliance: {health_pct:.1f}%

VIRTUAL MACHINES ({vms['total']} total)
{'-' * 30}
GREEN (Compliant):      {vms['green']}
YELLOW (Warning):       {vms['yellow']}
RED (Non-Compliant):    {vms['red']}
GREY (No Policy):       {vms['grey']}

CONTAINERS ({containers['total']} total)
{'-' * 30}
GREEN (Compliant):      {containers['green']}
YELLOW (Warning):       {containers['yellow']}
RED (Non-Compliant):    {containers['red']}
GREY (No Policy):       {containers['grey']}
"""

        if red_vms or red_containers:
            text += f"\n🚨 NON-COMPLIANT ENTITIES (Requires Immediate Action)\n{'-' * 60}\n"

            if red_vms:
                text += "\nVirtual Machines:\n"
                for vm in red_vms:
                    last_backup = vm.get('last_backup', 'Never')
                    text += f"  - {vm['name']} (ID: {vm['id']})\n"
                    text += f"    Reason: {vm['reason']}\n"
                    text += f"    Last Backup: {last_backup}\n"

            if red_containers:
                text += "\nContainers:\n"
                for container in red_containers:
                    last_backup = container.get('last_backup', 'Never')
                    text += f"  - {container['name']} (ID: {container['id']})\n"
                    text += f"    Reason: {container['reason']}\n"
                    text += f"    Last Backup: {last_backup}\n"

        text += """
---
This is an automated daily compliance report from Lab Backup System.
For more details, access the web interface at http://localhost:8000/compliance
"""
        return text

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
