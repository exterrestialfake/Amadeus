from langchain_core.runnables import RunnableConfig
from langchain.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
import json
import os
import asyncio
import base64
from io import BytesIO
from PIL import ImageGrab
import pygetwindow as gw
from loguru import logger

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/config.json")

@tool
async def capture_master_screen(config: RunnableConfig):
    """
    当你想要知道master在干什么时，可以调用此工具截图master的当前活动窗口，
    来理解master在干什么
    """
    # =====截取窗口/屏幕=====
    # ======低权限(screen_permission=0)时，只截取当前活动窗口======
    if config.get("configurable").get("screen_permission") == 0:
        active_win = gw.getActiveWindow()
        if active_win:
            bbox = (active_win.left, active_win.top, active_win.right, active_win.bottom)
            screenshot = await asyncio.to_thread(ImageGrab.grab, bbox)
        else:
            return None
    # ======高权限(screen_permission=1)时，截取全屏======
    else:
        screenshot = await asyncio.to_thread(ImageGrab.grab)
    # ======对截图进行处理以节省token，并转为base64=====
    # 1、压缩分辨率
    max_size = 1024
    if max(screenshot.size) > max_size:
        screenshot.thumbnail((max_size, max_size))
    # 2、转换为JPEG，再转为base64
    buffered = BytesIO()
    screenshot.convert("RGB").save(buffered, format="JPEG", quality=70)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str

# 加载所有的MCP工具
async def load_mcp_tools():
    try:
        with open(CONFIG_PATH, "r") as f:
            mcp_config = json.load(f).get("mcpServers", {})
        client = MultiServerMCPClient(mcp_config)
        mcp_tools = await client.get_tools()
        return mcp_tools
    except Exception as e:
        import traceback
        logger.error(f"[AMADEUS]: MCP报错的详细错误堆栈：\n{traceback.format_exc()}")
        return []