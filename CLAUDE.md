# WAN IP Sync - Claude Code 项目上下文

## 项目概述

**项目名称**: WAN IP Sync
**核心功能**: 从华为路由器获取公网IP，自动同步到阿里云云解析DNS
**运行环境**: Python 3.12+, 支持 Docker 部署

## 目录结构

```
wan-ip-sync/
├── src/
│   ├── main.py              # 程序入口
│   └── modules/
│       ├── config_loader.py # 配置加载（单例模式）
│       ├── ip_fetcher.py    # IP获取（华为路由器SCRAM认证）
│       ├── dns_syncer.py    # DNS同步（阿里云SDK）
│       └── notifier.py      # 通知模块（Webhook）
├── config/
│   ├── config.yaml          # 配置文件
│   └── config.yaml.example  # 配置示例
├── docker/
│   └── Dockerfile            # Docker镜像构建
├── docs/
│   └── ARCHITECTURE.md       # 架构设计文档
├── logs/                     # 日志目录
├── data/
│   └── .last_ip             # 上次IP记录
├── requirements.txt
└── CLAUDE.md                # 本文件
```

## 核心模块

### IP获取 (ip_fetcher.py)
- **HuaweiRouterFetcher**: 使用路由器HTTP API + SCRAM认证
- 备用方案: api.ipify.org, icanhazip.com, ifconfig.me/ip

### DNS同步 (dns_syncer.py)
- **AliyunDNSSyncer**: 使用阿里云 Python SDK
- 支持 UpdateDomainRecord / AddDomainRecord

### 通知 (notifier.py)
- 支持钉钉/企业微信 Webhook

## 配置项 (config.yaml)

```yaml
router:
  url: "http://192.168.3.1"
  username: "admin"
  password: "your_router_password"
  timeout: 10

aliyun:
  access_key_id: "your_access_key_id"
  access_key_secret: "your_access_key_secret"
  region_id: "cn-hangzhou"

domains:
  - domain: "your-domain.com"
    record: "subdomain"  # @ 表示根域名
    ttl: 600

check_interval: 3600      # 检查间隔（秒）

notification:
  type: "webhook"
  webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
```

## 运行方式

```bash
# 直接运行（循环模式）
python src/main.py

# 单次执行
python src/main.py --once

# 指定配置文件
python src/main.py --config /path/to/config.yaml

# Docker 运行
docker run -v ./config:/app/config wan-ip-sync
```

## 关键设计

1. **IP比较逻辑**: 首次运行从阿里云DNS获取记录IP，之后用本地 `.last_ip` 文件比较
2. **启动时清空本地IP**: 确保每次启动重新检测DNS状态
3. **日志**: 控制台 DEBUG 级别，文件 WARNING 级别，时区 UTC+8
4. **Docker 配置**: 使用腾讯云镜像源加速，目录挂载 `/app/config:/app/config`

## Commit 规范

使用中文撰写 commit message，格式为 `<类型>: <描述>`

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat:` | 新功能 | `feat: 添加企业微信Webhook支持` |
| `fix:` | 修复Bug | `fix: 修复路由器登录失败的问题` |
| `docs:` | 文档更新 | `docs: 更新README安装说明` |
| `style:` | 代码格式（不影响功能） | `style: 调整缩进风格` |
| `refactor:` | 重构（不影响功能） | `refactor: 提取IP比较逻辑` |
| `perf:` | 性能优化 | `perf: 减少DNS API调用次数` |
| `test:` | 测试相关 | `test: 添加IP获取单元测试` |
| `chore:` | 构建/工具相关 | `chore: 更新Docker镜像源` |
| `ci:` | CI/CD相关 | `ci: 添加GitHub Actions流程` |

**注意**:
- 修复代码时必须使用 `fix:` 打头
- 新功能使用 `feat:` 打头
- 冒号后加空格，描述简洁明了

## 工作流约定

### Commit 后构建 Docker

**每次执行 `git commit` 后**，自动询问是否需要构建 Docker 镜像：

```
Commit 完成，是否构建 Docker 镜像？

[ Yes ]  构建镜像 (docker build -t wan-ip-sync .)
[ No ]   跳过
```

- 选择 Yes：执行 `docker build -t wan-ip-sync .` 命令
- 选择 No：结束当前操作
