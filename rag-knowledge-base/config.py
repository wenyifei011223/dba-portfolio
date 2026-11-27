"""RAG 项目配置：LLM 后端二选一 + 参数实验取值。"""
import os

# 国内直连 huggingface.co 常超时，首次下载 Embedding / CrossEncoder 模型前设镜像。
# 若已自行配好代理，可删除这一行。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# ===== LLM 后端选择 =====
# "deepseek" -> 用 DeepSeek API，需设置环境变量 DEEPSEEK_API_KEY
# "ollama"   -> 本地 Ollama，需先 ollama pull qwen2.5:7b（免费，慢一些）
LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"

# ===== Embedding（手册指定，本地免 API 费）=====
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ===== 切块与检索默认参数 =====
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100
TOP_K = 5
RERANK_TOP_N = 10  # CrossEncoder 重排序候选数

# ===== 路径 =====
DATA_DIR = "data"
DB_DIR = "chroma_db"
RESULTS_DIR = "results"
COLLECTION = "mysql_kb"

# ===== 参数实验取值（evaluate.py 用）=====
GRID_CHUNK_SIZE = [256, 512, 1024]
GRID_CHUNK_OVERLAP = [0, 100, 200]
GRID_TOP_K = [3, 5, 10]
