import re
import asyncio
import logging
import requests
from typing import Optional
from playwright.async_api import async_playwright

logger = logging.getLogger("IPFetcher")


class HuaweiRouterFetcher:
    """华为凌霄子母路由 Q6 IP获取器（使用Playwright）"""

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password

    async def _get_ip_via_browser(self) -> Optional[str]:
        """使用无头浏览器获取IP"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                # 访问登录页
                await page.goto(f"{self.url}/html/index.html")
                await page.wait_for_load_state("networkidle")

                # 填写密码并登录
                await page.fill("#userpassword_ctrl", self.password)
                await page.keyboard.press("Enter")

                # 等待登录成功
                try:
                    await page.wait_for_url("**/home**", timeout=15000)
                    logger.info("路由器登录成功")
                except Exception:
                    logger.error("等待登录超时")
                    await browser.close()
                    return None

                # 跳转到设备信息页面获取IP
                await page.goto(f"{self.url}/html/index.html#/more/deviceinfo")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

                # 获取页面文本
                text = await page.inner_text("body")

                # 解析公网IP（格式：WAN IP 59.56.34.93）
                ip_match = re.search(r'WAN\s*IP\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text, re.IGNORECASE)
                if ip_match:
                    wan_ip = ip_match.group(1)
                    logger.info(f"从路由器获取到公网IP: {wan_ip}")
                    await browser.close()
                    return wan_ip

                logger.error("页面中未找到公网IP")
                await browser.close()
                return None

        except Exception as e:
            logger.error(f"浏览器获取IP失败: {e}")
            return None

    def _fetch_from_backup(self) -> Optional[str]:
        """从外部服务获取IP（备用方案）"""
        backup_services = [
            "https://api.ipify.org",
            "https://icanhazip.com",
            "https://ifconfig.me/ip",
        ]

        for service in backup_services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    ip = response.text.strip()
                    if self._is_valid_ip(ip):
                        logger.info(f"从外部服务获取到公网IP: {ip}")
                        return ip
            except Exception:
                continue

        logger.error("无法获取公网IP")
        return None

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """验证是否为有效的IPv4地址"""
        pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        return bool(re.match(pattern, ip))

    def get_public_ip(self) -> Optional[str]:
        """获取公网IP地址"""
        # 首先尝试使用浏览器从路由器获取
        ip = asyncio.run(self._get_ip_via_browser())
        if ip:
            return ip

        # 备用方案：通过外部服务获取
        return self._fetch_from_backup()


class IPFetcher:
    def __init__(self, config: dict):
        router_config = config.get("router", {})
        self.fetcher = HuaweiRouterFetcher(
            url=router_config.get("url", "http://192.168.3.1"),
            username=router_config.get("username", "admin"),
            password=router_config.get("password", ""),
        )

    def get_public_ip(self) -> Optional[str]:
        return self.fetcher.get_public_ip()


def get_public_ip(config: dict) -> Optional[str]:
    """便捷函数：获取公网IP"""
    fetcher = IPFetcher(config)
    return fetcher.get_public_ip()