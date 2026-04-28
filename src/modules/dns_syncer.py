import logging
from typing import Optional, List, Dict, Any
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import RpcRequest
from aliyunsdkalidns.request.v20150109 import UpdateDomainRecordRequest, DescribeDomainRecordsRequest, AddDomainRecordRequest
from modules.config_loader import get_config

logger = logging.getLogger("DNSSyncer")


class AliyunDNSSyncer:
    """阿里云DNS同步器"""

    def __init__(self, access_key_id: str, access_key_secret: str, region_id: str = "cn-hangzhou"):
        self.client = AcsClient(
            access_key_id,
            access_key_secret,
            region_id
        )

    def get_record_id(self, domain: str, record: str) -> Optional[str]:
        """获取域名记录ID"""
        request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
        request.set_DomainName(domain)
        request.set_PageSize(100)

        try:
            response = self.client.do_action_with_exception(request)
            import json
            data = json.loads(response)

            for item in data.get("DomainRecords", {}).get("Record", []):
                if item.get("RR") == record and item.get("Type") == "A":
                    return item.get("RecordId")

        except Exception as e:
            logger.error(f"获取记录ID失败: {e}")

        return None

    def get_record_value(self, domain: str, record: str) -> Optional[str]:
        """获取域名记录当前的IP值"""
        request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
        request.set_DomainName(domain)
        request.set_PageSize(100)

        try:
            response = self.client.do_action_with_exception(request)
            import json
            data = json.loads(response)

            for item in data.get("DomainRecords", {}).get("Record", []):
                if item.get("RR") == record and item.get("Type") == "A":
                    return item.get("Value")

        except Exception as e:
            logger.error(f"获取记录值失败: {e}")

        return None

    def update_record(self, domain: str, record: str, value: str, ttl: int = 600) -> bool:
        """更新DNS记录"""
        # 先获取当前记录的IP
        current_value = self.get_record_value(domain, record)

        if current_value == value:
            logger.info(f"DNS记录已是最新，无需更新: {record}.{domain} = {value}")
            return True

        if not current_value:
            # 记录不存在，创建新记录
            logger.warning(f"记录不存在，将创建新记录: {record}.{domain}")
            return self.add_record(domain, record, value, ttl)

        # 记录存在且IP不同，执行更新
        record_id = self.get_record_id(domain, record)
        request = UpdateDomainRecordRequest.UpdateDomainRecordRequest()
        request.set_RecordId(record_id)
        request.set_RR(record)
        request.set_Type("A")
        request.set_Value(value)
        request.set_TTL(ttl)

        try:
            self.client.do_action_with_exception(request)
            logger.info(f"DNS记录更新成功: {record}.{domain} ({current_value} -> {value})")
            return True
        except Exception as e:
            logger.error(f"更新DNS记录失败: {e}")
            return False

    def add_record(self, domain: str, record: str, value: str, ttl: int = 600) -> bool:
        """添加DNS记录"""
        request = AddDomainRecordRequest.AddDomainRecordRequest()
        request.set_DomainName(domain)
        request.set_RR(record)
        request.set_Type("A")
        request.set_Value(value)
        request.set_TTL(ttl)

        try:
            self.client.do_action_with_exception(request)
            logger.info(f"DNS记录添加成功: {record}.{domain} -> {value}")
            return True
        except Exception as e:
            logger.error(f"添加DNS记录失败: {e}")
            return False


class DNSSyncer:
    def __init__(self, config: dict):
        aliyun_config = config.get("aliyun", {})
        self.syncer = AliyunDNSSyncer(
            access_key_id=aliyun_config.get("access_key_id", ""),
            access_key_secret=aliyun_config.get("access_key_secret", ""),
            region_id=aliyun_config.get("region_id", "cn-hangzhou"),
        )
        self.domains = config.get("domains", [])

    def get_dns_ip(self, domain: str, record: str) -> Optional[str]:
        """获取DNS记录当前的IP"""
        return self.syncer.get_record_value(domain, record)

    def sync_all(self, ip: str) -> Dict[str, bool]:
        """同步所有域名记录"""
        results = {}

        for domain_config in self.domains:
            domain = domain_config.get("domain")
            record = domain_config.get("record", "@")
            ttl = domain_config.get("ttl", 600)

            if record == "@":
                record_name = domain
            else:
                record_name = f"{record}.{domain}"

            success = self.syncer.update_record(domain, record, ip, ttl)
            results[record_name] = success

        return results


def sync_to_dns(config: dict, ip: str) -> Dict[str, bool]:
    """便捷函数：同步IP到DNS"""
    syncer = DNSSyncer(config)
    return syncer.sync_all(ip)