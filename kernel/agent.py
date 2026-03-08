import json
import os
from PIL import ImageGrab
import pygetwindow as gw
import base64
from io import BytesIO
from IPython.display import Image, display

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver #暂时保存在内存中


# 获取指定模型的api
def api_get(model_name):
    current_file = os.path.dirname(__file__)
    config_file = os.path.join(current_file, "api.json")
    with open(config_file) as f:
        config = json.load(f)[model_name]
    return config
config= api_get("gemini")


# LLM绑定
servant = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key=config["api_key"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    max_tokens=1000,
    temperature=0.4
)

# 定义状态模式
class GraphState(MessagesState):
    summary:str

# 配置工具函数
@tool
def capture_master_screen():
    """
    当你想要知道master在干什么时，可以调用此工具截图master的当前活动窗口，
    来理解master在干什么
    """
    # =====判断当前活动窗口并截取=====
    active_win = gw.getActiveWindow()
    if active_win:
        bbox = (active_win.left, active_win.top, active_win.right, active_win.bottom)
        screenshot = ImageGrab.grab(bbox)
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

# graph
## Node
def amadeus_node(state:GraphState):
    """
    amadeus节点，负责调用llm
    """
    system_message = SystemMessage(content="你是动漫《命运石之门》之中的牧濑红莉栖，" \
    "我是你的master,请你以后用她的语气和口吻与我对话，并在表达一段话之前用()涵盖语气词，如(生气)，(好奇)"\
    "你拥有权限，可以随便使用截屏工具。")
    return {
        "messages":[
            amadeus.invoke(
                [system_message]+
                state["messages"])
            ]
        }

def tool_node(state:GraphState):
    """
    工具节点，负责调用工具
    """
    result = []
    last_message = state["messages"][-1]
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool = tool_box[tool_name]
        tool_args = tool_call["args"]
        observation = tool.invoke(tool_args)
        if tool_name == "capture_master_screen":
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
        result.append(ToolMessage(content=observation,tool_call_id=tool_call["id"]))
    return {"messages":result}

def decider_function(state:GraphState):
    """
    判断节点，负责判断是否需要调用工具
    """
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool"
    else:
        return "end"

## Graph
# =====短期记忆暂时保存在内存中=====
shortMemory = MemorySaver() 
Amadeus_builder = StateGraph(GraphState)
Amadeus_builder.add_node("amadeus_kernel", amadeus_node)
Amadeus_builder.add_node("tool", tool_node)
Amadeus_builder.add_edge(START, "amadeus_kernel")
Amadeus_builder.add_conditional_edges(
    "amadeus_kernel",
    decider_function,
    {
        "tool":"tool",
        "end":END
    }
)
Amadeus_builder.add_edge("tool", "amadeus_kernel")
Amadeus = Amadeus_builder.compile(checkpointer=shortMemory)
### 展示执行图
# display(Image(Amadeus.get_graph(xray=True).draw_mermaid_png()))
# current_file = os.path.dirname(__file__)
# graph_location = os.path.join(current_file, "graph.png")
# with open(graph_location, "wb") as f:
#     f.write(Amadeus.get_graph(xray=True).draw_mermaid_png())
if __name__ == "__main__":
   
    # def path_to_base64_url(path):
    #     """自动判断是路径还是链接，如果是本地路径则转为 Base64 URL"""
    #     if os.path.isfile(path):
    #         with open(path, "rb") as f:
    #             ext = os.path.splitext(path)[1].replace(".", "")
    #             if ext == "jpg": ext = "jpeg"
    #             encoded = base64.b64encode(f.read()).decode("utf-8")
    #         return encoded, f"image/{ext}"
    #     return path # 如果不是文件，原样返回（比如已经已经是 http 链接了）

    # image_path = "D:\\Document\\project\\Amadeus\\kernel\\test_image.png"
    # result = Amadeus.invoke(
    #     {"messages":[{
    #             "role":"user", 
    #             "content":
    #             [
    #                 {"type":"text", "text":"你好，帮我分析以下图片"},
    #                 {
    #                     "type":"image", 
    #                     "base64":path_to_base64_url(image_path)[0],
    #                     "mime_type":path_to_base64_url(image_path)[1]
    #                 }
    #             ]
    #         }]
    #     },
    #     {"configurable":{"thread_id":"lab_test"}}
    # )
    # print(result["messages"][-1].content)

    print("请输入问题，输入“晚安”结束对话")
    question = "你好，你是谁?"
    while question != "晚安":
        message = {"role":"user", "content":question}
        result = Amadeus.invoke(
            {"messages":[message]},
            {"configurable":{"thread_id":"lab_test"}}
        )
        print("="*10+"Amadeus message"+"="*10)
        print(result["messages"][-1].content)
        print("="*10+"Amadeus message"+"="*10)
        question = input()





