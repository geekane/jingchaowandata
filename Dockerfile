# 1. 选择一个官方的、稳定的Python基础镜像
FROM python:3.11-slim

# 2. 设置工作目录
WORKDIR /app

# 3. 核心步骤：更新软件包列表，并一次性安装所有依赖
#    - fonts-wqy-zenhei: 中文字体
#    - libnss3 libnspr4 ...: Playwright 运行 Chromium 所需的所有系统库
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    fonts-wqy-zenhei \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 4. 复制并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 安装Playwright的浏览器
RUN playwright install chromium

# 6. 复制项目的所有剩余文件
COPY . .

# 7. 暴露服务端口
EXPOSE 10000

# 8. 容器启动时执行的最终命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
