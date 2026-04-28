# WAN IP Sync to Aliyun DNS

从华为路由器获取公网IP，自动同步到阿里云云解析DNS的DDNS工具。

## 功能特性

- 从华为凌霄子母路由 Q6 获取公网IP（使用Playwright无头浏览器）
- 自动同步到阿里云云解析DNS（支持A记录）
- IP变化时通过钉钉/企业微信Webhook发送通知
- 支持单次执行和循环执行模式
- 日志长期保留

## 环境要求

- Python 3.10+
- Chrome/Chromium 浏览器（Playwright会自动安装）
- 华为凌霄子母路由 Q6（或固件API兼容的华为路由器）

## 安装

```bash
# 克隆或下载项目
cd wan_ip_sync

# 安装依赖
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chromium
```

## 配置

编辑 `config.yaml`：

```yaml
router:
  url: "http://192.168.3.1"      # 路由器地址
  username: "admin"             # 用户名
  password: "123456"           # 路由器登录密码

aliyun:
  access_key_id: "your_access_key_id"      # 阿里云AccessKey ID
  access_key_secret: "your_access_key_secret"  # 阿里云AccessKey Secret
  region_id: "cn-hangzhou"                  # 区域（默认即可）

domains:
  - domain: "your-domain.com"    # 主域名
    record: "subdomain"           # 子域名（如www，或@表示根域名）
    ttl: 600                       # TTL（秒）

check_interval: 3600    # 检查间隔（秒），默认1小时

notification:
  type: "webhook"       # 通知类型
  webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=your_token"
```

### 域名配置说明

```yaml
domains:
  # 示例1: service.your-domain.com
  - domain: "your-domain.com"
    record: "service"
    ttl: 600

  # 示例2: 根域名 your-domain.com
  - domain: "your-domain.com"
    record: "@"
    ttl: 600

  # 示例3: 多个子域名
  - domain: "your-domain.com"
    record: "www"
    ttl: 600
  - domain: "your-domain.com"
    record: "blog"
    ttl: 600
```

## 使用方法

### 循环运行（默认，每小时检查一次）

```bash
python src/main.py
```

### 单次执行

```bash
python src/main.py --once
```

### 指定配置文件

```bash
python src/main.py --config /path/to/config.yaml
```

## Docker部署

### 前置要求

- Docker Engine 20.10+
- Docker Compose 2.0+

### 快速启动

```bash
# 1. 克隆项目
git clone <repo-url> wan_ip_sync
cd wan_ip_sync

# 2. 编辑配置文件
vim config/config.yaml

# 3. 构建并启动
cd docker && docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

### 使用Docker Compose

```yaml
services:
  wan-ip-sync:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: wan-ip-sync
    restart: unless-stopped
    volumes:
      - ../config/config.yaml:/app/config/config.yaml:ro  # 只读挂载配置
      - ../logs:/app/logs                    # 持久化日志
      - ../data:/app/data                    # 持久化IP记录
    working_dir: /app/src
    environment:
      - TZ=Asia/Shanghai                     # 设置时区
```

### 手动Docker运行

```bash
# 构建镜像（从项目根目录）
docker build -t wan-ip-sync -f docker/Dockerfile .

# 运行容器
docker run -d \
  --name wan-ip-sync \
  --restart unless-stopped \
  -v $(pwd)/config/config.yaml:/app/config/config.yaml:ro \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  -w /app/src \
  wan-ip-sync
```

### 单次运行模式

```bash
docker run --rm \
  -v $(pwd)/config/config.yaml:/app/config/config.yaml:ro \
  -v $(pwd)/data:/app/data \
  -w /app/src \
  wan-ip-sync python main.py --once
```

### 查看容器状态

```bash
# 查看运行状态
docker ps | grep wan-ip-sync

# 查看实时日志
docker-compose logs -f

# 进入容器调试
docker exec -it wan-ip-sync bash
```

### 清理

```bash
# 停止并删除容器
docker-compose down

# 删除镜像
docker rmi wan-ip-sync
```

## 运行日志

日志文件位于 `logs/wan_ip_sync.log`，内容示例：

```
[2026-04-27 10:00:00] [INFO] [IPFetcher] 从路由器获取到公网IP: 59.56.34.93
[2026-04-27 10:00:01] [INFO] [DNSSyncer] DNS记录更新成功: service.fapple1012.com -> 59.56.34.93
[2026-04-27 10:00:01] [INFO] [Notifier] Webhook通知发送成功
```

## 通知效果

IP变化时，钉钉/企业微信会收到类似消息：

```
公网IP已变更

旧IP: 59.56.34.92
新IP: 59.56.34.93

同步结果:
  - service.fapple1012.com: 成功
```

## 项目结构

```
wan_ip_sync/
├── src/                    # 代码目录
│   ├── main.py             # 程序入口
│   └── modules/            # 模块目录
│       ├── config_loader.py    # 配置加载
│       ├── ip_fetcher.py       # IP获取（Playwright）
│       ├── dns_syncer.py       # DNS同步（阿里云SDK）
│       └── notifier.py         # 通知（Webhook）
├── config/                 # 配置目录
│   └── config.yaml         # 配置文件
├── docker/                 # Docker相关
│   ├── Dockerfile          # Docker镜像构建文件
│   └── docker-compose.yml  # Docker Compose配置
├── docs/                   # 文档目录
│   └── ARCHITECTURE.md     # 架构设计文档
├── logs/                   # 日志目录
├── data/                   # 数据目录
├── requirements.txt        # 依赖
└── README.md               # 使用说明
```
│   ├── Dockerfile          # Docker镜像构建文件
│   └── docker-compose.yml  # Docker Compose配置
├── docs/                   # 文档目录
│   ├── ARCHITECTURE.md     # 架构设计文档
│   └── README.md           # 本文档
├── logs/                   # 日志目录
└── data/                   # 数据目录（IP记录）
```

## 故障排除

### 1. 路由器登录失败

- 确认路由器地址是否正确（默认 `http://192.168.3.1`）
- 确认用户名密码是否正确
- 确认路由器Web管理界面可以正常访问

### 2. 获取IP失败

- 检查路由器是否正常联网
- 程序会自动切换到外部IP服务作为备用方案

### 3. DNS更新失败

- 确认阿里云AccessKey有DNS完全权限
- 确认域名已在阿里云注册
- 确认要更新的记录存在（或程序会自动创建）

### 4. 钉钉通知失败

- 确认Webhook地址正确
- 确认机器人没有被禁用
- 检查钉钉群机器人安全设置（关键词/加签等）

## License

MIT License
