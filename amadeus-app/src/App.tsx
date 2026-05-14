import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { InputPanel, OutputPanel, Message } from "./components/MessagePanel";
import CharacterPanel from "./components/CharacterPanel";
import "./App.css";

function App() {
  const [messages, setMessages] = useState<Message[]>([]);

  // 处理发送逻辑
  const handleUserSend = async (userInput: string) => {
    // 立刻通过 setMessages 添加用户消息，输出界面“秒出”用户消息
    const userMsg: Message = { id: Date.now(), role: "user", content: userInput };
    setMessages(prev => [...prev, userMsg]);

    try {
      // 发起请求
      const response = await invoke<string>("invoke", { prompt: userInput });
      // 拿到结果后，输出 AI 消息
      const aiMsg: Message = { id: Date.now() + 1, role: "assistant", content: response };
      setMessages(prev => [...prev, aiMsg]);
    } catch (error) {
      console.error("Failed to invoke:", error);
      // setMessages(prev => [...prev, Message()]);
    }
  };

  return (
    <div className="app-container">
      {/* =======================================================
          左侧边栏区域：包含历史记录列表 和 底部设置按钮
      ======================================================= */}
      <aside className="sidebar">
        <div className="history-panel">
          <h3>历史记录</h3>
          <div className="history-list">
            <div className="history-item">最近的交谈...</div>
          </div>
        </div>
        <button className="config-button">config</button>
      </aside>

      {/* =======================================================
          中间主内容区：包含顶部的聊天对话流 和 底部的输入框
      ======================================================= */}
      <main className="main-content">
        <OutputPanel messages={messages} />
        <InputPanel onUserSend={handleUserSend} />
      </main>

      {/* =======================================================
          右侧区域：预留给完整的 Amadeus 形象图片展示
      ======================================================= */}
      <aside className="character-panel">
        <div className="character-view">
          <h2>Amadeus 形象</h2>
          <CharacterPanel />
        </div>
      </aside>
    </div>
  );
}

export { App };
