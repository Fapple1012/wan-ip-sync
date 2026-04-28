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


def setup_logging():
    """配置日志"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


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
    except Exception as e:
        logging.error(f"保存IP失败: {e}")


def sync_once(config: dict, notifier: Notifier = None) -> bool:
    """执行一次同步"""
    logging.info("=" * 50)
    logging.info("开始执行IP同步")

    # 1. 获取当前公网IP（从路由器）
    fetcher = IPFetcher(config)
    current_ip = fetcher.get_public_ip()

    if not current_ip:
        logging.error("无法获取公网IP")
        if notifier:
            notifier.notify_error("无法获取公网IP，请检查路由器连接")
        return False

    logging.info(f"当前公网IP: {current_ip}")

    # 2. 从阿里云DNS获取各记录当前的IP
    syncer = DNSSyncer(config)
    dns_ips = {}
    for domain_config in config.get("domains", []):
        domain = domain_config.get("domain")
        record = domain_config.get("record", "@")
        dns_ip = syncer.get_dns_ip(domain, record)
        record_name = f"{record}.{domain}" if record != "@" else domain
        dns_ips[record_name] = dns_ip
        if dns_ip:
            logging.info(f"DNS当前IP [{record_name}]: {dns_ip}")
        else:
            logging.info(f"DNS当前IP [{record_name}]: 不存在")

    # 3. 检查是否有任何记录需要更新
    need_update = False
    for record_name, dns_ip in dns_ips.items():
        if dns_ip != current_ip:
            need_update = True
            if dns_ip:
                logging.info(f"IP变化检测: {record_name} ({dns_ip} -> {current_ip})")
            else:
                logging.info(f"DNS记录不存在或需创建: {record_name} -> {current_ip}")

    if not need_update:
        logging.info("DNS记录已是最新，无需更新")
        return True

    # 4. 执行DNS同步
    logging.info("执行DNS同步...")
    results = syncer.sync_all(current_ip)

    failed = [record for record, success in results.items() if not success]
    if failed:
        logging.warning(f"部分记录更新失败: {failed}")

    # 5. 保存当前IP到本地文件
    save_current_ip(STATE_FILE, current_ip)

    # 6. 发送通知
    if notifier:
        old_ips = {name: ip for name, ip in dns_ips.items() if ip}
        if old_ips:
            old_ip_str = list(old_ips.values())[0]
            notifier.notify_ip_changed(old_ip_str, current_ip, results)
        else:
            notifier.notify_startup(current_ip)

    logging.info("IP同步完成")
    return True


def run_loop(config: dict):
    """循环运行"""
    interval = config.get("check_interval", 600)
    notifier = Notifier(config) if config.get("notification", {}).get("webhook_url") else None

    logging.info(f"程序启动，每 {interval} 秒检查一次")

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