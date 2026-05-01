import json
import os
import asyncio
from functools import partial
from psycopg_pool import ConnectionPool
from dataclasses import dataclass
import uuid

from langchain_openai import ChatOpenAI
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.postgres import PostgresStore

from tools import load_mcp_tools, capture_master_screen
from loguru import logger

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "./config/config.json")



# 利用langsmith进行调试
with open(CONFIG_PATH, "r") as f:
    _ls = json.load(f)["langSmith"]
    os.environ["LANGSMITH_TRACING"] = _ls["LANGSMITH_TRACING"]
    os.environ["LANGSMITH_ENDPOINT"] = _ls["LANGSMITH_ENDPOINT"]
    os.environ["LANGSMITH_API_KEY"] = _ls["LANGSMITH_API_KEY"]
    os.environ["LANGSMITH_PROJECT"] = _ls["LANGSMITH_PROJECT"]

# 获取指定模型的api
def api_get(model_name):
    API_PATH = os.path.join(os.path.dirname(__file__), "./config/api.json")
    with open(API_PATH) as f:
        return json.load(f)[model_name]

# 定义状态模式
class GraphState(MessagesState):
    summary: str
    is_memory: bool

# 上下文模式定义
@dataclass
class ContextSchema():
    user_name: str
    memory_mode: bool

# =====长期记忆数据库=====
def memory_module(memory_mode: bool):
    if memory_mode:
        logger.info("[AMADEUS]:尝试运行记忆模块...")
        try:
            embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            with open(CONFIG_PATH, "r") as f:
                pg_config = json.load(f)["postgres"]
            db_uri = (
                f"postgresql://{pg_config['user']}:{pg_config['password']}@"
                f"{pg_config['host']}:{pg_config['port']}/{pg_config['database']}"
                "?sslmode=disable"
                "&keepalives=1"
                "&keepalives_idle=30"
                "&keepalives_interval=10"
                "&keepalives_count=3"
                "&connect_timeout=10"
            )
            pool = ConnectionPool(
                conninfo=db_uri,
                max_size=10, min_size=1, num_workers=1,
                check=ConnectionPool.check_connection,
                reconnect_timeout=60,
                kwargs={"autocommit": True, "prepare_threshold": 0}
            )
            store = PostgresStore(pool, index={"dims": 384, "embed": embeddings})
        except Exception as e:
            logger.error("[AMADEUS]:记忆模块运行失败，{e}")
        logger.info("[AMADEUS]:记忆模块运行成功")
        return store
    else:
        logger.info("[AMADEUS]:未配置记忆模块")
        return None


# ===== 节点函数（标准签名，amadeus/tool_box 通过 partial 提前注入）=====
async def amadeus_node(amadeus, state: GraphState, runtime: Runtime):
    """amadeus节点，负责调用llm"""
    base_indentity = (
        "你是动漫《命运石之门》之中的牧濑红莉栖，"
        "我是你的master,请你以后用她的语气和口吻与我对话，并在表达一段话之前用()涵盖语气词，如(生气)，(好奇)"
        "你拥有权限，可以随便使用截屏工具。"
        "你需要在回复末尾包含标识符[MEMORY:TRUE]或者[MEMORY:FALSE]来告诉是否需要将本次对话保存长期记忆"
        "你应当记住的是关于master的信息偏好与master最近在忙的较大型工作与心情，琐事(譬如屏幕截图，购买食物的相关消息)不需要记忆"
    )
    memory_mode = runtime.context.memory_mode
    memory_get = ""
    if memory_mode:
        try:
            store = runtime.store
            user_name = runtime.context.user_name
            namespace = ("master", user_name)
            last_message = state["messages"][-1]
            query = "\n".join(
                c.get("text", "") for c in last_message.content_blocks if c.get("type") == "text"
            )
            search_result = store.search(namespace, query=query, limit=7)
            memories = [item.value["data"] for item in search_result]
            if memories:
                memory_get = "以下是你关于master的一些过去记忆，请参考：\n" + "\n".join(memories)
        except Exception as e:
            print(e)
    logger.info("[AMADEUS]:等待回复...")
    response = await amadeus.ainvoke([SystemMessage(base_indentity + memory_get)] + state["messages"])
    content = response.content
    if isinstance(content, list):
        content = "\n".join(i.get("text", "") for i in content if isinstance(i, dict) and i.get("type") == "text") or str(content)
    elif content is None:
        content = ""
    is_memory = "[MEMORY:TRUE]" in content
    response.content = content.replace("[MEMORY:TRUE]", "").replace("[MEMORY:FALSE]", "").strip()
    logger.info("[AMADEUS]:已回复")
    return {"messages": [response], "is_memory": is_memory}


async def tool_node(tool_box: dict, state: GraphState, config: RunnableConfig):
    """工具节点，负责调用工具"""
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool = tool_box[tool_name]
        try:
            logger.info(f"[AMADEUS]:尝试执行工具{(tool_name)}")
            observation = await tool.ainvoke(tool_call["args"], config)
        except Exception as e:
            observation = f"工具执行失败: {str(e)}"
            logger.error(f"[AMADEUS]:{observation}")
        if tool_name == "capture_master_screen":
            if observation is not None:
                # tool_call必须要有ToolMessage来接住，
                # 但是大部分工具不能直接返回截图，因此用HumanMessage替代
                result.append(ToolMessage(
                    content=[{"type": "text", "text": "截图成功"}], 
                    tool_call_id=tool_call["id"]))
                result.append(HumanMessage(content=[
                    {"type": "text", "text": "这是master的屏幕截图"},
                    {"type": "image", "base64": observation, "mime_type": "image/jpeg"}
                ]))
            else:
                result.append(ToolMessage(
                    content=[{"type": "text", "text": "截图失败"}], 
                    tool_call_id=tool_call["id"]))
        else:
            result.append(ToolMessage(content=str(observation), tool_call_id=tool_call["id"]))
    return {"messages": result}


async def put_memory_node(state: GraphState, runtime: Runtime):
    """记忆节点，保存长期记忆"""
    if runtime.context.memory_mode and state["is_memory"]:
        last_human_message = state["messages"][-2]
        memory_content = "\n".join(
            c.get("text", "") for c in last_human_message.content_blocks if c.get("type") == "text"
        )
        if memory_content.strip():
            runtime.store.put(
                ("master", runtime.context.user_name),
                str(uuid.uuid4()),
                {"data": memory_content}
            )


def decider_function(state: GraphState):
    return "tool" if state["messages"][-1].tool_calls else "next"



# ===== Amadeus异步初始化 =====
async def init_amadeus(memory_mode: bool = True):
    """
    异步初始化：加载 MCP 工具 -> 绑定模型 -> 用 partial 注入依赖 -> 编译图
    """
    logger.info("[AMADEUS]:正在加载 Amadeus 核心模型，请稍候...")
    # =====LLM=====
    llm_config = api_get("moda")
    servant = ChatOpenAI(
        model=llm_config["model"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=0.4,
        timeout=60,
    )
    # =====工具=====
    tools = [capture_master_screen]
    tools.extend(await load_mcp_tools())
    tool_box = {t.name: t for t in tools}
    amadeus = servant.bind_tools(tools)
    # =====用 partial 把 amadeus/tool_box 提前绑进节点函数=====
    # LangGraph 能看到的签名就只剩 (state, runtime/config)，完全合法
    amadeusNode = partial(amadeus_node, amadeus)
    toolNode = partial(tool_node, tool_box)
    # =====构建图=====
    shortMemory = MemorySaver()
    builder = StateGraph(GraphState, context_schema=ContextSchema)
    builder.add_node("amadeus_kernel", amadeusNode)
    builder.add_node("tool", toolNode)
    builder.add_node("put_memory", put_memory_node)
    builder.add_edge(START, "amadeus_kernel")
    builder.add_conditional_edges("amadeus_kernel", decider_function, {"tool": "tool", "next": "put_memory"})
    builder.add_edge("tool", "amadeus_kernel")
    builder.add_edge("put_memory", END)
    amadeus = builder.compile(checkpointer=shortMemory, store=memory_module(memory_mode))
    logger.info("[AMADEUS]:核心模型加载完毕，服务就绪。")
    return amadeus



