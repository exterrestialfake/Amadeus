// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::{Deserialize, Serialize};

#[derive(Serialize)]
struct InvokeRequest {
    prompt: String,
    user_name: String,
}

#[derive(Deserialize)]
struct InvokeResponse {
    response: String,
}

#[tauri::command]
async fn invoke(prompt: String) -> Result<String, String> {
    // 构造发送到Python核心的请求数据
    let req_body = InvokeRequest {
        prompt,
        user_name: "christina".to_string(), // 可以根据需要修改以支持多用户
    };

    // 使用 reqwest 发起 POST 请求
    let client = reqwest::Client::new();
    let res = client
        .post("http://127.0.0.1:8000/api/invoke")
        .json(&req_body)
        .send()
        .await
        .map_err(|e| format!("无法连接到Python核心: {}", e))?;

    if res.status().is_success() {
        let invoke_res: InvokeResponse = res
            .json()
            .await
            .map_err(|e| format!("解析响应数据失败: {}", e))?;
        Ok(invoke_res.response)
    } else {
        Err(format!("Python核心返回了错误状态码: {}", res.status()))
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![invoke])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
