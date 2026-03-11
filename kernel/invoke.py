from agent import Amadeus, ContextSchema

if __name__ == "__main__":

    print("请输入问题，输入“晚安”结束对话")
    question = "你好，我的名字是什么？你应当知道的"
    while question != "晚安":
        message = {"role":"user", "content":question}
        result = Amadeus.invoke(
            {"messages":[message]},
            {"configurable":{"thread_id":"lab_test", "screen_permission":"1"}},
            context=ContextSchema(user_name="christina", memory_mode=True)
        )
        print("="*10+"Amadeus message"+"="*10)
        print(result["messages"][-1].content)
        print("="*10+"Amadeus message"+"="*10)
        question = input()

