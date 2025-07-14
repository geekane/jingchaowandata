# 1. 选择一个官方的、稳定的Python基础镜像
FROM python:3.11-slim

# 2. 设置工作目录，后续所有操作都在这个目录里进行
WORKDIR /app

# 3. 核心步骤：更新软件包列表，并安装中文字体
#    - apt-get update: 更新可用软件包的信息
#    - apt-get install -y: -y表示自动确认安装
#    - fonts-wqy-zenhei: 这是一个非常流行的开源中文字体（文泉驿正黑）
#    - --no-install-recommends: 不安装推荐的非必需包，保持镜像小巧
#    - rm -rf /var/lib/apt/lists/*: 清理缓存，减小最终镜像体积
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-wqy-zenhei && \
    rm -rf /var/lib/apt/lists/*

# 4. 复制依赖文件并安装依赖
#    先复制requirements.txt可以利用Docker的缓存机制，如果它没变，就不用重新安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 安装Playwright的浏览器
#    在已经安装了字体的环境下，我们只需要下载浏览器本身
RUN playwright install chromium

# 6. 复制项目的所有剩余文件到工作目录
COPY . .

# 7. 暴露服务端口（与uvicorn命令中的端口一致）
EXPOSE 10000

# 8. 容器启动时要执行的最终命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
