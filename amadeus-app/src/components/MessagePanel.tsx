import { useState } from "react";
import "./MessagePanel.css"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"


// 消息的数据结构
export type Message = {
    id: number;
    role: "user" | "assistant";
    content: string;
};

// ============================================================
// OutputPanel 组件：接收消息列表，负责渲染对话流
// ============================================================
interface OutputPanelProps {
    messages: Message[];
}

export const OutputPanel: React.FC<OutputPanelProps> = ({ messages }) => {

    const messageRender = (msg: Message) => {
        if (msg.role === "assistant")
            return (
                <div key={msg.id} className="AIMessage-row">
                    <div className="avatar">
                        <img src="/christina.svg" className="avatar-img" alt="christina" />
                    </div>
                    <div className="AIMessage-bubble">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                        </ReactMarkdown >
                    </div>
                </div>
            );
        else
            return (
                <div key={msg.id} className="UserMessage-row">
                    <div className="UserMessage-bubble">
                        {msg.content}
                    </div>
                </div>
            );
    };

    return (
        <section className="output-panel">
            {messages.length > 0
                ? messages.map((msg) => messageRender(msg))
                : <div className="placeholder-text">开始与 Amadeus 的对话...</div>
            }
        </section>
    );
};

// ============================================================
// InputPanel 组件：负责输入和发送消息，通过 onSend 将消息传给父组件
// ============================================================
interface InputPanelProps {
    onUserSend: (userInput: string) => void;
}

export const InputPanel: React.FC<InputPanelProps> = ({ onUserSend }) => {
    const [inputVal, setInputVal] = useState("");

    const handleInputSubmit = (formData: FormData) => {
        const input = formData.get("chat-input") as string;
        if (!input?.trim()) return;

        setInputVal(""); // 立刻清空输入框
        onUserSend(input); // 首先显示用户输入，然后显示模型输出
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        // 如果按下 Enter 键且没有按住 Shift 键
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault(); // 阻止默认换行行为
            const form = e.currentTarget.form;
            if (form) {
                // 手动触发 form 的 action。在 React 19 中，可以直接调用其 Action
                const formData = new FormData(form);
                handleInputSubmit(formData);
            }
        }
    };

    return (
        <footer className="input-panel">
            <form action={handleInputSubmit}>
                <textarea
                    id="chat-input"
                    name="chat-input"
                    rows={1}
                    value={inputVal}
                    onChange={(e) => setInputVal(e.currentTarget.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="开始与Amadeus的对话"
                    autoComplete="off"
                />
            </form>
        </footer>
    );
};