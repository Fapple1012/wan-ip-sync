FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（Playwright需要的系统库）
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装Chrome浏览器（Playwright需要）
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY ../requirements.txt /tmp/requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 安装Playwright浏览器
RUN playwright install chromium

# 复制应用代码
COPY ../src /app/src
COPY ../config/config.yaml /app/config/config.yaml

# 创建日志和数据目录
RUN mkdir -p logs data

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 默认运行方式
CMD ["python", "src/main.py"]
