"""
ingest.py —— 文档入库
解析 MD / PDF / DOCX/TXT → 去页眉页脚空行 → 递归切块 → Embedding → Chroma 持久化。
打印文档数、切块数、失败数（截图证据）。
"""
import os
import glob
import shutil
import argparse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import config


def load_documents(data_dir):
    """按扩展名解析文档，返回 (docs, fail_count)。"""
    docs, failed = [], 0
    patterns = ["**/*.md", "**/*.txt", "**/*.pdf", "**/*.docx"]
    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(data_dir, p), recursive=True))

    for path in files:
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".md", ".txt"):
                from langchain_community.document_loaders import TextLoader
                loader = TextLoader(path, encoding="utf-8")
            elif ext == ".pdf":
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(path)
            elif ext == ".docx":
                from langchain_community.document_loaders import Docx2txtLoader
                loader = Docx2txtLoader(path)
            else:
                continue
            loaded = loader.load()
            # 清洗：去空行、去常见页眉页脚
            for d in loaded:
                lines = [ln.strip() for ln in d.page_content.splitlines()]
                lines = [ln for ln in lines if ln and len(ln) > 3]
                d.page_content = "\n".join(lines)
                d.metadata["source"] = os.path.basename(path)
            docs.extend(loaded)
        except Exception as e:
            failed += 1
            print(f"[FAIL] {path}: {e}")
    return docs, failed


def build(chunk_size, chunk_overlap, db_dir, rebuild=True):
    if rebuild and os.path.exists(db_dir):
        shutil.rmtree(db_dir)

    docs, failed = load_documents(config.DATA_DIR)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    Chroma.from_documents(chunks, embeddings, collection_name=config.COLLECTION,
                          persist_directory=db_dir)

    print("=" * 50)
    print(f"文档数: {len(docs)}")
    print(f"切块数: {len(chunks)}  (chunk_size={chunk_size}, overlap={chunk_overlap})")
    print(f"失败数: {failed}")
    print(f"向量库: {db_dir}")
    print("=" * 50)
    return len(docs), len(chunks), failed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk-size", type=int, default=config.CHUNK_SIZE)
    ap.add_argument("--overlap", type=int, default=config.CHUNK_OVERLAP)
    ap.add_argument("--db-dir", default=config.DB_DIR)
    args = ap.parse_args()
    build(args.chunk_size, args.overlap, args.db_dir)
