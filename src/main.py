#!/usr/bin/env python3
import os
import sys
import time
import logging
import argparse
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_loader import ConfigLoader, get_config
from modules.ip_fetcher import IPFetcher
from modules.dns_syncer import DNSSyncer
from modules.notifier import Notifier


LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "wan_ip_sync.log")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STATE_FILE = os.path.join(DATA_DIR, ".last_ip")


class UTC8Formatter(logging.Formatter):
    """UTC+8 时区的格式化器"""
    def converter(self, timestamp):
        import datetime as dt_module
        utc_dt = dt_module.datetime.fromtimestamp(timestamp, dt_module.timezone.utc)
        return utc_dt.astimezone(dt_module.timezone(dt_module.timedelta(hours=8)))

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def setup_logging():
    """配置日志：DEBUG到屏幕，WARNING+同时写文件"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(UTC8Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(UTC8Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[console_handler, file_handler],
    )

    # 禁用第三方库的 DEBUG 日志
    for logger_name in [
        "urllib3",
        "requests",
        "aliyunsdkcore",
        "aliyunsdkalidns",
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def load_last_ip(state_file: str) -> str:
    """加载上次保存的IP"""
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def save_current_ip(state_file: str, ip: str):
    """保存当前IP"""
    try:
        with open(state_file, "w") as f:
            f.write(ip)
        logging.info(f"保存当前公网IP:{ip}")
    except Exception as e:
        logging.error(f"保存IP失败: {e}")


def sync_once(config: dict, notifier: Notifier = None) -> bool:
    """执行一次同步"""
    logging.debug("=" * 50)
    logging.debug("开始执行IP同步")

    # 1. 获取当前公网IP（从路由器）
    fetcher = IPFetcher(config)
    current_ip = fetcher.get_public_ip()

    if not current_ip:
        logging.error("无法获取公网IP")
        if notifier:
            notifier.notify_error("无法获取公网IP，请检查路由器连接")
        return False

    logging.debug(f"当前公网IP: {current_ip}")

    # 2. 获取上次保存的IP（dns_ip）
    last_ip = load_last_ip(STATE_FILE)
    syncer = DNSSyncer(config)

    if last_ip:
        # 非首次运行：直接用本地保存的IP比较
        logging.debug(f"上次保存的IP: {last_ip}")
        if current_ip == last_ip:
            logging.debug("IP未变化，无需更新DNS")
            return True
        # IP发生变化，需要同步
        need_update = True
        dns_ip = last_ip
    else:
        # 首次运行：从阿里云DNS获取各记录当前的IP
        logging.debug("首次运行，从阿里云DNS获取各记录当前IP")
        dns_ips = {}
        for domain_config in config.get("domains", []):
            domain = domain_config.get("domain")
            record = domain_config.get("record", "@")
            dns_ip = syncer.get_dns_ip(domain, record)
            record_name = f"{record}.{domain}" if record != "@" else domain
            dns_ips[record_name] = dns_ip
            if dns_ip:
                logging.debug(f"DNS当前IP [{record_name}]: {dns_ip}")
            else:
                logging.debug(f"DNS当前IP [{record_name}]: 不存在")

        # 检查是否有任何记录需要更新
        need_update = False
        for record_name, dns_ip in dns_ips.items():
            if dns_ip and dns_ip != current_ip:
                need_update = True
                logging.debug(f"IP变化检测: {record_name} ({dns_ip} -> {current_ip})")

        if not need_update:
            logging.debug("DNS记录已是最新，无需更新")
            save_current_ip(STATE_FILE, current_ip)
            return True

    # 3. 执行DNS同步
    logging.debug("执行DNS同步...")
    results = syncer.sync_all(current_ip)

    failed = [record for record, success in results.items() if not success]
    if failed:
        logging.warning(f"部分记录更新失败: {failed}")

    # 4. 保存当前IP到本地文件
    save_current_ip(STATE_FILE, current_ip)

    # 5. 发送通知
    if notifier:
        if dns_ip:
            notifier.notify_ip_changed(dns_ip, current_ip, results)
        else:
            notifier.notify_startup(current_ip)

    logging.debug("IP同步完成")
    return True


def run_loop(config: dict):
    """循环运行"""
    interval = config.get("check_interval", 600)
    # notifier = Notifier(config) if config.get("notification", {}).get("webhook_url") else None
    notifier = None

    logging.debug(f"程序启动，每 {interval} 秒检查一次")

    while True:
        try:
            sync_once(config, notifier)
        except Exception as e:
            logging.error(f"同步过程出错: {e}")

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="WAN IP Sync to Aliyun DNS")
    parser.add_argument("--config", "-c", help="配置文件路径", default=None)
    parser.add_argument("--once", "-o", action="store_true", help="只执行一次，不循环")

    args = parser.parse_args()

    setup_logging()

    loader = ConfigLoader()
    config = loader.load(args.config)

    if args.once:
        sync_once(config)
    else:
        run_loop(config)


if __name__ == "__main__":
    main()
