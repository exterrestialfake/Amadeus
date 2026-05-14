from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from agent import ContextSchema, init_amadeus
import sys
import os

from config.logging_Setup import setup_logging
from loguru import logger
print(sys.path[0])
# 配置日志
setup_logging()


Amadeus = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务器启动时预加载 AI 模型，防止需要第一次调用才加载模型"""
    global Amadeus
    connecting_time = 0
    MAX_CONNECTIING_TIME = 5
    while Amadeus is None and connecting_time <= MAX_CONNECTIING_TIME:
        if connecting_time >=1:
            logger.warning(f"Amadeus agent连接失败，次数：{connecting_time}")
        elif connecting_time == MAX_CONNECTIING_TIME:
            logger.error("Amadues创建失败，请检查网络后尝试")
        Amadeus = await init_amadeus()
        connecting_time += 1
    yield
    # 服务关闭时在此做清理（如有需要）
    Amadeus = None
app = FastAPI(title="Amadeus Core API", lifespan=lifespan)


# 输入与输出类
class InvokeRequest(BaseModel):
    prompt: str
    user_name: str = "christina"

class InvokeResponse(BaseModel):
    response: str

@app.post("/api/invoke", response_model=InvokeResponse)
async def invoke_agent(req: InvokeRequest):
    message = {"role": "user", "content": req.prompt}
    
    result = await Amadeus.ainvoke(
        {"messages": [message]},
        {"configurable": {"thread_id": "lab_test", "screen_permission": "1"}},
        context=ContextSchema(user_name=req.user_name, memory_mode=True)
    )
    
    reply = result["messages"][-1].content
    return InvokeResponse(response=reply)

if __name__ == "__main__":
    import uvicorn
    # 本地启动FastAPI服务器
    uvicorn.run("invoke:app", host="127.0.0.1", port=8000, reload=True)
