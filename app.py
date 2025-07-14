import asyncio
import base64
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from playwright.async_api import async_playwright, Page
from openai import AsyncOpenAI
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')

# 环境变量优先，如果不存在则退回使用文件（为了本地调试方便）
COOKIE_VALUE_FROM_ENV = os.getenv("LIFE_DATA_COOKIE")
COOKIE_FILE = '来客.json'

TARGET_URL = "https://www.life-data.cn/?channel_id=laike_data_first_menu&groupid=1768205901316096"
SCREENSHOT_PATH = "dashboard_screenshot.png"
DEBUG_SCREENSHOT_PATH = "debug_screenshot.png"
REFRESH_INTERVAL_SECONDS = 10

client = AsyncOpenAI(
    base_url='https://api-inference.modelscope.cn/v1/',
    api_key='bae85abf-09f0-4ea3-9228-1448e58549fc',
)
MODEL_ID = 'Qwen/Qwen2.5-VL-7B-Instruct' 

app_state = {"latest_data": None, "status": "Initializing..."}

def get_detailed_prompt():
    # ... 此函数保持不变 ...
    return """
    你是一个专业的数据分析师。请分析这张仪表盘截图，并提取所有关键指标卡片的信息。
    严格按照以下JSON格式返回，不要添加任何额外的解释或Markdown标记。
    { "update_time": "...", "comparison_date": "...", "metrics": [ { "name": "...", "value": "...", "comparison": "...", "status": "..." } ] }
    请确保：
    1. **只提取以下指标**：成交金额、核销金额、商品访问人数、核销券数。
    2. **忽略“退款金额”** 以及其他所有未列出的指标。
    3. 所有字段都从图片中准确提取。
    """

def encode_image_to_base64(image_path: str) -> str:
    # ... 此函数保持不变 ...
    try:
        with open(image_path, "rb") as image_file: return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError: return ""

async def analyze_image_with_vlm(image_base64: str) -> dict:
    # ... 此函数保持不变 ...
    if not image_base64: return {}
    try:
        response = await client.chat.completions.create(
            model=MODEL_ID,
            messages=[{'role': 'user', 'content': [{'type': 'text', 'text': get_detailed_prompt()}, {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{image_base64}'}}],}]
        )
        raw_content = response.choices[0].message.content
        if raw_content.startswith("```json"): raw_content = raw_content[7:-3].strip()
        return json.loads(raw_content)
    except Exception as e:
        logging.error(f"调用视觉模型或解析JSON时出错: {e}")
        return {}


# =========================================================
# === 核心修改：使用最严谨的方式来验证页面 ===
# =========================================================
async def wait_for_data_to_load(page: Page, timeout: int = 60000):
    """
    智能等待，直到页面上出现 "今日实时数据" 这个关键文本。
    这是判断是否成功进入仪表盘页面的最可靠方法。
    """
    logging.info("正在严谨验证页面内容，寻找 '今日实时数据'...")
    try:
        # Playwright 的 `page.get_by_text()` 非常强大，它能找到任何包含指定文本的元素。
        # 我们在这里等待这个元素变得可见。
        await page.get_by_text("今日实时数据").wait_for(state="visible", timeout=timeout)
        
        logging.info("验证成功！已在页面上找到 '今日实时数据'。")
        return True
    except PlaywrightTimeoutError:
        logging.error(f"验证失败：在 {timeout/1000} 秒内未找到 '今日实时数据' 文本。")
        return False
    except Exception as e:
        logging.error(f"在验证页面时发生未知错误: {e}")
        return False


async def run_playwright_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # 统一的Cookie处理逻辑
        try:
            if COOKIE_VALUE_FROM_ENV:
                logging.info("正在使用环境变量中的Cookie...")
                cookie = {"name": "satoken", "value": COOKIE_VALUE_FROM_ENV, "domain": "www.life-data.cn", "path": "/"}
                await context.add_cookies([cookie])
                logging.info("成功设置satoken Cookie。")
            elif os.path.exists(COOKIE_FILE):
                logging.info(f"正在使用文件 '{COOKIE_FILE}' 中的Cookie...")
                with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                    await context.add_cookies(json.load(f)['cookies'])
                logging.info("成功从文件加载Cookie。")
            else:
                app_state["status"] = "错误: 未找到任何Cookie配置 (环境变量或文件)。"
                logging.error(app_state["status"])
                await browser.close()
                return
        except Exception as e:
            app_state["status"] = f"设置或加载Cookie失败: {e}"
            await browser.close()
            return

        page = await context.new_page()
        try:
            logging.info(f"正在导航至: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
            
            # 在进入主循环前，先进行一次决定性的页面验证
            if not await wait_for_data_to_load(page, timeout=30000): # 首次验证给30秒时间
                app_state["status"] = "致命错误: 无法验证目标页面，很可能Cookie已失效或需要重新登录。"
                logging.error(app_state["status"])
                await page.screenshot(path=DEBUG_SCREENSHOT_PATH, full_page=True)
                logging.info(f"致命错误快照已保存至 {DEBUG_SCREENSHOT_PATH}。")
                await browser.close()
                return # 直接退出后台任务

            logging.info("首次页面验证通过，进入持续刷新循环。")

            while True:
                try:
                    logging.info("开始新一轮数据刷新...")
                    await page.reload(wait_until="domcontentloaded", timeout=90000)
                    
                    # 每次刷新后都进行验证
                    if await wait_for_data_to_load(page):
                        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
                        image_base64 = encode_image_to_base64(SCREENSHOT_PATH)
                        if image_base64:
                            analysis_result = await analyze_image_with_vlm(image_base64)
                            if analysis_result and analysis_result.get('metrics'):
                                app_state["latest_data"] = analysis_result
                                app_state["status"] = f"数据已更新。下一次刷新在 {REFRESH_INTERVAL_SECONDS} 秒后。"
                            else:
                                app_state["status"] = "AI分析未能提取有效数据。"
                        else:
                            app_state["status"] = "创建截图失败。"
                    else:
                        app_state["status"] = "页面验证失败，可能已掉线。"
                        await page.screenshot(path=DEBUG_SCREENSHOT_PATH, full_page=True)

                except Exception as e:
                    logging.error(f"后台任务循环发生错误: {e}")
                    app_state["status"] = "后台任务发生错误，正在重试..."
                    await page.screenshot(path=DEBUG_SCREENSHOT_PATH, full_page=True)
                
                await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

        except Exception as e:
            app_state["status"] = f"Playwright 任务发生致命错误: {e}"
            logging.error(f"Playwright 任务发生致命错误: {e}", exc_info=True)
            await page.screenshot(path=DEBUG_SCREENSHOT_PATH, full_page=True)
        finally:
            await browser.close()

# ... FastAPI的lifespan, app, 路由等部分保持不变 ...
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_playwright_scraper())
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/data")
async def get_data():
    if app_state["latest_data"] is None:
        raise HTTPException(status_code=404, detail={"status": app_state["status"], "data": None})
    return {"status": app_state["status"], "data": app_state["latest_data"]}

@app.get("/debug_screenshot")
async def get_debug_screenshot():
    if os.path.exists(DEBUG_SCREENSHOT_PATH): return FileResponse(DEBUG_SCREENSHOT_PATH)
    return HTTPException(status_code=404, detail="调试截图不存在。")

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("      🚀 竞潮玩实时数据看板 (严谨验证模式) 🚀")
    print(f"\n      ➡️   http://127.0.0.1:7860")
    print("="*60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=7860)
