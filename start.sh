#!/bin/bash

# 1. 安装固定版本的依赖
pip install -r requirements.txt

# 2. (核心修改) 只安装Playwright的Chromium浏览器，不尝试安装系统依赖
playwright install chromium

# 3. 用uvicorn启动你的FastAPI应用
uvicorn app:app --host 0.0.0.0 --port 10000
