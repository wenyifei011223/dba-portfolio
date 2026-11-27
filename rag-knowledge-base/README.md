# RAG 私有知识库（最小可运行版）

> 定位（手册原话）：证明会 Python 和数据处理，能跑通 + 拿出参数对比表即可，不追求完美。
> 技术栈：Python 3.10 + LangChain + Chroma + 本地 Embedding（all-MiniLM-L6-v2，免 API 费）+ LLM 二选一。

## 〇、环境准备（动手前先看，三个卡点）

| 卡点 | 现状（2026-11-27 自查） | 解决办法 |
|---|---|---|
| Python 版本 | 本机是 **3.13**，requirements 锁定依赖（chromadb 0.5.23 / torch）在 3.13 装不上 | **必须用 3.10**：装 Python 3.10 后 `py -3.10 -m venv venv`；或用 conda `conda create -n rag python=3.10` |
| LLM 后端 | 本机无 Ollama、无 `DEEPSEEK_API_KEY` | 只想跑通/出参数表可**先用 `--no-llm`（默认），完全不需要 LLM**；要生成答案再二选一 |
| HuggingFace 下载 | 国内直连 hf.co 常超时 | `config.py` 已设 `HF_ENDPOINT=https://hf-mirror.com`；如仍失败手动 `set HF_ENDPOINT=https://hf-mirror.com` |

> **今天最短路径**：Python 3.10 建 venv → `pip install -r requirements.txt` → `python evaluate.py --quick`（3 组 × 5 题，约几分钟验证流程）→ 通过后跑完整 `python evaluate.py`。全程无需 key。

## 一、快速开始

```bash
cd rag-knowledge-base
py -3.10 -m venv venv && venv\Scripts\activate   # 必须用 3.10，见第〇节
pip install -r requirements.txt

# 1) 放语料：把 8 篇笔记（md）或 PDF/DOCX 复制到 data/
# 2) 建向量库（打印文档数/切块数/失败数 → 截图证据）
python ingest.py

# 3) 问一个问题（只测检索，不调 LLM，省 key）
python retrieve.py "MySQL 8 默认的认证插件是什么？" --no-llm

# 4) 参数对比实验（先跑快速验证，再跑完整）
python evaluate.py --quick          # 快速验证：只跑 chunk_size 的 3 组 × 5 题
python evaluate.py                  # 完整 9 组 × 20 题，约 20–40 分钟
python evaluate.py --with-llm       # 加 LLM 测准确率（需 key/Ollama，更慢）
```

## 二、LLM 后端二选一

| 后端 | 配置 | 优点 | 缺点 |
|---|---|---|---|
| Ollama（默认） | `export LLM_BACKEND=ollama`，先 `ollama pull qwen2.5:7b` | 免费、离线 | 慢，需装模型 |
| DeepSeek API | `export LLM_BACKEND=deepseek`，`export DEEPSEEK_API_KEY=你的key` | 快、答案好 | 需付费 key |

> 只需验证检索效果时加 `--no-llm`，两种后端都不需要。

## 三、语料说明

放到 `data/` 的文件支持 `.md` / `.txt` / `.pdf` / `.docx`，会统一做：
- 去空行、去页眉页脚
- `RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=100)` 切块
- `all-MiniLM-L6-v2` 本地向量化 → Chroma 持久化到 `chroma_db/`

**建议**：先把 `../notes/` 的 8 篇笔记拷进来跑通，再考虑加公开 MySQL 官方文档 PDF 凑 120+ 份。

## 四、模块对应简历四条

| 模块 | 简历表述 |
|---|---|
| `ingest.py` | 多格式文档解析清洗、向量化入库 |
| `retrieve.py` | 向量+BM25 混合检索、CrossEncoder 重排序、Agent 工具链（Pydantic+tenacity） |
| `retrieve.py` 的 sources | 答案溯源（返回引用片段和来源文件/页码） |
| `evaluate.py` | 多组对照测试验证 chunk_size/top-k 对问答效果的影响 |

## 五、产出（跑完后填）

- `results/evaluation.csv` —— 9 组参数的命中率/准确率/索引耗时/延迟
- `results/param_compare.png` —— 参数对比图
- 运行 `python ingest.py` 的截图 —— 文档数/切块数/失败数

## 六、面试话术（30 秒）

> "我用 LangChain + Chroma 做了个 MySQL 知识库：把 8 篇运维笔记和多格式文档解析清洗后切块，用本地 MiniLM 向量化入库；检索用向量加 BM25 混合，再上 CrossEncoder 重排序，答案带来源溯源。参数上对比了 chunk_size 256/512/1024、overlap 0/100/200、top_k 3/5/10 共九组，用 20 个问答对测命中率，结果在 evaluation.csv 里——这块证明的是我的 Python 工程化和数据处理能力。"
