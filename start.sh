#!/bin/bash

# 1. 安装固定版本的依赖
pip install -r requirements.txt

# 2. 安装Playwright的Chromium浏览器及其系统依赖
#    加上 --force 选项确保每次都检查
playwright install --with-deps chromium

# 3. (核心修改) 直接用uvicorn启动你的FastAPI应用
#    --host 0.0.0.0 让服务可以被外部访问
#    --port 10000 是Render推荐的默认端口，它会自动映射
#    app:app 指的是 app.py 文件中的 app = FastAPI()
uvicorn app:app --host 0.0.0.0 --port 10000
