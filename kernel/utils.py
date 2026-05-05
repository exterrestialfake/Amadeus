def load_file(file_path: str)->str:
    """读取文件内容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def save_file(file_path: str, content: str):
    """保存文件内容"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)