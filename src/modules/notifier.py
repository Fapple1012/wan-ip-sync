import logging
import json
import requests
from typing import Optional
from modules.config_loader import get_config

logger = logging.getLogger("Notifier")


class WebhookNotifier:
    """Webhook通知器（支持钉钉、企业微信等）"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str, msg_type: str = "text") -> bool:
        """发送Webhook消息"""
        payload = {
            "msgtype": msg_type,
            msg_type: {"content": message}
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"Webhook通知发送成功")
                    return True
                else:
                    logger.warning(f"Webhook通知发送失败: {result.get('errmsg', '未知错误')}")
            else:
                logger.warning(f"Webhook请求失败，状态码: {response.status_code}")

        except Exception as e:
            logger.error(f"发送Webhook消息失败: {e}")

        return False


class Notifier:
    def __init__(self, config: dict):
        self.config = config
        self.notifier: Optional[WebhookNotifier] = None

        notification_config = config.get("notification", {})
        notification_type = notification_config.get("type", "webhook")

        if notification_type == "webhook":
            webhook_url = notification_config.get("webhook_url")
            if webhook_url:
                self.notifier = WebhookNotifier(webhook_url)

    def notify_ip_changed(self, old_ip: str, new_ip: str, records: dict) -> bool:
        """发送IP变更通知"""
        if not self.notifier:
            logger.warning("未配置通知器")
            return False

        message_lines = [
            f"公网IP已变更",
            f"",
            f"旧IP: {old_ip}",
            f"新IP: {new_ip}",
            f"",
            f"同步结果:",
        ]

        for record, success in records.items():
            status = "成功" if success else "失败"
            message_lines.append(f"  - {record}: {status}")

        message = "\n".join(message_lines)
        return self.notifier.send(message)

    def notify_error(self, error_message: str) -> bool:
        """发送错误通知"""
        if not self.notifier:
            return False

        message = f"WAN IP Sync 错误\n\n{error_message}"
        return self.notifier.send(message)

    def notify_startup(self, ip: str) -> bool:
        """发送启动通知"""
        if not self.notifier:
            return False

        message = f"WAN IP Sync 已启动\n\n当前公网IP: {ip}"
        return self.notifier.send(message)


def send_ip_change_notification(config: dict, old_ip: str, new_ip: str, records: dict) -> bool:
    """便捷函数：发送IP变更通知"""
    notifier = Notifier(config)
    return notifier.notify_ip_changed(old_ip, new_ip, records)