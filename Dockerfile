# 1. 从微软官方的、预装好一切的Playwright镜像开始
# 这个镜像已经包含了Python, 所有系统依赖, 浏览器, 以及字体
FROM mcr.microsoft.com/playwright/python:v1.53.0-jammy

# 2. 设置工作目录
WORKDIR /app

# 3. 复制我们项目的依赖文件
COPY requirements.txt .

# 4. 安装我们项目所需的Python库
RUN pip install --no-cache-dir -r requirements.txt

# 5. 复制我们项目的所有代码 (app.py, index.html, 字体文件等)
COPY . .

# 6. 暴露服务端口
EXPOSE 10000

# 7. 容器启动时，运行我们的FastAPI应用
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
