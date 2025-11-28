"""
NotificationService: Handles notifications for test execution events

Supports:
- Email notifications (SMTP)
- Slack notifications (webhook)
- Webhook notifications (custom URLs)
"""

import logging
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, List
from datetime import datetime
import requests
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection


class NotificationService:
    """Service for sending execution notifications"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system = System()
        
        # SMTP settings from environment
        self.smtp_host = getattr(self.system, 'smtp_host', 'localhost')
        self.smtp_port = int(getattr(self.system, 'smtp_port', 587))
        self.smtp_user = getattr(self.system, 'smtp_user', None)
        self.smtp_password = getattr(self.system, 'smtp_password', None)
        self.smtp_from = getattr(self.system, 'smtp_from', 'noreply@auroqa.local')
    
    def get_notification_settings(self, plan_id: int) -> Optional[Dict]:
        """Get notification settings for a plan"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT notify_on_start, notify_on_completion, notify_on_failure,
                           notify_on_retry, email_recipients, webhook_urls, slack_channels
                    FROM execution_suite_plan_notifications
                    WHERE execution_suite_plan_id = %s
                    """,
                    (plan_id,)
                )
                result = cursor.fetchone()
                if result:
                    return {
                        'notify_on_start': result[0],
                        'notify_on_completion': result[1],
                        'notify_on_failure': result[2],
                        'notify_on_retry': result[3],
                        'email_recipients': result[4].split(',') if result[4] else [],
                        'webhook_urls': result[5].split(',') if result[5] else [],
                        'slack_channels': result[6].split(',') if result[6] else []
                    }
                return None
        except Exception as e:
            self.logger.error(f"Error getting notification settings: {e}")
            return None
        finally:
            return_db_connection(conn)
    
    def save_notification_settings(
        self,
        plan_id: int,
        notify_on_start: bool = False,
        notify_on_completion: bool = True,
        notify_on_failure: bool = True,
        notify_on_retry: bool = False,
        email_recipients: List[str] = None,
        webhook_urls: List[str] = None,
        slack_channels: List[str] = None
    ) -> bool:
        """Save or update notification settings for a plan"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check if settings exist
                cursor.execute(
                    "SELECT id FROM execution_suite_plan_notifications WHERE execution_suite_plan_id = %s",
                    (plan_id,)
                )
                exists = cursor.fetchone()
                
                email_str = ','.join(email_recipients) if email_recipients else None
                webhook_str = ','.join(webhook_urls) if webhook_urls else None
                slack_str = ','.join(slack_channels) if slack_channels else None
                
                if exists:
                    cursor.execute(
                        """
                        UPDATE execution_suite_plan_notifications
                        SET notify_on_start = %s, notify_on_completion = %s,
                            notify_on_failure = %s, notify_on_retry = %s,
                            email_recipients = %s, webhook_urls = %s, slack_channels = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE execution_suite_plan_id = %s
                        """,
                        (notify_on_start, notify_on_completion, notify_on_failure,
                         notify_on_retry, email_str, webhook_str, slack_str, plan_id)
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO execution_suite_plan_notifications
                            (execution_suite_plan_id, notify_on_start, notify_on_completion,
                             notify_on_failure, notify_on_retry, email_recipients,
                             webhook_urls, slack_channels)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (plan_id, notify_on_start, notify_on_completion, notify_on_failure,
                         notify_on_retry, email_str, webhook_str, slack_str)
                    )
                
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error saving notification settings: {e}")
            return False
        finally:
            return_db_connection(conn)
    
    def notify_execution_start(self, plan_id: int, run_id: int, plan_name: str):
        """Send notification when execution starts"""
        settings = self.get_notification_settings(plan_id)
        if not settings or not settings.get('notify_on_start'):
            return
        
        subject = f"[AuroQA] Execution Started: {plan_name}"
        message = f"""
Test Execution Started

Plan: {plan_name}
Run ID: {run_id}
Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This is an automated notification from AuroQA.
"""
        self._send_all_notifications(settings, subject, message, 'started')
    
    def notify_execution_complete(
        self,
        plan_id: int,
        run_id: int,
        plan_name: str,
        status: str,
        total_tests: int,
        passed_tests: int,
        failed_tests: int,
        duration_seconds: float
    ):
        """Send notification when execution completes"""
        settings = self.get_notification_settings(plan_id)
        if not settings:
            return
        
        # Check if we should notify
        should_notify = settings.get('notify_on_completion')
        if status == 'failed' and settings.get('notify_on_failure'):
            should_notify = True
        
        if not should_notify:
            return
        
        status_emoji = "✅" if status == 'passed' else "❌"
        subject = f"[AuroQA] {status_emoji} Execution {status.upper()}: {plan_name}"
        
        message = f"""
Test Execution {status.upper()}

Plan: {plan_name}
Run ID: {run_id}
Status: {status.upper()}

Results:
  Total Tests: {total_tests}
  Passed: {passed_tests}
  Failed: {failed_tests}
  Duration: {duration_seconds:.1f}s

Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This is an automated notification from AuroQA.
"""
        self._send_all_notifications(settings, subject, message, status)
    
    def notify_retry(self, plan_id: int, run_id: int, plan_name: str, retry_count: int, test_name: str):
        """Send notification when a test is retried"""
        settings = self.get_notification_settings(plan_id)
        if not settings or not settings.get('notify_on_retry'):
            return
        
        subject = f"[AuroQA] Test Retry: {test_name}"
        message = f"""
Test Retry Notification

Plan: {plan_name}
Run ID: {run_id}
Test: {test_name}
Retry Count: {retry_count}

This is an automated notification from AuroQA.
"""
        self._send_all_notifications(settings, subject, message, 'retry')
    
    def _send_all_notifications(self, settings: Dict, subject: str, message: str, status: str):
        """Send notifications through all configured channels"""
        # Email notifications
        if settings.get('email_recipients'):
            self._send_email(settings['email_recipients'], subject, message)
        
        # Slack notifications
        if settings.get('slack_channels'):
            self._send_slack(settings['slack_channels'], subject, message, status)
        
        # Webhook notifications
        if settings.get('webhook_urls'):
            self._send_webhook(settings['webhook_urls'], subject, message, status)
    
    def _send_email(self, recipients: List[str], subject: str, message: str):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_from
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            self.logger.info(f"Email sent to {recipients}")
        except Exception as e:
            self.logger.error(f"Error sending email: {e}")
    
    def _send_slack(self, channels: List[str], subject: str, message: str, status: str):
        """Send Slack notification via webhook"""
        color = "#36a64f" if status == 'passed' else "#dc3545" if status in ['failed', 'error'] else "#ffc107"
        
        payload = {
            "attachments": [{
                "color": color,
                "title": subject,
                "text": message,
                "footer": "AuroQA Notification",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        for webhook_url in channels:
            try:
                response = requests.post(
                    webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                if response.status_code == 200:
                    self.logger.info(f"Slack notification sent to {webhook_url}")
                else:
                    self.logger.warning(f"Slack notification failed: {response.status_code}")
            except Exception as e:
                self.logger.error(f"Error sending Slack notification: {e}")
    
    def _send_webhook(self, urls: List[str], subject: str, message: str, status: str):
        """Send webhook notification"""
        payload = {
            "subject": subject,
            "message": message,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "source": "AuroQA"
        }
        
        for url in urls:
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                if response.status_code in [200, 201, 202]:
                    self.logger.info(f"Webhook notification sent to {url}")
                else:
                    self.logger.warning(f"Webhook notification failed: {response.status_code}")
            except Exception as e:
                self.logger.error(f"Error sending webhook notification: {e}")
