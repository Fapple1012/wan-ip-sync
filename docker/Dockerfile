FROM python:3.12-slim

WORKDIR /app

# 使用腾讯云镜像源加速基础镜像和pip包
RUN pip config set global.index-url https://mirrors.tencent.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.tencent.com \
    && pip config set global.extra-index-url https://mirror.ccs.tencentyun.com/pypi/simple \
    && pip config set global.cache-dir /tmp/pip-cache

# 安装系统依赖（使用腾讯云Debian镜像）
RUN echo 'deb https://mirrors.tencent.com/debian trixie main non-free-firmware' > /etc/apt/sources.list && \
    echo 'deb https://mirrors.tencent.com/debian-security trixie-security main' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.tencent.com/debian trixie-updates main' >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    gnupg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装Playwright浏览器及其依赖
RUN pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium

# 复制依赖文件
COPY ../requirements.txt /tmp/requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 复制应用代码
COPY ../src /app/src
COPY ../config/config.yaml /app/config/config.yaml

# 创建日志和数据目录
RUN mkdir -p logs data

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 默认运行方式
CMD ["python", "src/main.py"]
