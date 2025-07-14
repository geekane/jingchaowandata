import asyncio
import base64
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse  # === 1. 新增导入 ===
import uvicorn

from playwright.async_api import async_playwright
from openai import AsyncOpenAI
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')

COOKIE_FILE = '来客.json'
TARGET_URL = "https://www.life-data.cn/?channel_id=laike_data_first_menu&groupid=1768205901316096"
SCREENSHOT_PATH = "dashboard_screenshot.png"
DEBUG_SCREENSHOT_PATH = "debug_screenshot.png"  # === 2. 定义调试截图路径 ===
REFRESH_INTERVAL_SECONDS = 10

client = AsyncOpenAI(
    base_url='https://api-inference.modelscope.cn/v1/',
    api_key='bae85abf-09f0-4ea3-9228-1448e58549fc',
)
MODEL_ID = 'Qwen/Qwen2.5-VL-7B-Instruct' 

app_state = {"latest_data": None, "status": "Initializing..."}

def get_detailed_prompt():
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
    try:
        with open(image_path, "rb") as image_file: return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError: return ""

async def analyze_image_with_vlm(image_base64: str) -> dict:
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

async def run_playwright_scraper():
    if not os.path.exists(COOKIE_FILE):
        app_state["status"] = f"错误: Cookie 文件 '{COOKIE_FILE}' 未找到。"
        logging.error(app_state["status"])
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        try:
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                await context.add_cookies(json.load(f)['cookies'])
            logging.info("Cookie 加载成功。")
        except Exception as e:
            app_state["status"] = f"加载 Cookie 失败: {e}"
            await browser.close()
            return

        page = await context.new_page()
        try:
            logging.info(f"正在导航至: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
            
            while True:
                try:
                    logging.info("开始新一轮数据刷新...")
                    await page.reload(wait_until="domcontentloaded", timeout=90000)
                    await asyncio.sleep(5) 
                    logging.info("页面刷新成功，正在进行常规截图...")
                    await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
                    
                    image_base64 = encode_image_to_base64(SCREENSHOT_PATH)
                    if image_base64:
                        analysis_result = await analyze_image_with_vlm(image_base64)
                        if analysis_result:
                            app_state["latest_data"] = analysis_result
                            app_state["status"] = f"数据已更新。下一次刷新在 {REFRESH_INTERVAL_SECONDS} 秒后。"
                        else:
                            app_state["status"] = "AI分析未能生成有效数据，正在重试..."
                    else:
                        app_state["status"] = "创建截图失败，正在重试..."

                except PlaywrightTimeoutError as e:
                    # =========================================================
                    # === 3. 核心修改：在超时错误时，保存调试截图 ===
                    # =========================================================
                    logging.error(f"页面刷新超时！正在保存当前浏览器页面用于调试...")
                    try:
                        await page.screenshot(path=DEBUG_SCREENSHOT_PATH, full_page=True)
                        logging.info(f"调试截图已保存为 {DEBUG_SCREENSHOT_PATH}。您可以通过访问 /debug_screenshot 查看。")
                    except Exception as screenshot_error:
                        logging.error(f"保存调试截图失败: {screenshot_error}")

                    app_state["status"] = "目标页面加载超时，正在重试..."
                    logging.error(f"页面刷新超时，将在 {REFRESH_INTERVAL_SECONDS} 秒后重试: {e}")
                
                except Exception as e:
                    logging.error(f"后台任务发生未知错误，将在 {REFRESH_INTERVAL_SECONDS} 秒后重试: {e}")
                    app_state["status"] = "后台任务发生未知错误，正在重试..."
                
                await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

        except Exception as e:
            app_state["status"] = f"Playwright 任务发生致命错误: {e}"
            logging.error(f"Playwright 任务发生致命错误，任务已终止: {e}", exc_info=True)
        finally:
            await browser.close()

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

# =========================================================
# === 4. 新增：用于提供调试截图的API路由 ===
# =========================================================
@app.get("/debug_screenshot")
async def get_debug_screenshot():
    if os.path.exists(DEBUG_SCREENSHOT_PATH):
        return FileResponse(DEBUG_SCREENSHOT_PATH)
    return HTTPException(status_code=404, detail="调试截图不存在，可能尚未发生超时错误。")

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("      🚀 竞潮玩实时数据看板 (调试模式) 🚀")
    print(f"\n      ➡️   http://127.0.0.1:7860")
    print(f"      ➡️   当超时发生后，请访问 /debug_screenshot 查看快照")
    print("="*60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=7860)
