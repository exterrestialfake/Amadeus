import IPython.core.display_functions
import IPython.core.display_functions
import IPython.core.display_functions
import IPython.core.display_functions
import json
import os
from PIL import ImageGrab
import pygetwindow as gw
import base64
from io import BytesIO
from IPython.display import Image, display
from psycopg_pool import ConnectionPool
from dataclasses import dataclass
import uuid

from langchain_openai import ChatOpenAI
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.checkpoint.memory import MemorySaver 
from langgraph.store.postgres import PostgresStore


# 获取指定模型的api
def api_get(model_name):
    current_file = os.path.dirname(__file__)
    config_file = os.path.join(current_file, "api.json")
    with open(config_file) as f:
        config = json.load(f)[model_name]
    return config
## =====大模型调用配置=====
llm_config= api_get("moda")


# LLM绑定
servant = ChatOpenAI(
    model=llm_config["model"],
    api_key=llm_config["api_key"],
    base_url=llm_config["base_url"],
    max_tokens=1000,
    temperature=0.4
)

# 定义状态模式
class GraphState(MessagesState):
    summary:str
    is_memory:bool

# 上下文模式定义
@dataclass
class ContextSchema():
    user_name:str
    memory_mode:bool

# 配置工具函数
@tool
def capture_master_screen(config:RunnableConfig):
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
            screenshot = ImageGrab.grab(bbox)
        else:
            return None
    # ======高权限(screen_permission=1)时，截取全屏======
    else:
        screenshot = ImageGrab.grab()
    # ======对截图进行处理以节省token，并转为base64=====
    # 1、压缩分辨率
    max_size = 1024
    if max(screenshot.size)>max_size:
        screenshot.thumbnail((max_size, max_size))
    # 2、转换为JPEG，再转为base64
    buffered = BytesIO()
    screenshot.convert("RGB").save(buffered, format="JPEG", quality=70)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str
tools = [capture_master_screen]
tool_box = {tool.name:tool for tool in tools}
amadeus = servant.bind_tools(tools)


# 节点函数
def amadeus_node(state:GraphState, runtime:Runtime):
    """
    amadeus节点，负责调用llm
    """
    base_indentity = "你是动漫《命运石之门》之中的牧濑红莉栖，" \
    "我是你的master,请你以后用她的语气和口吻与我对话，并在表达一段话之前用()涵盖语气词，如(生气)，(好奇)"\
    "你拥有权限，可以随便使用截屏工具。" \
    "你需要在回复末尾包含标识符[MEMORY:TRUE]或者[MEMORY:FALSE]来告诉是否需要将本次对话保存长期记忆" \
    "你应当记住的是关于master的信息偏好与master最近在忙的较大型工作与心情，琐事(譬如屏幕截图，购买食物)不需要记忆"
    # 记忆模式
    memory_mode = runtime.context.memory_mode
    if memory_mode:
        ## =====搜索以往的长期记忆, 最多读取三条=====
        store = runtime.store
        user_name = runtime.context.user_name
        namespace = ("master", user_name)
        last_message_content = state["messages"][-1].content
        if isinstance(last_message_content, list):
            query = "\n".join([item["text"] for item in last_message_content if item.get("type", "text")=="text"])
        else:
            query = last_message_content
        search_result = store.search(namespace, query=query, limit=3)
        ## =====上下文注入=====
        memories = [item.value["data"] for item in search_result]
        if memories:
            memory_get = "以下是你关于master的一些过去记忆，请参考：\n"+"\n".join(memories)
        else:
            memory_get = ""
    else:
        memory_get = ""
    system_content = base_indentity+memory_get
    system_message = SystemMessage(system_content)
    
    response = amadeus.invoke([system_message]+state["messages"])
    content = response.content
    is_memory = "[MEMORY:TRUE]" in content
    response.content = content.replace("[MEMORY:TRUE]", "").replace("[MEMORY:FALSE]", "").strip()
    return {
            "messages":[response],
            "is_memory":is_memory
        }

def tool_node(state:GraphState, config:RunnableConfig):
    """
    工具节点，负责调用工具
    """
    # =====调用工具===== 
    result = []
    last_message = state["messages"][-1]
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool = tool_box[tool_name]
        tool_args = tool_call["args"]
        observation = tool.invoke(tool_args, config)
        if tool_name == "capture_master_screen":
            if observation is not None:
                # =====构建toolMessage返回=====
                tool_return = [
                    {"type":"text", "text":"screen successfully"}
                ]
                result.append(ToolMessage(content=tool_return, tool_call_id=tool_call["id"]))
                # =====构建截屏HumanMessage返回，让模型读取=====
                fake_humanMessage = HumanMessage(content=[
                    {"type":"text", "text":"这是master的屏幕截图"},
                    {
                    "type":"image",
                    "base64":f"{observation}",
                    "mime_type":"image/jpeg"}
                ])
                result.append(fake_humanMessage)
            else:
                tool_return = [
                    {"type":"text", "text":"screen failed"}
                ]
                result.append(ToolMessage(content=tool_return, tool_call_id=tool_call["id"]))
        else:
            result.append(ToolMessage(content=observation,tool_call_id=tool_call["id"]))
    return {"messages":result}

def put_memory_node(state:GraphState, runtime:Runtime):
    """增加记忆节点，决定是否保存长期记忆，不对短期记忆进行修改，仅保存文本"""
    memory_mode = runtime.context.memory_mode
    if memory_mode:
        is_memory = state["is_memory"]
        last_human_content = state["messages"][-2].content
        if isinstance(last_human_content, list):
            memory_content = "\n".join([item["text"] for item in last_human_content if item.get("type", "text")=="text"])
        else:
            memory_content = last_human_content
        store = runtime.store
        user_name = runtime.context.user_name
        namespace = ("master", user_name)
        if is_memory:
            store.put(namespace, str(uuid.uuid4()), {"data":memory_content})

def decider_function(state:GraphState):
    """
    判断函数，负责判断是否需要调用工具
    """
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool"
    else:
        return "end"



# 构建图
# =====短期记忆暂时保存在内存中=====
shortMemory = MemorySaver() 

# =====长期记忆保存在PostgresStore数据库中=====
## =====embedding 模型=====
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
## =====数据库链接字符串=====
db_uri = "postgresql://neondb_owner:npg_nj0d7IUbghqa@ep-billowing-truth-a1xg5e8c-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&options=endpoint%3Dep-billowing-truth-a1xg5e8c-pooler"
## =====连接池=====
pool = ConnectionPool(
    conninfo=db_uri,
    max_size=20,                #最大并发数
    kwargs={"autocommit":True}  
)
## =====长期记忆数据库存储===== 
store = PostgresStore(
    pool,
    index={
    "dims":384,
    "embed":embeddings,
    }
)
store.setup()

Amadeus_builder = StateGraph(GraphState, context_schema=ContextSchema)
Amadeus_builder.add_node("amadeus_kernel", amadeus_node)
Amadeus_builder.add_node("tool", tool_node)
Amadeus_builder.add_node("put_memory", put_memory_node)
Amadeus_builder.add_edge(START, "amadeus_kernel")
Amadeus_builder.add_edge("amadeus_kernel", "put_memory")
Amadeus_builder.add_conditional_edges(
    "put_memory",
    decider_function,
    {
        "tool":"tool",
        "end":END
    }
)
Amadeus_builder.add_edge("tool", "amadeus_kernel")
Amadeus = Amadeus_builder.compile(checkpointer=shortMemory, store=store)
# 展示执行图
# display(Image(Amadeus.get_graph(xray=True).draw_mermaid_png()))
current_file = os.path.dirname(__file__)
graph_location = os.path.join(current_file, "graph.png")
with open(graph_location, "wb") as f:
    f.write(Amadeus.get_graph(xray=True).draw_mermaid_png())




