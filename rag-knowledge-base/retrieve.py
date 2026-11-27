"""
retrieve.py —— 检索 + 答案生成
向量检索 + BM25 混合（EnsembleRetriever）+ CrossEncoder 重排序 + 答案溯源。
Agent 工具链：Pydantic 参数校验 + tenacity 失败重试 + 异常捕获（打印重试日志）。
LLM 二选一：DeepSeek API / Ollama 本地，由 config.LLM_BACKEND 控制。
"""
import os
import time
import argparse
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
import logging

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
# 兼容 langchain 0.3.x（官方路径）与 1.0+（迁到 langchain_classic 的路径）
try:
    from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
    from langchain.retrievers.document_compressors import CrossEncoderReranker
except ImportError:
    from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
    from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rag")


class QueryInput(BaseModel):
    """Pydantic 参数校验：问题非空且长度受限。"""
    question: str = Field(..., min_length=2, max_length=500)


def make_llm():
    if config.LLM_BACKEND == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.DEEPSEEK_MODEL,
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            temperature=0,
        )
    else:  # ollama
        from langchain_community.llms import Ollama
        return Ollama(model=config.OLLAMA_MODEL, base_url=config.OLLAMA_BASE_URL, temperature=0)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
       before_sleep=before_sleep_log(logger, logging.WARNING))
def call_llm(llm, prompt):
    """tenacity 失败重试，重试过程写日志（截图证据）。"""
    return llm.invoke(prompt)


def build_retriever(db_dir, top_k):
    # 与 ingest.py 保持一致：优先魔搭本地路径，无缓存时回退 HF model id
    model_path = config.LOCAL_EMBEDDING_PATH if os.path.isdir(config.LOCAL_EMBEDDING_PATH) else config.EMBEDDING_MODEL
    embeddings = HuggingFaceEmbeddings(model_name=model_path)
    vectordb = Chroma(collection_name=config.COLLECTION, embedding_function=embeddings,
                      persist_directory=db_dir)

    # BM25 需要原始文本，从向量库取回所有文档
    all_docs = vectordb.get(include=["documents", "metadatas"])
    from langchain_core.documents import Document
    bm25_docs = [Document(page_content=t, metadata=m)
                 for t, m in zip(all_docs["documents"], all_docs["metadatas"])]
    bm25 = BM25Retriever.from_documents(bm25_docs, k=top_k)
    vector = vectordb.as_retriever(search_kwargs={"k": top_k})
    ensemble = EnsembleRetriever(retrievers=[vector, bm25], weights=[0.6, 0.4])

    # CrossEncoder 重排序（同样优先魔搭本地路径）
    rerank_path = config.LOCAL_RERANK_PATH if os.path.isdir(config.LOCAL_RERANK_PATH) else "cross-encoder/ms-marco-MiniLM-L-6-v2"
    compressor = CrossEncoderReranker(model=HuggingFaceCrossEncoder(model_name=rerank_path),
                                      top_n=min(top_k, config.RERANK_TOP_N))
    return ContextualCompressionRetriever(base_compressor=compressor, base_retriever=ensemble)


def answer(question, db_dir=config.DB_DIR, top_k=config.TOP_K, with_llm=True):
    q = QueryInput(question=question)  # 参数校验
    retriever = build_retriever(db_dir, top_k)
    docs = retriever.invoke(q.question)

    # 答案溯源：返回引用片段 + 来源文件名/页码
    sources = []
    for d in docs:
        meta = d.metadata or {}
        sources.append({"source": meta.get("source", "unknown"),
                        "page": meta.get("page", "N/A"),
                        "snippet": d.page_content[:150]})
    context = "\n\n".join(d.page_content for d in docs)

    result = {"question": q.question, "sources": sources,
              "context": context, "context_len": len(context)}
    if with_llm:
        prompt = f"基于以下资料回答问题，不要编造。资料：\n{context}\n\n问题：{q.question}\n答案："
        llm = make_llm()
        try:
            t0 = time.time()
            resp = call_llm(llm, prompt)  # 只调用一次，tenacity 负责重试
            result["answer"] = resp.content if hasattr(resp, "content") else str(resp)
            result["latency"] = round(time.time() - t0, 3)
        except Exception as e:
            result["answer"] = f"[生成失败，已重试 3 次] {e}"
            result["latency"] = None
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question", help="要问的问题")
    ap.add_argument("--top-k", type=int, default=config.TOP_K)
    ap.add_argument("--no-llm", action="store_true", help="只测检索，不调 LLM（省 key/省时）")
    args = ap.parse_args()
    r = answer(args.question, top_k=args.top_k, with_llm=not args.no_llm)
    print("=" * 50)
    print("问题:", r["question"])
    if "answer" in r:
        print("答案:", r["answer"])
        print("延迟:", r["latency"], "s")
    print("引用来源:")
    for i, s in enumerate(r["sources"], 1):
        print(f"  [{i}] {s['source']} (page {s['page']}): {s[' snippet'][:80]}...")
    print("=" * 50)
