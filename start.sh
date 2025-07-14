#!/bin/bash

# 1. 安装项目依赖
pip install -r requirements.txt

# 2. 安装Playwright的Chromium浏览器及其系统依赖
playwright install --with-deps chromium

# 3. 用gunicorn启动你的FastAPI应用
#    -w 4 表示启动4个工作进程
#    -k uvicorn.workers.UvicornWorker 是让gunicorn使用uvicorn来处理请求
#    app:app 指的是 app.py 文件中的 app = FastAPI()
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
