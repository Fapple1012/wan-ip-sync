# WAN IP Sync to Aliyun DNS - 架构设计文档

## 1. 项目概述

**项目名称**: WAN IP Sync
**项目类型**: Python 异步同步工具
**核心功能**: 从华为路由器获取公网IP，自动同步到阿里云云解析DNS
**目标用户**: 需要将动态公网IP与域名绑定的用户

## 2. 系统架构

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   华为路由器      │────▶│   HTTP API        │────▶│   阿里云DNS      │
│ 凌霄子母路由 Q6   │     │   SCRAM登录       │     │   云解析DNS      │
│  (Web管理界面)    │     │                   │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                          ┌──────────────────┐
                          │   钉钉Webhook     │
                          │   通知服务        │
                          └──────────────────┘
                                │
                                ▼
                          ┌──────────────────┐
                          │   日志文件         │
                          │  (不清空，长期保留) │
                          └──────────────────┘
```

## 3. 模块设计

### 3.1 IP获取模块 (IPFetcher)

**类**: `HuaweiRouterFetcher`

**职责**: 从路由器获取公网IP地址

**技术方案**:
- 使用路由器HTTP API，无需无头浏览器
- 访问路由器 Web 管理入口 `http://192.168.3.1/html/index.html` 获取CSRF
- 调用 `/api/system/user_login_nonce` 发起SCRAM登录
- 调用 `/api/system/user_login_proof` 完成登录并校验服务端签名
- 调用 `/api/ntwk/wan?type=active` 获取当前活动WAN信息
- 从接口响应中的 `IPv4Addr` 字段读取公网IP

**备用方案**:
当路由器不可访问时，通过外部服务获取IP：
- https://api.ipify.org
- https://icanhazip.com
- https://ifconfig.me/ip

**关键代码逻辑**:
```python
# 登录
await page.fill("#userpassword_ctrl", password)
await page.keyboard.press("Enter")
await page.wait_for_url("**/home**", timeout=15000)

# 获取IP
await page.goto(f"{url}/html/index.html#/more/deviceinfo")
text = await page.inner_text("body")
ip_match = re.search(r'WAN\s*IP\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text)
```

### 3.2 DNS同步模块 (DNSSyncer)

**类**: `AliyunDNSSyncer`

**职责**: 将公网IP同步到阿里云云解析DNS

**技术方案**:
- 使用阿里云 Python SDK (`aliyun-python-sdk-core-v3`, `aliyun-python-sdk-alidns`)
- 使用 AcsClient 连接阿里云 API
- 调用 `UpdateDomainRecordRequest` 更新DNS记录
- 若记录不存在，自动调用 `AddDomainRecordRequest` 创建

**API调用流程**:
1. `DescribeDomainRecordsRequest` - 查询现有记录获取 RecordId
2. `UpdateDomainRecordRequest` - 更新记录（设置新IP）
3. 若记录不存在 - `AddDomainRecordRequest` - 创建新记录

### 3.3 通知模块 (Notifier)

**类**: `WebhookNotifier`

**职责**: 通过Webhook发送通知

**支持类型**:
- 钉钉机器人
- 企业微信机器人
- 任何支持 text 类型消息的 Webhook

**通知场景**:
- `notify_ip_changed`: IP发生变化时
- `notify_error`: 发生错误时（无法获取IP等）
- `notify_startup`: 程序启动时

### 3.4 配置加载模块 (ConfigLoader)

**类**: `ConfigLoader` (单例模式)

**职责**: 加载和管理配置文件

**配置文件格式**: YAML

```yaml
router:
  url: "http://192.168.3.1"
  username: "admin"
  password: "123456"

aliyun:
  access_key_id: "your_access_key_id"
  access_key_secret: "your_access_key_secret"
  region_id: "cn-hangzhou"

domains:
  - domain: "example.com"
    record: "subdomain"
    ttl: 600

check_interval: 3600  # 秒

notification:
  type: "webhook"
  webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
```

## 4. 主程序流程

### 4.1 循环模式 (默认)

```
启动程序
    │
    ▼
加载配置文件
    │
    ▼
初始化通知器（如果配置了Webhook）
    │
    ▼
获取当前公网IP
    │
    ▼
发送启动通知（包含当前IP）
    │
    ▼
保存当前IP到 .last_ip 文件
    │
    ▼
循环开始
    │
    ├─── 获取当前公网IP
    │
    ├─── 加载上次保存的IP
    │
    ├─── 比较IP
    │       │
    │       ├─ IP相同 ─→ 跳过DNS更新
    │       │
    │       └─ IP不同 ─→ 执行DNS同步
    │                   │
    │                   ├─── 更新阿里云DNS记录
    │                   │
    │                   ├─── 保存新IP到 .last_ip
    │                   │
    │                   └─── 发送IP变更通知
    │
    └─── 等待 check_interval 秒后继续
```

### 4.2 单次模式 (`--once`)

```
启动程序
    │
    ▼
加载配置文件
    │
    ▼
获取当前公网IP
    │
    ├─── 无法获取 ─→ 发送错误通知 → 退出
    │
    └─── 获取成功
            │
            ├─── 比较上次IP
            │       │
            │       ├─ IP相同 ─→ 退出
            │       │
            │       └─ IP不同 ─→ 更新DNS
            │
            └─── 退出
```

## 5. 文件结构

```
wan_ip_sync/
├── main.py                 # 程序入口
├── config.yaml             # 配置文件
├── requirements.txt        # 依赖包
├── modules/
│   ├── __init__.py
│   ├── config_loader.py    # 配置加载模块
│   ├── ip_fetcher.py       # IP获取模块（路由器HTTP API）
│   ├── dns_syncer.py       # DNS同步模块（阿里云SDK）
│   └── notifier.py         # 通知模块（Webhook）
├── logs/                   # 日志目录
│   └── wan_ip_sync.log     # 日志文件（不清空）
└── .last_ip               # 上次IP记录（隐藏文件）
```

## 6. 状态管理

### 6.1 IP状态文件 (`.last_ip`)

- 位置: 程序运行目录 `.last_ip`
- 内容: 最近一次成功同步的公网IP地址
- 用途: 与当前IP比较，判断是否需要更新DNS

### 6.2 日志文件

- 位置: `logs/wan_ip_sync.log`
- 格式: `[时间] [级别] [模块名] 消息`
- 保留策略: 不清空，长期保留
- 同时输出到控制台

## 7. 依赖技术

| 依赖包 | 版本 | 用途 |
|--------|------|------|
| aliyun-python-sdk-core-v3 | >=2.13.33 | 阿里云SDK核心 |
| aliyun-python-sdk-alidns | >=1.0.0 | 阿里云DNS API |
| pyyaml | >=6.0 | 配置文件解析 |
| requests | >=2.28.0 | 路由器API请求、Webhook通知 |

## 8. 错误处理

| 场景 | 处理方式 |
|------|----------|
| 路由器无法访问 | 切换到外部IP服务获取 |
| 外部IP服务也失败 | 发送错误通知，程序退出（循环模式则下次重试） |
| DNS API调用失败 | 记录日志，发送错误通知 |
| Webhook发送失败 | 仅记录日志，不重试 |
| 配置文件不存在 | 抛出 FileNotFoundError |

## 9. 命令行参数

| 参数 | 说明 |
|------|------|
| `--config`, `-c` | 指定配置文件路径 |
| `--once`, `-o` | 单次执行模式，不循环 |

## 10. 安全性考虑

- 配置文件中的密码和AccessKey应妥善保管
- 建议不要将 `config.yaml` 提交到版本控制系统
- 日志文件中可能包含IP地址信息，需注意隐私
