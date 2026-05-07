import hashlib
import hmac
import logging
import re
import secrets
from typing import Optional

import requests

logger = logging.getLogger("IPFetcher")


class RouterLoginError(RuntimeError):
    """路由器登录流程异常。"""


class HuaweiRouterFetcher:
    """华为凌霄子母路由 Q6 IP获取器（使用路由器HTTP API）"""

    def __init__(self, url: str, username: str, password: str, timeout: int = 10):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    @staticmethod
    def _parse_csrf(html: str) -> dict[str, str]:
        csrf_param = re.search(r'<meta name="csrf_param" content="([^"]+)"', html)
        csrf_token = re.search(r'<meta name="csrf_token" content="([^"]+)"', html)
        if not csrf_param or not csrf_token:
            raise RouterLoginError("无法从路由器首页解析CSRF信息")

        return {
            "csrf_param": csrf_param.group(1),
            "csrf_token": csrf_token.group(1),
        }

    @staticmethod
    def _update_csrf(csrf: dict[str, str], payload: dict) -> dict[str, str]:
        if payload.get("csrf_param") and payload.get("csrf_token"):
            return {
                "csrf_param": payload["csrf_param"],
                "csrf_token": payload["csrf_token"],
            }
        return csrf

    @staticmethod
    def _router_hmac(key: bytes | str, message: bytes | str) -> bytes:
        if isinstance(key, str):
            key = key.encode()
        if isinstance(message, str):
            message = message.encode()
        return hmac.new(key, message, hashlib.sha256).digest()

    @classmethod
    def _make_client_proof(
        cls,
        password: str,
        salt_hex: str,
        iterations: int,
        auth_message: str,
    ) -> tuple[str, str]:
        salted_password = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            iterations,
            dklen=32,
        )

        # 路由器内置的CryptoJS SCRAM封装使用 HmacSHA256(message, key)，
        # 因此这里的HMAC参数顺序与标准SCRAM相反。
        client_key = cls._router_hmac(b"Client Key", salted_password)
        stored_key = hashlib.sha256(client_key).digest()
        client_signature = cls._router_hmac(auth_message, stored_key)
        client_proof = bytes(a ^ b for a, b in zip(client_key, client_signature)).hex()

        server_key = cls._router_hmac(b"Server Key", salted_password)
        expected_server_signature = cls._router_hmac(auth_message, server_key).hex()
        return client_proof, expected_server_signature

    def _post_json(self, session: requests.Session, path: str, payload: dict) -> dict:
        response = session.post(f"{self.url}{path}", json=payload, timeout=self.timeout)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise RouterLoginError(
                f"路由器接口 {path} 返回非JSON响应: {response.text!r}"
            ) from exc

    def _login(self, session: requests.Session) -> dict[str, str]:
        index = session.get(f"{self.url}/html/index.html", timeout=self.timeout)
        index.raise_for_status()
        csrf = self._parse_csrf(index.text)

        client_nonce = secrets.token_hex(32)
        nonce_response = self._post_json(
            session,
            "/api/system/user_login_nonce",
            {
                "data": {
                    "username": self.username,
                    "firstnonce": client_nonce,
                },
                "csrf": csrf,
            },
        )
        csrf = self._update_csrf(csrf, nonce_response)

        if nonce_response.get("err") != 0:
            raise RouterLoginError(f"user_login_nonce失败: {nonce_response}")

        server_nonce = nonce_response["servernonce"]
        auth_message = f"{client_nonce},{server_nonce},{server_nonce}"
        client_proof, expected_server_signature = self._make_client_proof(
            password=self.password,
            salt_hex=nonce_response["salt"],
            iterations=int(nonce_response["iterations"]),
            auth_message=auth_message,
        )

        proof_response = self._post_json(
            session,
            "/api/system/user_login_proof",
            {
                "data": {
                    "clientproof": client_proof,
                    "finalnonce": server_nonce,
                },
                "csrf": csrf,
            },
        )

        if proof_response.get("err") != 0:
            raise RouterLoginError(f"user_login_proof失败: {proof_response}")
        if proof_response.get("serversignature") != expected_server_signature:
            raise RouterLoginError("路由器SCRAM服务端签名校验失败")

        logger.debug("路由器登录成功")
        return self._update_csrf(csrf, proof_response)

    def _get_wan(self, session: requests.Session) -> dict:
        response = session.get(f"{self.url}/api/ntwk/wan?type=active", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_public_ip(self) -> Optional[str]:
        """获取公网IP地址（仅从路由器获取）"""
        try:
            with requests.Session() as session:
                session.headers.update(
                    {
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Content-Type": "application/json; charset=utf-8",
                        "X-Requested-With": "XMLHttpRequest",
                        "_ResponseFormat": "JSON",
                    }
                )

                self._login(session)
                wan = self._get_wan(session)

            wan_ip = wan.get("IPv4Addr")
            if not wan_ip:
                logger.error(f"路由器WAN接口响应中未找到IPv4Addr: {wan}")
                return None

            logger.debug(f"从路由器获取到公网IP: {wan_ip}")
            return wan_ip
        except (requests.RequestException, RouterLoginError, KeyError, ValueError) as exc:
            logger.error(f"路由器API获取IP失败: {exc}")
            raise


class IPFetcher:
    def __init__(self, config: dict):
        router_config = config.get("router", {})
        self.fetcher = HuaweiRouterFetcher(
            url=router_config.get("url", "http://192.168.3.1"),
            username=router_config.get("username", "admin"),
            password=router_config.get("password", ""),
            timeout=router_config.get("timeout", 10),
        )

    def get_public_ip(self) -> Optional[str]:
        return self.fetcher.get_public_ip()


def get_public_ip(config: dict) -> Optional[str]:
    """便捷函数：获取公网IP"""
    fetcher = IPFetcher(config)
    return fetcher.get_public_ip()
